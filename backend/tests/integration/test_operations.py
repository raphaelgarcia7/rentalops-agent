"""Real disposable database recovery, files, authority revocation and failures."""

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from alembic import command
from fastapi.testclient import TestClient
from infra.operations.backup import (
    backup,
    backup_status,
    copy_recovery_point,
    database_manifest,
    restore,
    run,
    verified_package,
)
from sqlalchemy import create_engine, text

from rentalops_api.auth import AuthError, AuthService, AuthSettings
from rentalops_api.catalog import CatalogService
from rentalops_api.catalog_contracts import ReasonCommand
from rentalops_api.catalog_storage import CatalogError, PhotoStorage
from rentalops_api.config import DatabaseSettings
from rentalops_api.database import build_engine, build_session_factory
from rentalops_api.main import app
from rentalops_api.operations import (
    OperationsError,
    active_operation,
    maintenance,
    private_path,
)
from rentalops_api.quotation_contracts import QuotationWrite
from rentalops_api.quotations import QuotationService

from ..conftest import migration_config
from ..database_safety import test_settings as safe_settings
from ..unit.test_catalog_storage import synthetic_image
from .test_quotations import draft
from .test_quotations import quotations as quotation_fixture

pytestmark = pytest.mark.integration


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    settings = safe_settings(os.environ.get("TEST_DATABASE_URL"), None)
    # Use only the already-validated loopback test server. Never its shared schema.
    base_url = settings.url.set(query={})
    administrator = create_engine(
        base_url.set(database="postgres"), hide_parameters=True
    )
    names = []

    def database(kind):
        name = f"rentalops_{kind}_test_{uuid4().hex}"
        with administrator.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as db:
            db.execute(text(f'CREATE DATABASE "{name}"'))
        names.append(name)
        return DatabaseSettings(base_url.set(database=name))

    roots = {}
    for name in ("photos", "backups", "barrier", "scratch", "restored", "offhost"):
        root = tmp_path / name
        root.mkdir(mode=0o700)
        roots[name] = root
    monkeypatch.setenv("OPERATIONS_ROOT", str(roots["barrier"]))
    key = tmp_path / "identity.txt"
    recipients = tmp_path / "recipients.txt"
    run(["age-keygen", "--output", str(key)])
    os.chmod(key, 0o600)
    # age-keygen emits public recipient on stdout only with -y; redirect privately.
    import subprocess

    result = subprocess.run(
        ["age-keygen", "-y", str(key)], check=True, capture_output=True
    )
    recipients.write_bytes(result.stdout)
    os.chmod(recipients, 0o600)
    source = database("source")
    engine = build_engine(source)
    try:
        with engine.begin() as db:
            command.upgrade(migration_config(db), "head")
        quotations = quotation_fixture.__wrapped__(engine)
        service, actor, ids = quotations
        catalog = CatalogService(service.factory, PhotoStorage(roots["photos"]))
        catalog.upload_photo(ids["arch"], 1, synthetic_image(), "image/png", actor)
        payload = draft(quotations)
        preview = service.preview(payload)
        saved, _ = service.write(
            QuotationWrite.model_validate(
                {
                    **payload.model_dump(mode="json"),
                    "request_id": str(uuid4()),
                    "catalog_versions": preview["catalog_versions"],
                }
            ),
            actor,
        )
        # Historical quotation keeps the first photo after detachment/replacement.
        first = catalog.get("products", ids["arch"])
        catalog.edit_photo(
            ids["arch"],
            first["photos"][0]["id"],
            ReasonCommand(expected_version=2, reason="Synthetic replacement"),
            actor,
        )
        catalog.upload_photo(
            ids["arch"], 3, synthetic_image(size=(9, 9)), "image/png", actor
        )
        auth = AuthService(
            service.factory,
            AuthSettings(
                "http://localhost:5173", False, "synthetic-operations-rate-key" * 3
            ),
        )
        token = auth.issue_link("synthetic-quotation@example.invalid", "access")
        password = "synthetic recovery passphrase"
        auth.set_password(token, password, "loopback")
        session_token, _ = auth.login(
            "synthetic-quotation@example.invalid", password, "loopback"
        )
        auth.create_user("synthetic-pending@example.invalid")
        pending = auth.issue_link("synthetic-pending@example.invalid", "access")
        yield {
            "source": source,
            "engine": engine,
            "roots": roots,
            "key": key,
            "recipients": recipients,
            "database": database,
            "quote": saved,
            "auth": auth,
            "session_token": session_token,
            "pending": pending,
            "password": password,
            "catalog": catalog,
            "actor": actor,
            "ids": ids,
        }
    finally:
        engine.dispose()
        # names were created by this fixture after strict host/name validation.
        for name in reversed(names):
            with administrator.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as db:
                db.execute(text(f'DROP DATABASE "{name}"'))
        administrator.dispose()
        for root in roots.values():
            # Only directories this fixture created under its unique pytest root.
            private_path(root)
            assert root.parent == tmp_path
            shutil.rmtree(root)
        for private_file in (key, recipients):
            private_path(private_file, directory=False)
            private_file.unlink()


