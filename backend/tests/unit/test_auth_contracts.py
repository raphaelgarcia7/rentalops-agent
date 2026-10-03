import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from rentalops_api.auth import AuthSettings, normalize_email, validate_password
from rentalops_api.auth_routes import LoginPayload, PasswordPayload, auth_service
from rentalops_api.main import app


def test_passphrases_email_and_secret_representations():
    assert normalize_email(" PERSON@EXAMPLE.INVALID ") == "person@example.invalid"
    assert validate_password("a long pass phrase") == "a long pass phrase"
    for length in (12, 128):
        assert validate_password("x" * length) == "x" * length
    for length in (0, 11, 129):
        with pytest.raises(ValueError):
            validate_password("x" * length)
    for email in ("", "a@", "@example.invalid", "a b@example.invalid", "a@b@c"):
        with pytest.raises(ValueError):
            normalize_email(email)
    assert "synthetic secret" not in repr(
        LoginPayload(email="person@example.invalid", password="synthetic secret")
    )
    assert "private-token" not in repr(
        PasswordPayload(token="private-token", password="synthetic secret")
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"AUTH_ORIGIN": ""},
        {"AUTH_RATE_KEY": "short"},
        {"APP_ENV": "production", "AUTH_ORIGIN": "http://localhost:5173"},
        {"AUTH_ORIGIN": "https://example.invalid/path"},
        {"AUTH_ORIGIN": "http://example.invalid"},
        {"AUTH_ORIGIN": "https://user:secret@example.invalid"},
        {"AUTH_ORIGIN": "https://example.invalid?x=1"},
        {"AUTH_ORIGIN": "https://example.invalid:99999"},
        {"APP_ENV": "typo"},
    ],
)
def test_insecure_configuration_is_rejected(changes):
    values = {"AUTH_ORIGIN": "http://localhost:5173", "AUTH_RATE_KEY": "x" * 32}
    with pytest.raises(ValueError, match="configuration"):
        AuthSettings.from_values(values | changes)


def test_production_cookie_and_configuration_repr():
    settings = AuthSettings.from_values(
        {
            "APP_ENV": "production",
            "AUTH_ORIGIN": "https://rentalops.example.invalid",
            "AUTH_RATE_KEY": "x" * 32,
        }
    )
    assert settings.secure_cookie
    assert "x" * 32 not in repr(settings)


def test_validation_and_backend_failure_never_echo_inputs_or_sql(caplog):
    def failing_service():
        raise OperationalError("SECRET SQL", {}, Exception("private-secret"))

    app.dependency_overrides[auth_service] = failing_service
    try:
        with TestClient(app) as client:
            response = client.get("/auth/session")
            assert response.status_code == 503
            assert response.json() == {"detail": "Serviço indisponível."}
    finally:
        app.dependency_overrides.clear()
    assert "SECRET SQL" not in caplog.text
    assert "private-secret" not in caplog.text


def test_insecure_production_auth_fails_closed_without_breaking_health(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("AUTH_RATE_KEY", "synthetic-key" * 4)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/auth/session")
        assert response.status_code == 503
        assert response.json() == {"detail": "Serviço indisponível."}
        assert "synthetic-key" not in response.text
