"""Create minimal team identity, without authentication or seeded accounts."""

import sqlalchemy as sa
from alembic import op

revision = "0001_team_identity"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "length(email) BETWEEN 1 AND 320 AND email = lower(btrim(email))",
            name="ck_users_email_normalized",
        ),
    )
    # Normalize direct SQL writes too, before length and unique checks run.
    op.execute("""
        CREATE FUNCTION normalize_team_identity() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.email := lower(regexp_replace(
                NEW.email, '^[[:space:]]+|[[:space:]]+$', '', 'g'
            ));
            IF TG_OP = 'UPDATE' THEN
                NEW.updated_at := clock_timestamp();
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER users_normalize_identity
        BEFORE INSERT OR UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION normalize_team_identity()
    """)


def downgrade() -> None:
    op.drop_table("users")
    op.execute("DROP FUNCTION normalize_team_identity()")
