from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import UUID

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from rentalops_api.config import DatabaseSettings, environment_values
from rentalops_api.database import build_engine, build_session_factory, session_scope
from rentalops_api.main import app
from rentalops_api.models import User

from ..conftest import migration_config
from ..database_safety import new_schema_name, validated_schema
from ..database_safety import test_settings as safe_settings

pytestmark = pytest.mark.integration


def test_libpq_environment_cannot_redirect_validated_target(monkeypatch):
    values = environment_values()
    settings = safe_settings(
        values.get("TEST_DATABASE_URL"), values.get("DATABASE_URL")
    )
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.1")
    monkeypatch.setenv("PGPORT", "1")
    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            assert str(connection.scalar(text("SELECT inet_server_addr()"))) in {
                "127.0.0.1",
                "::1",
            }
            assert (
                connection.scalar(text("SELECT current_database()"))
                == settings.url.database
            )
    finally:
        engine.dispose()


def test_migration_does_not_touch_another_namespace(isolated_engine: Engine):
    sibling = validated_schema(new_schema_name())
    with isolated_engine.begin() as connection:
        public_tables = inspect(connection).get_table_names(schema="public")
        connection.execute(text(f'CREATE SCHEMA "{sibling}"'))
        try:
            connection.execute(text(f'CREATE TABLE "{sibling}".sentinel (value text)'))
            connection.execute(
                text(f"INSERT INTO \"{sibling}\".sentinel VALUES ('synthetic')")
            )
            command.upgrade(migration_config(connection), "head")
            command.downgrade(migration_config(connection), "base")
            assert (
                connection.scalar(text(f'SELECT value FROM "{sibling}".sentinel'))
                == "synthetic"
            )
            assert inspect(connection).get_table_names(schema="public") == public_tables
        finally:
            connection.execute(
                text(f'DROP SCHEMA "{validated_schema(sibling)}" CASCADE')
            )


def test_caller_can_recover_same_session_with_explicit_rollback(
    migrated_engine: Engine,
):
    with session_scope(build_session_factory(migrated_engine)) as session:
        session.add(User(email="before@example.invalid"))
        session.commit()
        with pytest.raises(IntegrityError):
            session.add(User(email="before@example.invalid"))
            session.commit()
        session.rollback()
        session.add(User(email="after@example.invalid"))
        session.commit()
        assert len(session.scalars(select(User)).all()) == 2


def test_migrations_idempotent_and_disposable_downgrade(isolated_engine: Engine):
    with isolated_engine.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) == {
            "users",
            "alembic_version",
            "auth_sessions",
            "password_links",
            "login_failures",
            "auth_audit",
            "password_set_attempts",
            "products",
            "kits",
            "kit_items",
            "catalog_history",
            "stock_movements",
            "maintenance_entries",
            "product_photos",
        }
        assert connection.scalar(text("SELECT count(*) FROM users")) == 0
        connection.execute(
            text("INSERT INTO users(email) VALUES ('migration@example.invalid')")
        )
        identifier = connection.scalar(text("SELECT id FROM users"))
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT id FROM users")) == identifier
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0004_catalog"
        )
        command.downgrade(config, "base")
        assert "users" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT count(*) FROM users")) == 0


def test_identity_persists_uuid_utc_normalized_email_and_updated_time(
    migrated_engine: Engine,
):
    factory = build_session_factory(migrated_engine)
    with session_scope(factory) as session:
        user = User(email="  TEAM@EXAMPLE.INVALID ")
        session.add(user)
        session.commit()
        session.refresh(user)
        identifier, created, updated = user.id, user.created_at, user.updated_at
        assert isinstance(identifier, UUID)
        assert user.email == "team@example.invalid"
        assert user.is_active is True
        assert created.utcoffset() == updated.utcoffset() == timedelta(0)
    with session_scope(factory) as session:
        stored = session.get(User, identifier)
        assert stored is not None
        stored.is_active = False
        session.commit()
        session.refresh(stored)
        assert stored.id == identifier and stored.created_at == created
        assert stored.updated_at > updated
        assert stored.updated_at.utcoffset() == timedelta(0)
        assert stored.is_active is False


def test_database_normalizes_direct_sql_and_enforces_constraints(
    migrated_engine: Engine,
):
    with migrated_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users(email) VALUES (:email)"),
            {"email": "\t SQL@EXAMPLE.INVALID \n"},
        )
        assert (
            connection.scalar(text("SELECT email FROM users")) == "sql@example.invalid"
        )
    for email in ["sql@example.invalid", " SQL@EXAMPLE.INVALID ", "", " \t ", None]:
        with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO users(email) VALUES (:email)"), {"email": email}
            )
    with pytest.raises(DataError), migrated_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users(email) VALUES (:email)"), {"email": "a" * 321}
        )
    with migrated_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users(email) VALUES (:email)"), {"email": "a" * 320}
        )
        assert connection.scalar(text("SELECT count(*) FROM users")) == 2


def test_concurrent_duplicate_has_exactly_one_commit(migrated_engine: Engine):
    factory = build_session_factory(migrated_engine)
    barrier = Barrier(2)

    def insert(email: str) -> str:
        try:
            with session_scope(factory) as session:
                session.add(User(email=email))
                barrier.wait(timeout=10)
                session.commit()
            return "committed"
        except IntegrityError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(insert, ["race@example.invalid", " RACE@EXAMPLE.INVALID "])
        )
    assert sorted(outcomes) == ["committed", "rejected"]
    with session_scope(factory) as session:
        assert len(session.scalars(select(User)).all()) == 1


def test_failed_transaction_rolls_back_closes_and_next_operation_succeeds(
    migrated_engine: Engine,
):
    factory = build_session_factory(migrated_engine)
    with session_scope(factory) as session:
        session.add(User(email="existing@example.invalid"))
        session.commit()
    original_close = Session.close
    with patch.object(
        Session, "close", autospec=True, side_effect=original_close
    ) as close:
        with pytest.raises(IntegrityError), session_scope(factory) as session:
            session.add_all(
                [
                    User(email="partial@example.invalid"),
                    User(email="existing@example.invalid"),
                ]
            )
            session.commit()
        close.assert_called_once()
    with session_scope(factory) as session:
        assert [user.email for user in session.scalars(select(User)).all()] == [
            "existing@example.invalid"
        ]
        session.add(User(email="recovered@example.invalid"))
        session.commit()
    assert migrated_engine.pool.checkedout() == 0


def test_uncommitted_exit_does_not_persist(migrated_engine: Engine):
    factory = build_session_factory(migrated_engine)
    with session_scope(factory) as session:
        session.add(User(email="uncommitted@example.invalid"))
        session.flush()
    with session_scope(factory) as session:
        assert session.scalars(select(User)).all() == []
    assert migrated_engine.pool.checkedout() == 0


def test_real_readiness_and_database_outage(migrated_engine: Engine, caplog):
    settings = DatabaseSettings(migrated_engine.url)
    with patch(
        "rentalops_api.main.DatabaseSettings.from_environment", return_value=settings
    ):
        with TestClient(app) as client:
            assert client.get("/health/ready").json() == {"status": "ready"}
            assert client.get("/health/ready").status_code == 200
    unreachable = DatabaseSettings(settings.url.set(port=1))
    with patch(
        "rentalops_api.main.DatabaseSettings.from_environment", return_value=unreachable
    ):
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            response = client.get("/health/ready")
            assert response.status_code == 503
            assert response.json() == {"status": "unavailable"}
    assert "SELECT" not in caplog.text and "postgresql" not in caplog.text
