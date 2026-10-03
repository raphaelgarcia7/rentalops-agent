"""Keep the real-browser harness fail-closed for personal data in access logs."""

import runpy
from pathlib import Path
from unittest.mock import patch


def test_browser_server_disables_access_logs_and_untrusted_proxy_headers(monkeypatch):
    # Exercise the actual entry point without starting a server or opening a DB.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))
    with patch("uvicorn.run") as run:
        runpy.run_module("backend.tests.browser_server", run_name="__main__")
    run.assert_called_once()
    assert run.call_args.kwargs == {
        "host": "127.0.0.1",
        "port": 8000,
        "access_log": False,
        "proxy_headers": False,
        "log_level": "warning",
    }
