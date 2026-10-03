"""Fail closed before any test connection or namespace mutation."""

import re
from uuid import uuid4

from rentalops_api.config import DatabaseConfigurationError, DatabaseSettings

SCHEMA_PATTERN = re.compile(r"rentalops_test_[0-9a-f]{32}")


def local_host(host: str | None) -> str:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "loopback"
    return host or ""


def test_settings(
    test_url: str | None, development_url: str | None
) -> DatabaseSettings:
    if not test_url:
        raise DatabaseConfigurationError(
            "TEST_DATABASE_URL is required for integration."
        )
    settings = DatabaseSettings.from_url(test_url)
    url = settings.url
    if (
        local_host(url.host) != "loopback"
        or url.query
        or not re.fullmatch(r"[a-z0-9_]+", url.database or "")
        or not re.search(r"(^|_)test($|_)", url.database or "")
    ):
        raise DatabaseConfigurationError(
            "Integration requires a local, explicitly named test database, "
            "without URL query options."
        )
    if development_url:
        development = DatabaseSettings.from_url(development_url).url
        if (local_host(url.host), url.port or 5432, url.database) == (
            local_host(development.host),
            development.port or 5432,
            development.database,
        ):
            raise DatabaseConfigurationError(
                "Test and development databases must differ."
            )
        # libpq query parameters can redirect a development URL. Refuse ambiguity.
        if development.query:
            raise DatabaseConfigurationError(
                "Development URL query options prevent safe target comparison."
            )
    host = "::1" if url.host == "::1" else "127.0.0.1"
    # Pin the actual address as well, so PGHOSTADDR/PGSERVICE cannot redirect it.
    return DatabaseSettings(
        url.set(host=host, port=url.port or 5432).update_query_dict({"hostaddr": host})
    )


def new_schema_name() -> str:
    return "rentalops_test_" + uuid4().hex


def validated_schema(name: str) -> str:
    if not SCHEMA_PATTERN.fullmatch(name):
        raise ValueError("Refusing an unowned test schema.")
    return name
