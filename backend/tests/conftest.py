from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, event, text
from sqlalchemy.engine import Connection

from rentalops_api.config import environment_values
from rentalops_api.database import build_engine

from .database_safety import new_schema_name, test_settings, validated_schema


def migration_config(connection: Connection) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def isolated_engine() -> Iterator[Engine]:
    values = environment_values()
    # Validation precedes build_engine, connect, DDL and teardown.
    settings = test_settings(
        values.get("TEST_DATABASE_URL"), values.get("DATABASE_URL")
    )
    namespace = validated_schema(new_schema_name())
    administrator = build_engine(settings)
    engine = build_engine(settings)
    created = False
    try:
        with administrator.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{namespace}"'))
        created = True

        @event.listens_for(engine, "connect")
        def set_namespace(dbapi_connection, connection_record):
            # Session-level SET in autocommit survives transaction rollbacks.
            previous = dbapi_connection.autocommit
            dbapi_connection.autocommit = True
            with dbapi_connection.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{namespace}"')
            dbapi_connection.autocommit = previous

        yield engine
    finally:
        engine.dispose()
        if created:
            with administrator.begin() as connection:
                connection.execute(
                    text(f'DROP SCHEMA "{validated_schema(namespace)}" CASCADE')
                )
        administrator.dispose()


@pytest.fixture
def migrated_engine(isolated_engine: Engine) -> Engine:
    with isolated_engine.begin() as connection:
        command.upgrade(migration_config(connection), "head")
    return isolated_engine
