"""Small synchronous SQLAlchemy boundary with explicit transaction ownership."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from rentalops_api.config import DatabaseSettings


def build_engine(settings: DatabaseSettings) -> Engine:
    return create_engine(
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
