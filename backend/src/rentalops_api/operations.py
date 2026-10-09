"""Single-host maintenance barrier and private filesystem checks."""

import importlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import portalocker

from rentalops_api.config import environment_values

active_depth: ContextVar[int] = ContextVar("operations_depth", default=0)


class OperationsError(ValueError):
    """Controlled operational failure, without paths or infrastructure details."""


def private_path(path: Path, *, directory: bool = True) -> Path:
    try:
        if not path.is_absolute() or path.resolve() != path:
            raise OSError
        for ancestor in (path, *path.parents):
            if ancestor.is_symlink() or ancestor.is_junction():
                raise OSError
            if (ancestor / ".git").exists():
                raise OSError
        if directory and not path.is_dir():
            raise OSError
        if not directory and not stat.S_ISREG(path.lstat().st_mode):
            raise OSError
        if os.name == "nt":
            security = importlib.import_module("win32security")
            acl = security.GetFileSecurity(
                str(path), security.DACL_SECURITY_INFORMATION
            ).GetSecurityDescriptorDacl()
            if acl is None:
                raise OSError
            for index in range(acl.GetAceCount()):
                ace = acl.GetAce(index)
                if (
                    ace[0][0] == security.ACCESS_ALLOWED_ACE_TYPE
                    and ace[1]
                    and security.ConvertSidToStringSid(ace[2])
                    in {"S-1-1-0", "S-1-5-7", "S-1-5-11", "S-1-5-32-545"}
                ):
                    raise OSError
        elif path.stat().st_mode & 0o077:
            raise OSError
        return path
    except Exception:
        raise OperationsError("Private filesystem unavailable.") from None


def operation_root() -> Path | None:
    values = environment_values()
    value = values.get("OPERATIONS_ROOT")
    if not value:
        if values.get("APP_ENV") == "production":
            raise OperationsError("Maintenance configuration required.")
        return None  # Existing local development remains usable.
    return private_path(Path(value))


def lock_path(root: Path, name: str) -> Path:
    path = root / name
    if path.exists() or path.is_symlink() or path.is_junction():
        private_path(path, directory=False)
    else:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    return path


@contextmanager
def active_operation(root: Path | None = None) -> Iterator[None]:
    if active_depth.get():
        yield
        return
    root = root or operation_root()
    if root is None:
        yield
        return
    private_path(root)
    try:
        # Lock intent first: backup acquires this exclusively before draining.
        # New operations fail instead of queuing indefinitely behind maintenance.
        intent = portalocker.Lock(
            lock_path(root, "intent.lock"),
            mode="a+b",
            timeout=0,
            flags=portalocker.LOCK_SH | portalocker.LOCK_NB,
        )
        with intent:
            active = portalocker.Lock(
                lock_path(root, "active.lock"),
                mode="a+b",
                timeout=0,
                flags=portalocker.LOCK_SH | portalocker.LOCK_NB,
            )
            active.acquire()
        try:
            token = active_depth.set(active_depth.get() + 1)
            yield
        finally:
            active_depth.reset(token)
            active.release()
    except portalocker.exceptions.LockException, OSError:
        raise OperationsError("Maintenance in progress. Try again later.") from None


@contextmanager
def maintenance(root: Path, timeout: float = 60) -> Iterator[None]:
    private_path(root)
    try:
        with portalocker.Lock(
            lock_path(root, "intent.lock"),
            mode="a+b",
            timeout=timeout,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        ):
            with portalocker.Lock(
                lock_path(root, "active.lock"),
                mode="a+b",
                timeout=timeout,
                flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
            ):
                yield
    except portalocker.exceptions.LockException, OSError:
        raise OperationsError(
            "Maintenance could not drain active operations."
        ) from None
