"""Commercial quotations, immutable revisions and transactional replay."""

import sqlalchemy as sa
from alembic import op

revision = "0006_quotations"
down_revision = "0005_customers"
branch_labels = None
depends_on = None


def stamp():
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def actor():
    return [
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "session_id", sa.Uuid(), sa.ForeignKey("auth_sessions.id"), nullable=False
        ),
    ]


def revision_fk():
    return sa.ForeignKeyConstraint(
        ["quotation_id", "version"],
        ["quotation_versions.quotation_id", "quotation_versions.number"],
    )


def upgrade() -> None:
    op.create_table(
        "quotations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=False
        ),
        sa.Column("current_version", sa.Integer(), nullable=False),
        stamp(),
        sa.CheckConstraint("current_version >= 1", name="ck_quotation_version"),
    )
    op.create_index(
        "ix_quotations_customer", "quotations", ["customer_id", "created_at", "id"]
    )
    op.create_index("ix_quotations_order", "quotations", ["created_at", "id"])
    op.create_table(
        "quotation_versions",
        sa.Column(
            "quotation_id", sa.Uuid(), sa.ForeignKey("quotations.id"), primary_key=True
        ),
        sa.Column("number", sa.Integer(), primary_key=True),
        *[
            sa.Column(key, sa.Date(), nullable=False)
            for key in ["pickup_date", "event_date", "return_date", "valid_until"]
        ],
        *[
            sa.Column(key, sa.Numeric(12, 2), nullable=False)
            for key in [
                "subtotal",
                "discount_amount",
                "total",
                "estimated_deposit",
                "estimated_balance",
            ]
        ],
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(4000)),
        *actor(),
        stamp(),
        sa.CheckConstraint("number >= 1", name="ck_quotation_revision"),
        sa.CheckConstraint(
            "pickup_date <= event_date AND event_date <= return_date "
            "AND valid_until <= pickup_date",
            name="ck_quotation_dates",
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND discount_amount >= 0 AND discount_amount <= subtotal "
            "AND total = subtotal - discount_amount AND total >= 0.01 "
            "AND estimated_deposit >= 0.01 AND estimated_balance >= 0 "
            "AND estimated_deposit + estimated_balance = total",
            name="ck_quotation_money",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR length(btrim(reason)) BETWEEN 1 AND 4000",
            name="ck_quotation_reason",
        ),
    )
    op.create_index(
        "ix_quotation_versions_validity", "quotation_versions", ["valid_until"]
    )
    op.create_foreign_key(
        "fk_quotation_current",
        "quotations",
        "quotation_versions",
        ["id", "current_version"],
        ["quotation_id", "number"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "quotation_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("quotation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id")),
        sa.Column("kit_id", sa.Uuid(), sa.ForeignKey("kits.id")),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        revision_fk(),
        sa.UniqueConstraint(
            "quotation_id", "version", "position", name="uq_quotation_line_position"
        ),
        sa.CheckConstraint(
            "(product_id IS NULL) <> (kit_id IS NULL)", name="ck_quotation_line_source"
        ),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 2147483647 AND unit_price >= 0 "
            "AND position >= 0 AND source_version >= 1",
            name="ck_quotation_line_values",
        ),
    )
    op.create_table(
        "quotation_components",
        sa.Column(
            "line_id", sa.Uuid(), sa.ForeignKey("quotation_lines.id"), primary_key=True
        ),
        sa.Column(
            "product_id", sa.Uuid(), sa.ForeignKey("products.id"), primary_key=True
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 2147483647 AND source_version >= 1",
            name="ck_quotation_component_values",
        ),
    )
    op.create_table(
        "quotation_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("quotation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        *actor(),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        stamp(),
        revision_fk(),
    )
    op.create_table(
        "quotation_requests",
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("operation", sa.String(80), primary_key=True),
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("quotation_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        revision_fk(),
        sa.CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'", name="ck_quotation_request_hash"
        ),
    )
    op.execute("""CREATE FUNCTION reject_quotation_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Commercial revisions are immutable'; END; $$""")
    for table in [
        "quotation_versions",
        "quotation_lines",
        "quotation_components",
        "quotation_audit",
        "quotation_requests",
    ]:
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_quotation_mutation()"
        )


def downgrade() -> None:
    op.drop_constraint("fk_quotation_current", "quotations", type_="foreignkey")
    for table in [
        "quotation_requests",
        "quotation_audit",
        "quotation_components",
        "quotation_lines",
        "quotation_versions",
        "quotations",
    ]:
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_quotation_mutation()")
