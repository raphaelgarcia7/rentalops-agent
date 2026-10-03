"""Online, explicit migrations; tests may supply their isolated connection."""

from alembic import context

from rentalops_api import catalog_models  # noqa: F401 - register catalog metadata
from rentalops_api.config import DatabaseSettings
from rentalops_api.database import build_engine
from rentalops_api.models import Base


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError(
        "Offline migrations are not supported; use an explicit database."
    )

provided_connection = context.config.attributes.get("connection")
if provided_connection is not None:
    migrate(provided_connection)
else:
    engine = build_engine(DatabaseSettings.from_environment())
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