def point(recovery):
    return backup(
        recovery["source"],
        recovery["roots"]["photos"],
        recovery["roots"]["backups"],
        recovery["roots"]["barrier"],
        recovery["recipients"],
    )


def recover(recovery, manifest, target=None):
    return restore(
        manifest,
        recovery["key"],
        recovery["roots"]["scratch"],
        target or recovery["database"]("restore"),
        recovery["roots"]["restored"],
        discardable=True,
    )


def test_real_backup_restore_login_queries_photos_history_and_revocation(recovery):
    started = monotonic()
    published = point(recovery)
    backup_elapsed = monotonic() - started
    with verified_package(
        published / "manifest.json", recovery["key"], recovery["roots"]["scratch"]
    ) as (_, manifest):
        assert manifest["database"]["tables"]["quotations"]["count"] == 1
        assert manifest["database"]["tables"]["catalog_history"]["count"] == 3
        assert manifest["database"]["tables"]["customers"]["count"] == 1
    # Independent-directory copy is explicitly a local off-host simulation.
    copied = copy_recovery_point(
        published / "manifest.json", recovery["roots"]["offhost"]
    )
    target = recovery["database"]("restore")
    result = recover(recovery, copied / "manifest.json", target)
    engine = build_engine(target)
    try:
        auth = AuthService(build_session_factory(engine), recovery["auth"].settings)
        with pytest.raises(AuthError):
            auth.identity(recovery["session_token"])
        with pytest.raises(AuthError):
            auth.set_password(
                recovery["pending"], "different synthetic passphrase", "loopback"
            )
        fresh, identity = auth.login(
            "synthetic-quotation@example.invalid", recovery["password"], "loopback"
        )
        assert auth.identity(fresh).user_id == identity.user_id
        service = QuotationService(build_session_factory(engine))
        restored = service.get(recovery["quote"]["id"])
        assert restored["customer_id"] == recovery["quote"]["customer_id"]
        assert restored["total"] == recovery["quote"]["total"]
        assert len(service.versions(recovery["quote"]["id"])) == 1
        photos = recovery["roots"]["photos"]
        destination = recovery["roots"]["restored"]
        assert {p.name: p.read_bytes() for p in photos.iterdir()} == {
            p.name: p.read_bytes() for p in destination.iterdir()
        }
        with engine.connect() as db:
            assert (
                db.scalar(
                    text("SELECT count(*) FROM auth_sessions WHERE revoked_at IS NULL")
                )
                == 1
            )
            assert (
                db.scalar(
                    text("SELECT count(*) FROM password_links WHERE revoked_at IS NULL")
                )
                == 0
            )
        print(
            json.dumps(
                {
                    "ops02": result,
                    "backup_seconds": round(backup_elapsed, 3),
                    "encrypted_bytes": (published / "package.tar.age").stat().st_size,
                    "private_file_bytes": sum(
                        p.stat().st_size for p in photos.iterdir()
                    ),
                }
            )
        )
    finally:
        engine.dispose()


