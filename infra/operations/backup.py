"""Encrypted consistent PostgreSQL/private-file recovery points (age + pg tools)."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any
from uuid import uuid4

from rentalops_api.catalog_storage import CatalogError, PhotoStorage
from rentalops_api.config import DatabaseSettings
from rentalops_api.operations import (
    OperationsError,
    maintenance,
    operation_root,
    private_path,
)
from rentalops_api.readiness import check_schema, schema_head
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

FORMAT = 1


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    try:
        subprocess.run(command, env=env, check=True, capture_output=True, timeout=600)
    except OSError, subprocess.SubprocessError:
        raise OperationsError("External operation failed.") from None


def pg_environment(settings: DatabaseSettings) -> dict[str, str]:
    url = settings.url
    if url.query:
        raise OperationsError("Ambiguous database options refused.")
    # Remove libpq ambient redirections. Credentials never enter argv or output.
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env.update(
        {
            "PGHOST": url.host or "",
            "PGPORT": str(url.port or 5432),
            "PGDATABASE": url.database or "",
            "PGUSER": url.username or "",
            "PGPASSWORD": url.password or "",
            "PGCONNECT_TIMEOUT": "3",
            "PGOPTIONS": "-c timezone=UTC -c statement_timeout=600000",
        }
    )
    return env


@contextmanager
def connection(settings: DatabaseSettings) -> Iterator[Connection]:
    engine = create_engine(
        settings.url,
        echo=False,
        hide_parameters=True,
        connect_args={"connect_timeout": 3},
    )  # Operator bypasses product barrier only while holding exclusive maintenance.
    try:
        with engine.connect() as db:
            yield db
    finally:
        engine.dispose()


def database_manifest(db: Connection) -> dict[str, Any]:
    version = check_schema(db)
    tables = sorted(inspect(db).get_table_names(schema="public"))
    result: dict[str, Any] = {}
    for table in tables:
        if not re.fullmatch(r"[a-z_]+", table):
            raise OperationsError("Unexpected database schema.")
        rows = sorted(
            db.scalars(
                text(f'SELECT row_to_json(t)::text FROM public."{table}" t')
            ).all()
        )
        result[table] = {
            "count": len(rows),
            "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
        }
    photos = [
        dict(row)
        for row in db.execute(
            text(
                "SELECT storage_key, size, sha256 FROM product_photos ORDER BY storage_key"
            )
        ).mappings()
    ]
    return {"schema": version, "tables": result, "photos": photos}


def checked_photos(db_manifest: dict[str, Any], root: Path) -> None:
    storage = PhotoStorage(root)
    for photo in db_manifest["photos"]:
        storage.read(photo["storage_key"], photo["size"], photo["sha256"])


def backup(
    settings: DatabaseSettings,
    storage_root: Path,
    output_dir: Path,
    operations_root: Path,
    recipient_file: Path,
) -> Path:
    started = monotonic()
    for root in (storage_root, output_dir, operations_root):
        private_path(root)
    if operation_root() != operations_root:
        raise OperationsError("Shared maintenance configuration mismatch.")
    private_path(recipient_file, directory=False)
    if any(
        root == other or root in other.parents or other in root.parents
        for root, other in ((storage_root, output_dir), (storage_root, operations_root))
    ):
        raise OperationsError("Independent directories required.")
    point = "point-" + uuid4().hex
    with TemporaryDirectory(prefix=".partial-", dir=output_dir) as temporary:
        stage = Path(temporary)
        plain = stage / "plain"
        plain.mkdir(mode=0o700)
        files = plain / "files"
        files.mkdir(mode=0o700)
        with maintenance(operations_root), connection(settings) as db:
            snapshot = database_manifest(db)
            checked_photos(snapshot, storage_root)
            run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--file",
                    str(plain / "database.dump"),
                ],
                env=pg_environment(settings),
            )
            os.chmod(plain / "database.dump", 0o600)
            for path in sorted(storage_root.iterdir()):
                private_path(path, directory=False)
                if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", path.name):
                    raise OperationsError("Unexpected private file.")
                shutil.copyfile(path, files / path.name)
                os.chmod(files / path.name, 0o600)
            # Refuse a writer bypassing the configured maintenance barrier.
            if snapshot != database_manifest(db):
                raise OperationsError("Database changed during maintenance.")
            checked_photos(snapshot, files)
        members = {
            path.relative_to(plain).as_posix(): {
                "size": path.stat().st_size,
                "sha256": digest(path),
            }
            for path in plain.rglob("*")
            if path.is_file()
        }
        manifest = {
            "format": FORMAT,
            "created_at": datetime.now(UTC).isoformat(),
            "database": snapshot,
            "members": members,
        }
        (plain / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        os.chmod(plain / "manifest.json", 0o600)
        archive = stage / "package.tar"
        with tarfile.open(archive, "w") as package:
            for path in sorted(plain.rglob("*")):
                if path.is_file():
                    package.add(path, arcname=path.relative_to(plain).as_posix())
        os.chmod(archive, 0o600)
        published = stage / "published"
        published.mkdir(mode=0o700)
        encrypted = published / "package.tar.age"
        run(
            [
                "age",
                "--encrypt",
                "--recipients-file",
                str(recipient_file),
                "--output",
                str(encrypted),
                str(archive),
            ]
        )
        os.chmod(encrypted, 0o600)
        # This outer manifest is a transport receipt, never trusted for restoration.
        receipt = {
            "format": FORMAT,
            "created_at": manifest["created_at"],
            "ciphertext_sha256": digest(encrypted),
            "encrypted_bytes": encrypted.stat().st_size,
            "duration_seconds": round(monotonic() - started, 3),
        }
        (published / "manifest.json").write_text(json.dumps(receipt), encoding="utf-8")
        os.chmod(published / "manifest.json", 0o600)
        target = output_dir / point
        published.rename(
            target
        )  # Same-volume atomic publish; incomplete never appears.
        return target


@contextmanager
def verified_package(
    manifest: Path, identity_file: Path, scratch_root: Path
) -> Iterator[tuple[Path, dict[str, Any]]]:
    private_path(manifest, directory=False)
    private_path(identity_file, directory=False)
    private_path(scratch_root)
    encrypted = manifest.parent / "package.tar.age"
    private_path(encrypted, directory=False)
    receipt = json.loads(manifest.read_text(encoding="utf-8"))
    if receipt.get("format") != FORMAT or digest(encrypted) != receipt.get(
        "ciphertext_sha256"
    ):
        raise OperationsError("Recovery point integrity failed.")
    with TemporaryDirectory(prefix="verify-", dir=scratch_root) as temporary:
        root = Path(temporary)
        archive = root / "package.tar"
        run(
            [
                "age",
                "--decrypt",
                "--identity",
                str(identity_file),
                "--output",
                str(archive),
                str(encrypted),
            ]
        )
        os.chmod(archive, 0o600)
        with tarfile.open(archive) as package:
            members = package.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise OperationsError("Recovery manifest incomplete.")
            for member in members:
                if not member.isfile() or not re.fullmatch(
                    r"manifest\.json|database\.dump|files/[0-9a-f]{32}\.(jpg|png|webp)",
                    member.name,
                ):
                    raise OperationsError("Unsafe recovery member.")
                target = root / member.name
                target.parent.mkdir(mode=0o700, exist_ok=True)
                source = package.extractfile(member)
                if source is None:
                    raise OperationsError("Recovery member missing.")
                with source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
                os.chmod(target, 0o600)
        authenticated = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if authenticated.get("format") != FORMAT:
            raise OperationsError("Recovery format incompatible.")
        expected = authenticated.get("members", {})
        if (
            set(expected) != set(names) - {"manifest.json"}
            or "database.dump" not in expected
        ):
            raise OperationsError("Recovery manifest incomplete.")
        for name, entry in expected.items():
            path = root / name
            if path.stat().st_size != entry["size"] or digest(path) != entry["sha256"]:
                raise OperationsError("Recovery member integrity failed.")
        if authenticated["database"]["schema"] != schema_head():
            raise OperationsError("Recovery schema incompatible.")
        (root / "files").mkdir(mode=0o700, exist_ok=True)
        checked_photos(authenticated["database"], root / "files")
        yield root, authenticated


def restore(
    manifest: Path,
    identity_file: Path,
    scratch_root: Path,
    target_settings: DatabaseSettings,
    target_storage: Path,
    *,
    discardable: bool,
) -> dict[str, Any]:
    started = monotonic()
    url = target_settings.url
    if (
        not discardable
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.query
        or not re.fullmatch(r"rentalops_restore_test_[0-9a-f]{32}", url.database or "")
    ):
        raise OperationsError("Explicit local disposable recovery database required.")
    private_path(target_storage)
    if (
        any(target_storage.iterdir())
        or target_storage == scratch_root
        or (
            manifest.parent == target_storage
            or manifest.parent in target_storage.parents
        )
    ):
        raise OperationsError("Empty independent recovery storage required.")
    with verified_package(manifest, identity_file, scratch_root) as (root, approved):
        # Authenticate everything before any target mutation or connection.
        admin = DatabaseSettings(url.set(database="postgres"))
        with connection(admin) as db:
            exists = db.scalar(
                text("SELECT 1 FROM pg_database WHERE datname=:name"),
                {"name": url.database},
            )
            db.rollback()
            if not exists:
                db.execution_options(isolation_level="AUTOCOMMIT").execute(
                    text(f'CREATE DATABASE "{url.database}"')
                )
        with connection(target_settings) as db:
            if db.scalar(
                text(
                    "SELECT count(*) FROM pg_namespace WHERE nspname NOT IN "
                    "('public','pg_catalog','information_schema') "
                    "AND nspname NOT LIKE 'pg_%'"
                )
            ) or db.scalar(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname NOT IN "
                    "('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'"
                )
            ):
                raise OperationsError("Empty recovery database required.")
        run(
            [
                "pg_restore",
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
                "--single-transaction",
                "--dbname",
                url.database or "",
                str(root / "database.dump"),
            ],
            env=pg_environment(target_settings),
        )
        for path in (root / "files").iterdir():
            with (
                path.open("rb") as source,
                (target_storage / path.name).open("xb") as target,
            ):
                shutil.copyfileobj(source, target)
            os.chmod(target_storage / path.name, 0o600)
        with connection(target_settings) as db:
            actual = database_manifest(db)
            if actual != approved["database"]:
                raise OperationsError("Recovered database validation failed.")
            checked_photos(actual, target_storage)
            # Retain attribution/history; revoke recovered authority before use.
            for table in ("auth_sessions", "password_links"):
                db.execute(
                    text(
                        f"UPDATE {table} SET revoked_at=now() WHERE revoked_at IS NULL"
                    )
                )
            db.commit()
        return {
            "status": "restored",
            "schema": actual["schema"],
            "table_count": len(actual["tables"]),
            "photo_count": len(actual["photos"]),
            "duration_seconds": round(monotonic() - started, 3),
        }


def backup_status(output_dir: Path, maximum_age_hours: float = 24) -> dict[str, Any]:
    private_path(output_dir)
    times = []
    for point in output_dir.glob("point-*"):
        private_path(point)
        receipt = point / "manifest.json"
        private_path(receipt, directory=False)
        value = json.loads(receipt.read_text(encoding="utf-8"))
        encrypted = point / "package.tar.age"
        private_path(encrypted, directory=False)
        if digest(encrypted) != value.get("ciphertext_sha256"):
            raise OperationsError("Backup integrity alert.")
        times.append(datetime.fromisoformat(value["created_at"]))
    age = (datetime.now(UTC) - max(times)).total_seconds() / 3600 if times else None
    return {
        "status": "ok"
        if age is not None and 0 <= age <= maximum_age_hours
        else "alert",
        "age_hours": round(age, 3) if age is not None else None,
        "recovery_points": len(times),
    }


def copy_recovery_point(manifest: Path, copy_dir: Path) -> Path:
    """Copy ciphertext only; real off-host transport is an operator gate."""
    private_path(copy_dir)
    source = private_path(manifest.parent)
    if (
        copy_dir == source
        or source in copy_dir.parents
        or copy_dir in source.parents
        or not re.fullmatch(r"point-[0-9a-f]{32}", source.name)
    ):
        raise OperationsError("Independent encrypted copy directory required.")
    receipt = json.loads(private_path(manifest, directory=False).read_text())
    encrypted = private_path(source / "package.tar.age", directory=False)
    if digest(encrypted) != receipt.get("ciphertext_sha256"):
        raise OperationsError("Recovery point integrity failed.")
    target = copy_dir / source.name
    if target.exists():
        raise OperationsError("Copy destination already exists.")
    with TemporaryDirectory(prefix=".partial-", dir=copy_dir) as temporary:
        stage = Path(temporary) / "published"
        stage.mkdir(mode=0o700)
        for item in (manifest, encrypted):
            shutil.copyfile(item, stage / item.name)
            os.chmod(stage / item.name, 0o600)
        if digest(stage / encrypted.name) != receipt["ciphertext_sha256"]:
            raise OperationsError("Encrypted copy integrity failed.")
        stage.rename(target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["backup", "verify", "restore", "status", "copy"]
    )
    parser.add_argument("--db-url-env", default="DATABASE_URL")
    parser.add_argument("--target-db-url-env", default="RESTORE_DATABASE_URL")
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--target-storage-root", type=Path)
    parser.add_argument("--operations-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--copy-dir", type=Path)
    parser.add_argument("--scratch-root", type=Path)
    parser.add_argument("--recipient-file", type=Path)
    parser.add_argument("--identity-file", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--discardable-target", action="store_true")
    args = parser.parse_args()
    required = {
        "backup": ["storage_root", "output_dir", "operations_root", "recipient_file"],
        "verify": ["manifest", "identity_file", "scratch_root"],
        "restore": ["manifest", "identity_file", "scratch_root", "target_storage_root"],
        "status": ["output_dir"],
        "copy": ["manifest", "copy_dir"],
    }
    if any(getattr(args, name) is None for name in required[args.command]):
        parser.error("Required operational arguments missing.")
    try:
        if args.command == "backup":
            point = backup(
                DatabaseSettings.from_url(os.environ.get(args.db_url_env)),
                args.storage_root,
                args.output_dir,
                args.operations_root,
                args.recipient_file,
            )
            result = {"status": "published", "point": point.name}
        elif args.command == "status":
            result = backup_status(args.output_dir)
        elif args.command == "copy":
            copied = copy_recovery_point(args.manifest, args.copy_dir)
            result = {"status": "copied", "point": copied.name}
        elif args.command == "verify":
            with verified_package(args.manifest, args.identity_file, args.scratch_root):
                result = {"status": "verified"}
        else:
            result = restore(
                args.manifest,
                args.identity_file,
                args.scratch_root,
                DatabaseSettings.from_url(os.environ.get(args.target_db_url_env)),
                args.target_storage_root,
                discardable=args.discardable_target,
            )
        print(json.dumps(result))
        if result["status"] == "alert":
            raise SystemExit(2)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        CatalogError,
        SQLAlchemyError,
        tarfile.TarError,
    ):
        # Do not echo argv, subprocess stderr, DB exceptions, or private file paths.
        print(json.dumps({"status": "failed", "category": "operations"}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
