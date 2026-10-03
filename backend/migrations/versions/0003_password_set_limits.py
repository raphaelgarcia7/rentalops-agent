"""Persist password-setting budgets before any costly credential work."""

import sqlalchemy as sa
from alembic import op

revision = "0003_password_set_limits"
down_revision = "0002_password_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_set_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("identifier_hash", sa.String(64), nullable=False),
        sa.Column("origin_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for key in ("identifier", "origin"):
        op.create_index(
            f"ix_password_set_{key}_time",
            "password_set_attempts",
            [f"{key}_hash", "created_at"],
        )


def downgrade() -> None:
    op.drop_table("password_set_attempts")
