import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from rentalops_api.config import (
    DatabaseConfigurationError,
    DatabaseSettings,
    environment_values,
)
from rentalops_api.database import build_engine
from rentalops_api.models import User

from ..database_safety import new_schema_name, validated_schema
from ..database_safety import test_settings as safe_settings

TEST_URL = "postgresql+psycopg://synthetic:synthetic@127.0.0.1/rentalops_test"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "bad-secret",
        "sqlite:///test.db",
        "mysql://user:password@localhost/test",
        "postgresql://user:password@localhost:bad/test",
    ],
)
def test_configuration_rejects_invalid_urls_without_disclosure(value):
    with pytest.raises(DatabaseConfigurationError) as error:
        DatabaseSettings.from_url(value)
    assert "password" not in str(error.value)
    assert "bad-secret" not in str(error.value)


def test_environment_overrides_root_dotenv(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=from-file\nTEST_DATABASE_URL=test-file\n", encoding="utf-8"
    )
    values = environment_values(env_file, {"DATABASE_URL": "explicit"})
    assert values["DATABASE_URL"] == "explicit"
    assert values["TEST_DATABASE_URL"] == "test-file"
    assert environment_values(env_file, {"DATABASE_URL": ""})["DATABASE_URL"] == ""


def test_settings_repr_and_engine_do_not_expose_credentials_or_enable_echo(monkeypatch):
    monkeypatch.setenv("SQLALCHEMY_ECHO", "true")
    settings = DatabaseSettings.from_url(TEST_URL)
    assert "synthetic" not in repr(settings)
    with patch("psycopg.connect", side_effect=AssertionError("unexpected connection")):
        engine = build_engine(settings)
        assert engine.echo is False
        assert engine.pool.echo is False
        assert engine.hide_parameters is True
        engine.dispose()


def test_imports_neither_connect_nor_migrate():
    code = """
from unittest.mock import patch
with patch('psycopg.connect', side_effect=AssertionError('connection')), \\
     patch('sqlalchemy.create_engine', side_effect=AssertionError('engine')), \\
     patch('alembic.command.upgrade', side_effect=AssertionError('DDL')):
    import rentalops_api.config
    import rentalops_api.database
    import rentalops_api.models
    import rentalops_api.main
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "test_url,development",
    [
        (None, None),
        ("sqlite:///rentalops_test", None),
        ("postgresql://user:password@remote.example/rentalops_test", None),
        ("postgresql://user:password@127.0.0.2/rentalops_test", None),
        ("postgresql://user:password@localhost/rentalops", None),
        ("postgresql://user:password@localhost/contest", None),
        (TEST_URL + "?host=remote.example", None),
        (TEST_URL + "?service=production", None),
        (TEST_URL, "postgresql://other:other@localhost:5432/rentalops_test"),
        (TEST_URL, "postgresql://other:other@[::1]:5432/rentalops_test"),
        (TEST_URL, "postgresql://other:other@localhost/development?host=remote"),
    ],
)
def test_unsafe_integration_targets_fail_before_connection(test_url, development):
    with patch("psycopg.connect", side_effect=AssertionError("unsafe connection")):
        with pytest.raises(DatabaseConfigurationError) as error:
            safe_settings(test_url, development)
        assert "password" not in str(error.value)


def test_safe_target_and_namespace_validation():
    settings = safe_settings(TEST_URL, "postgresql://user:password@localhost/rentalops")
    assert settings.url.host == "127.0.0.1"
    assert settings.url.query["hostaddr"] == "127.0.0.1"
    assert settings.url.port == 5432
    assert validated_schema(new_schema_name()).startswith("rentalops_test_")
    for unsafe in [
        "public",
        "rentalops_test_",
        "rentalops_test_" + "a" * 32 + "; DROP SCHEMA public",
    ]:
        with pytest.raises(ValueError):
            validated_schema(unsafe)


@pytest.mark.parametrize("value", ["", " ", "a" * 321])
def test_invalid_email(value):
    with pytest.raises(ValueError):
        User(email=value)


def test_email_normalization_and_limit():
    assert User(email="  TEAM@EXAMPLE.INVALID\t").email == "team@example.invalid"
    assert len(User(email="A" * 320).email) == 320
