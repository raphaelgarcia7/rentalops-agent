"""Password credentials, opaque sessions and private administrative links."""

import sqlalchemy as sa
from alembic import op

revision = "0002_password_auth"
down_revision = "0001_team_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "password_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("purpose IN ('access', 'reset')", name="ck_link_purpose"),
    )
    op.create_index("ix_password_links_user_id", "password_links", ["user_id"])
    op.create_table(
        "login_failures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("identifier_hash", sa.String(64), nullable=False),
        sa.Column("origin_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for key in ("identifier", "origin"):
        op.create_index(
            f"ix_failure_{key}_time", "login_failures", [f"{key}_hash", "created_at"]
        )
    op.create_table(
        "auth_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("auth_sessions.id")),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in ("auth_audit", "login_failures", "password_links", "auth_sessions"):
        op.drop_table(table)
    op.drop_column("users", "password_hash")
