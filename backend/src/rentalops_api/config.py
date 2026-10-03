"""Explicit database configuration; importing this module performs no I/O."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class DatabaseConfigurationError(ValueError):
    """A safe diagnostic that never includes a supplied connection string."""


def environment_values(
    env_file: Path = ROOT_ENV_FILE,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    values = {key: value for key, value in dotenv_values(env_file).items() if value}
    values.update(os.environ if environ is None else environ)
    return values


@dataclass(frozen=True)
class DatabaseSettings:
    url: URL = field(repr=False)

    @classmethod
    def from_url(cls, value: str | None) -> DatabaseSettings:
        if not value:
            raise DatabaseConfigurationError("DATABASE_URL is required.")
        try:
            url = make_url(value)
            # Validate the port now, rather than failing later with a raw URL.
            port = url.port
        except ArgumentError, ValueError, TypeError:
            raise DatabaseConfigurationError(
                "Invalid database configuration."
            ) from None
        if (
            url.drivername not in {"postgresql", "postgresql+psycopg"}
            or not url.database
            or not url.host
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise DatabaseConfigurationError("A PostgreSQL database URL is required.")
        return cls(url.set(drivername="postgresql+psycopg"))

    @classmethod
    def from_environment(cls) -> DatabaseSettings:
        return cls.from_url(environment_values().get("DATABASE_URL"))
