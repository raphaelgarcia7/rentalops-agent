"""Small synchronous SQLAlchemy boundary with explicit transaction ownership."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from rentalops_api.config import DatabaseSettings
from rentalops_api.operations import active_operation


def build_engine(settings: DatabaseSettings) -> Engine:
    engine = create_engine(
        settings.url,
        echo=False,
        echo_pool=False,
        hide_parameters=True,
        pool_pre_ping=True,
        pool_timeout=3,
        connect_args={
            "connect_timeout": 3,
            "options": "-c timezone=UTC -c statement_timeout=3000",
        },
    )

    @event.listens_for(engine, "checkout")
    def guard_connection(
        dbapi_connection: object, record: ConnectionPoolEntry, proxy: object
    ) -> None:
        guard = active_operation()
        guard.__enter__()
        # The ConnectionPoolEntry owns this guard until transaction/connection close.
        record.info["operations_guard"] = guard

    @event.listens_for(engine, "checkin")
    def release_connection(
        dbapi_connection: object, record: ConnectionPoolEntry
    ) -> None:
        guard = record.info.pop("operations_guard", None)
        if guard is not None:
            guard.__exit__(None, None, None)

    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Caller commits explicitly; exceptions roll back and every exit closes."""
    session = factory()
    try:
        yield session
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
