from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from rentalops_api.config import DatabaseConfigurationError
from rentalops_api.main import app


@pytest.mark.parametrize("url", ["", "malformed-password", "sqlite:///private.db"])
def test_real_missing_or_malformed_configuration_returns_generic_503(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "error",
    [
        DatabaseConfigurationError(
            "postgresql://synthetic:password@localhost/database"
        ),
        OperationalError(
            "SELECT secret",
            {},
            Exception("postgresql://synthetic:password@localhost/database"),
        ),
    ],
)
def test_health_survives_database_failure_and_readiness_redacts(error, caplog):
    with patch(
        "rentalops_api.main.DatabaseSettings.from_environment", side_effect=error
    ):
        with TestClient(app) as client:
            live = client.get("/health")
            ready = client.get("/health/ready")
    assert live.status_code == 200
    assert live.json() == {"status": "ok", "service": "rentalops-api"}
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable"}
    assert all(
        secret not in ready.text + caplog.text
        for secret in ["password", "postgresql", "SELECT", "Traceback"]
    )