def test_wrong_key_corruption_missing_photo_and_midway_failure_no_publish(recovery):
    published = point(recovery)
    with recovery["engine"].connect() as db:
        before = database_manifest(db)
    wrong = recovery["roots"]["scratch"] / "wrong.txt"
    run(["age-keygen", "-o", str(wrong)])
    os.chmod(wrong, 0o600)
    with (
        pytest.raises(OperationsError),
        verified_package(
            published / "manifest.json", wrong, recovery["roots"]["scratch"]
        ),
    ):
        pass
    encrypted = published / "package.tar.age"
    original = encrypted.read_bytes()
    encrypted.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    with (
        pytest.raises(OperationsError),
        verified_package(
            published / "manifest.json", recovery["key"], recovery["roots"]["scratch"]
        ),
    ):
        pass
    encrypted.write_bytes(original)
    photo = next(recovery["roots"]["photos"].iterdir())
    photo_bytes = photo.read_bytes()
    photo.unlink()
    with pytest.raises(CatalogError):
        point(recovery)
    photo.write_bytes(photo_bytes)
    os.chmod(photo, 0o600)
    with patch(
        "infra.operations.backup.run", side_effect=OperationsError("synthetic failure")
    ):
        with pytest.raises(OperationsError):
            point(recovery)
    assert list(recovery["roots"]["backups"].iterdir()) == [published]
    with recovery["engine"].connect() as db:
        assert before == database_manifest(db)


def test_backup_drains_real_upload_before_database_and_file_snapshot(recovery):
    written = Event()
    release = Event()
    storage = recovery["catalog"].storage
    original = storage.write

    def paused_write(data, image_format):
        stored = original(data, image_format)
        written.set()
        assert release.wait(10)
        return stored

    with (
        patch.object(storage, "write", side_effect=paused_write),
        ThreadPoolExecutor(2) as pool,
    ):
        upload = pool.submit(
            recovery["catalog"].upload_photo,
            recovery["ids"]["arch"],
            4,
            synthetic_image(size=(11, 11)),
            "image/png",
            recovery["actor"],
        )
        # Use the existing audit identity rather than inventing another actor.
        assert written.wait(5)
        pending = pool.submit(point, recovery)
        deadline = monotonic() + 5
        try:
            while monotonic() < deadline:
                if pending.done():
                    pending.result()
                    pytest.fail("backup did not drain upload")
                try:
                    with active_operation(recovery["roots"]["barrier"]):
                        pass
                except OperationsError:
                    break
                sleep(0.01)
            else:
                pytest.fail("backup did not block new writes")
            assert not upload.done() and not pending.done()
        finally:
            release.set()
        assert upload.result(timeout=10)["version"] == 5
        published = pending.result(timeout=10)
    with verified_package(
        published / "manifest.json", recovery["key"], recovery["roots"]["scratch"]
    ) as (_, manifest):
        assert len(manifest["database"]["photos"]) == 3
        assert (
            len([name for name in manifest["members"] if name.startswith("files/")])
            == 3
        )
    assert backup_status(recovery["roots"]["backups"])["status"] == "ok"


def test_nonempty_target_and_unapproved_target_refused_source_untouched(recovery):
    published = point(recovery)
    with recovery["engine"].connect() as db:
        before = database_manifest(db)
    with pytest.raises(OperationsError):
        recover(recovery, published / "manifest.json", recovery["source"])
    target = recovery["database"]("restore")
    engine = create_engine(target.url)
    with engine.begin() as db:
        db.execute(text("CREATE TABLE sentinel (id int)"))
    engine.dispose()
    with pytest.raises(OperationsError):
        recover(recovery, published / "manifest.json", target)
    marker = recovery["roots"]["restored"] / "sentinel"
    marker.write_bytes(b"synthetic")
    with pytest.raises(OperationsError):
        recover(recovery, published / "manifest.json")
    assert marker.read_bytes() == b"synthetic"
    with recovery["engine"].connect() as db:
        assert before == database_manifest(db)


