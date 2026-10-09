"""Schema compatibility derived from the bundled migration graph."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text

from rentalops_api.operations import OperationsError


def schema_head() -> str:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "migrations")
    )
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise OperationsError("Schema unavailable.")
    return head


def check_schema(connection: Connection) -> str:
    version = connection.scalar(text("SELECT version_num FROM alembic_version"))
    if version != schema_head():
        raise OperationsError("Schema incompatible.")
    return str(version)
