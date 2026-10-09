import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from rentalops_api.main import app
from rentalops_api.operations import (
    OperationsError,
    active_depth,
    active_operation,
    maintenance,
    private_path,
)


def test_barrier_drains_existing_operations_and_refuses_new_writes(tmp_path):
    assert active_depth.get() == 0
    started = Event()
    release = Event()
    maintenance_started = Event()

    def operation():
        with active_operation(tmp_path):
            started.set()
            assert release.wait(5)
            # Existing operation may continue nested work while intent is locked.
            with active_operation(tmp_path):
                pass

    def backup():
        with maintenance(tmp_path, timeout=5):
            maintenance_started.set()

    with ThreadPoolExecutor(2) as pool:
        current = pool.submit(operation)
        assert started.wait(5)
        future = pool.submit(backup)
        # Observe the actual intent barrier; no arbitrary sleep decides success.
        deadline = monotonic() + 4
        while monotonic() < deadline:
            if future.done():
                release.set()
                future.result()
            try:
                with active_operation(tmp_path):
                    pass
            except OperationsError:
                break
            sleep(0.01)
        else:
            release.set()
            pytest.fail("maintenance never blocked new operations")
        assert not maintenance_started.is_set()
        release.set()
        current.result(timeout=5)
        future.result(timeout=5)
        assert maintenance_started.is_set()


def test_public_permissions_fail_closed(tmp_path):
    if os.name != "nt":
        tmp_path.chmod(0o755)
        with pytest.raises(OperationsError):
            private_path(tmp_path)
        tmp_path.chmod(0o700)
    else:
        import subprocess

        subprocess.run(
            ["icacls", str(tmp_path), "/grant", "*S-1-1-0:(R)"],
            check=True,
            capture_output=True,
        )
        try:
            with pytest.raises(OperationsError):
                private_path(tmp_path)
        finally:
            subprocess.run(
                ["icacls", str(tmp_path), "/remove:g", "*S-1-1-0"],
                check=True,
                capture_output=True,
            )


def test_structured_log_redaction_body_query_headers_paths(caplog):
    caplog.set_level(logging.INFO, logger="rentalops.operations")
    sentinel = "SYNTHETIC_PRIVATE_SENTINEL"
    with TestClient(app) as client:
        for path in ("/health", f"/photos/{sentinel}", "/auth/password/set"):
            client.post(
                path + f"?token={sentinel}",
                json={"password": sentinel, "token": sentinel},
                headers={
                    "Cookie": sentinel,
                    "Authorization": sentinel,
                    "Referer": sentinel,
                    "X-Request-ID": sentinel,
                },
            )
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "rentalops.operations"
    ]
    assert len(records) == 3 and sentinel not in json.dumps(records)
    assert all(
        set(record)
        == {"request_id", "operation", "duration_ms", "code", "error_category"}
        for record in records
    )


def test_production_requires_shared_barrier(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("OPERATIONS_ROOT", raising=False)
    with patch(
        "rentalops_api.operations.environment_values",
        return_value={"APP_ENV": "production"},
    ):
        with pytest.raises(OperationsError), active_operation():
            pass
