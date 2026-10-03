"""Progressive PF customers, CPF uniqueness and metadata-only audit."""

import sqlalchemy as sa
from alembic import op

revision = "0005_customers"
down_revision = "0004_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(16), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("notes", sa.String(4000)),
        sa.Column("cpf", sa.String(11)),
        sa.Column("rg", sa.String(30)),
        sa.Column("address", sa.JSON()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("cpf", name="uq_customers_cpf"),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 200", name="ck_customer_name"
        ),
        sa.CheckConstraint("phone ~ '^\\+[1-9][0-9]{6,14}$'", name="ck_customer_phone"),
        sa.CheckConstraint(
            "cpf IS NULL OR cpf ~ '^[0-9]{11}$'", name="ck_customer_cpf"
        ),
        sa.CheckConstraint("version >= 1", name="ck_customer_version"),
    )
    op.create_index("ix_customers_name_id", "customers", ["name", "id"])
    op.create_index("ix_customers_phone", "customers", ["phone"])
    op.create_table(
        "customer_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=False
        ),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "session_id", sa.Uuid(), sa.ForeignKey("auth_sessions.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version >= 1", name="ck_customer_audit_version"),
    )
    op.create_index(
        "ix_customer_audit_customer",
        "customer_audit",
        ["customer_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("customer_audit")
    op.drop_table("customers")