def test_ready_real_schema_storage_database_and_maintenance(recovery, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", recovery["source"].url.render_as_string(hide_password=False)
    )
    monkeypatch.setenv("STORAGE_ROOT", str(recovery["roots"]["photos"]))
    with TestClient(app) as client:
        assert client.get("/ready").json() == {"status": "ready"}
        monkeypatch.setenv("STORAGE_ROOT", str(recovery["roots"]["photos"] / "missing"))
        assert client.get("/ready").status_code == 503
        monkeypatch.setenv("STORAGE_ROOT", str(recovery["roots"]["photos"]))
        with maintenance(recovery["roots"]["barrier"]):
            assert client.post("/customers", json={}).status_code == 503
            assert client.get("/ready").status_code == 503
            assert client.get("/health").status_code == 200
        with recovery["engine"].begin() as db:
            db.execute(text("UPDATE alembic_version SET version_num='0005_customers'"))
        assert client.get("/ready").status_code == 503
        monkeypatch.setenv(
            "DATABASE_URL",
            recovery["source"].url.set(port=1).render_as_string(hide_password=False),
        )
        assert client.get("/ready").status_code == 503


def test_ready_unusable_private_storage_fail_closed_and_recovers(recovery, monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", recovery["source"].url.render_as_string(hide_password=False)
    )
    monkeypatch.setenv("STORAGE_ROOT", str(recovery["roots"]["photos"]))
    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        original_access = os.access

        def storage_access(path, mode):
            if Path(path) == recovery["roots"]["photos"]:
                return False
            return original_access(path, mode)

        with patch(
            "rentalops_api.catalog_storage.os.access", side_effect=storage_access
        ):
            response = client.get("/ready")
            assert response.status_code == 503
            assert response.json() == {"status": "unavailable"}
            assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200


def test_backup_missing_and_older_than_24h_alert(recovery):
    assert backup_status(recovery["roots"]["backups"])["status"] == "alert"
    published = point(recovery)
    receipt = published / "manifest.json"
    value = json.loads(receipt.read_text())
    value["created_at"] = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    receipt.write_text(json.dumps(value))
    assert backup_status(recovery["roots"]["backups"])["status"] == "alert"


def test_authenticated_incomplete_manifest_and_missing_photo_refused(recovery):
    import tarfile

    published = point(recovery)
    with verified_package(
        published / "manifest.json", recovery["key"], recovery["roots"]["scratch"]
    ) as (root, authenticated):
        # Still a valid encrypted package; authenticated manifest omits the dump.
        authenticated["members"].pop("database.dump")
        (root / "manifest.json").write_text(json.dumps(authenticated))
        archive = root / "incomplete.tar"
        with tarfile.open(archive, "w") as package:
            for name in ("manifest.json", "database.dump", *authenticated["members"]):
                package.add(root / name, arcname=name)
        encrypted = published / "package.tar.age"
        encrypted.unlink()  # Only this fixture's synthetic recovery point.
        run(
            [
                "age",
                "-R",
                str(recovery["recipients"]),
                "-o",
                str(encrypted),
                str(archive),
            ]
        )
        os.chmod(encrypted, 0o600)
        from infra.operations.backup import digest

        receipt = published / "manifest.json"
        value = json.loads(receipt.read_text())
        value["ciphertext_sha256"] = digest(encrypted)
        receipt.write_text(json.dumps(value))
    with pytest.raises(OperationsError):
        recover(recovery, published / "manifest.json")
    assert list(recovery["roots"]["restored"].iterdir()) == []


def test_actual_nginx_backend_logs_redact_private_data(recovery, tmp_path):
    executable = os.environ.get("TEST_NGINX_BINARY") or shutil.which("nginx")
    if not executable:
        pytest.fail("TEST_NGINX_BINARY or nginx required for actual proxy verification")
    repository = Path(__file__).resolve().parents[3]
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        "<!doctype html><title>Synthetic proxy fixture</title>"
    )
    (tmp_path / "temp").mkdir()
    (tmp_path / "logs").mkdir()
    operations = repository / "infra/operations"
    # Allocate isolated loopback ports; reserve no existing server/service.
    import socket

    ports = []
    for _ in range(2):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            ports.append(sock.getsockname()[1])
    api_port, proxy_port = ports
    backend_log = tmp_path / "backend.jsonl"
    proxy_log = tmp_path / "proxy.jsonl"
    nginx_root = Path(executable).parent
    config = (operations / "nginx.conf").read_text()
    replacements = {
        "/etc/nginx/mime.types": f'"{(nginx_root / "conf/mime.types").as_posix()}"',
        "/tmp/nginx.pid": f'"{(tmp_path / "nginx.pid").as_posix()}"',
        "/dev/null": "nul" if os.name == "nt" else "/dev/null",
        "/dev/stdout": f'"{proxy_log.as_posix()}"',
        "/tmp/client-body": f'"{(tmp_path / "client-body").as_posix()}"',
        "/tmp/proxy": f'"{(tmp_path / "proxy").as_posix()}"',
        "/usr/share/nginx/html": f'"{static.as_posix()}"',
        "listen 8080": f"listen 127.0.0.1:{proxy_port}",
        "http://backend:8000/": f"http://127.0.0.1:{api_port}/",
        "worker_processes auto": "worker_processes 1",
    }
    for before, after in replacements.items():
        config = config.replace(before, after)
    proxy_config = tmp_path / "nginx.conf"
    proxy_config.write_text(config)
    env = dict(os.environ)
    env.update(
        {
            "DATABASE_URL": recovery["source"].url.render_as_string(
                hide_password=False
            ),
            "STORAGE_ROOT": str(recovery["roots"]["photos"]),
            "AUTH_ORIGIN": f"http://127.0.0.1:{proxy_port}",
            "AUTH_RATE_KEY": "synthetic-proxy-rate-key" * 3,
        }
    )
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with backend_log.open("wb") as log:
        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "rentalops_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
                "--no-access-log",
                "--no-proxy-headers",
                "--log-config",
                str(operations / "logging.json"),
            ],
            env=env,
            stdout=log,
            stderr=log,
            creationflags=flags,
        )
        proxy = None
        try:
            deadline = monotonic() + 15
            while monotonic() < deadline:
                try:
                    if (
                        httpx.get(f"http://127.0.0.1:{api_port}/health").status_code
                        == 200
                    ):
                        break
                except httpx.TransportError:
                    sleep(0.1)
            else:
                pytest.fail("isolated backend did not start")
            prefix = tmp_path.as_posix() + "/"
            subprocess.run(
                [executable, "-p", prefix, "-c", str(proxy_config), "-t"],
                check=True,
                capture_output=True,
                creationflags=flags,
            )
            proxy = subprocess.Popen(
                [executable, "-p", prefix, "-c", str(proxy_config)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
            sentinel = "SYNTHETIC_PRIVATE_SENTINEL"
            deadline = monotonic() + 10
            while monotonic() < deadline:
                try:
                    response = httpx.get(f"http://127.0.0.1:{proxy_port}/api/ready")
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    sleep(0.1)
            else:
                pytest.fail("isolated proxy did not start")
            base = f"http://127.0.0.1:{proxy_port}"
            assert httpx.get(base + "/").status_code == 200
            response = httpx.post(
                base + f"/api/auth/password/set?token={sentinel}",
                json={"token": sentinel, "password": sentinel},
                headers={
                    "Cookie": sentinel,
                    "Referer": sentinel,
                    "Authorization": sentinel,
                },
            )
            assert response.status_code in {403, 422}
            assert httpx.get(base + f"/api/photos/{sentinel}").status_code in {401, 422}
        finally:
            if proxy is not None:
                subprocess.run(
                    [
                        executable,
                        "-p",
                        tmp_path.as_posix() + "/",
                        "-c",
                        str(proxy_config),
                        "-s",
                        "quit",
                    ],
                    check=True,
                    capture_output=True,
                    creationflags=flags,
                )
                proxy.wait(timeout=10)
            backend.terminate()
            backend.wait(timeout=10)
    for path in (backend_log, proxy_log):
        records = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(records) >= 2
        assert "SYNTHETIC_PRIVATE_SENTINEL" not in path.read_text()
        assert (
            "postgresql" not in path.read_text()
            and str(tmp_path) not in path.read_text()
        )
