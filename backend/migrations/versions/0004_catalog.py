"""Products, product-only kits, audit movements and private photo metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0004_catalog"
down_revision = "0003_password_set_limits"
branch_labels = None
depends_on = None


def identifier():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def timestamp(name="created_at"):
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def record_columns():
    return [
        identifier(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        timestamp(),
        timestamp("updated_at"),
    ]


def upgrade() -> None:
    op.create_table(
        "products",
        *record_columns(),
        sa.Column("total_quantity", sa.Integer(), nullable=False),
        sa.Column("maintenance_quantity", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(4000)),
        sa.Column("category", sa.String(100)),
        sa.Column("color", sa.String(100)),
        sa.Column("dimensions", sa.String(200)),
        sa.Column("replacement_value", sa.Numeric(12, 2)),
        sa.Column("observation", sa.String(4000)),
        sa.CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 200", name="ck_product_name"
        ),
        sa.CheckConstraint("price >= 0", name="ck_product_price"),
        sa.CheckConstraint("version >= 1", name="ck_product_version"),
        sa.CheckConstraint("replacement_value >= 0", name="ck_product_replacement"),
        sa.CheckConstraint(
            "total_quantity >= 0 AND maintenance_quantity BETWEEN 0 AND total_quantity",
            name="ck_product_stock",
        ),
    )
    op.create_index("ix_products_name_id", "products", ["name", "id"])
    op.create_table(
        "kits",
        *record_columns(),
        sa.CheckConstraint("length(btrim(name)) BETWEEN 1 AND 200", name="ck_kit_name"),
        sa.CheckConstraint("price >= 0", name="ck_kit_price"),
        sa.CheckConstraint("version >= 1", name="ck_kit_version"),
    )
    op.create_index("ix_kits_name_id", "kits", ["name", "id"])
    op.create_table(
        "kit_items",
        sa.Column("kit_id", sa.Uuid(), sa.ForeignKey("kits.id"), primary_key=True),
        sa.Column(
            "product_id", sa.Uuid(), sa.ForeignKey("products.id"), primary_key=True
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_kit_item_quantity"),
    )
    op.create_table(
        "catalog_history",
        identifier(),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id")),
        sa.Column("kit_id", sa.Uuid(), sa.ForeignKey("kits.id")),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "session_id", sa.Uuid(), sa.ForeignKey("auth_sessions.id"), nullable=False
        ),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        timestamp(),
        sa.CheckConstraint(
            "(product_id IS NULL) <> (kit_id IS NULL)", name="ck_history_target"
        ),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_history_reason"),
    )
    op.create_index(
        "ix_history_product", "catalog_history", ["product_id", "created_at", "id"]
    )
    op.create_index("ix_history_kit", "catalog_history", ["kit_id", "created_at", "id"])
    op.create_table(
        "stock_movements",
        identifier(),
        sa.Column(
            "product_id", sa.Uuid(), sa.ForeignKey("products.id"), nullable=False
        ),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "session_id", sa.Uuid(), sa.ForeignKey("auth_sessions.id"), nullable=False
        ),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("total_after", sa.Integer(), nullable=False),
        sa.Column("maintenance_after", sa.Integer(), nullable=False),
        timestamp(),
        sa.CheckConstraint(
            "operation IN ('initial','entry','withdrawal','correction',"
            "'maintenance','release')",
            name="ck_stock_operation",
        ),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_stock_reason"),
        sa.CheckConstraint("quantity >= 0", name="ck_stock_quantity"),
        sa.CheckConstraint(
            "total_after >= 0 AND maintenance_after BETWEEN 0 AND total_after",
            name="ck_stock_after",
        ),
    )
    op.create_index(
        "ix_stock_product", "stock_movements", ["product_id", "created_at", "id"]
    )
    op.create_table(
        "maintenance_entries",
        identifier(),
        sa.Column(
            "product_id", sa.Uuid(), sa.ForeignKey("products.id"), nullable=False
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("released_quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        timestamp(),
        sa.CheckConstraint("quantity >= 1", name="ck_maintenance_quantity"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_maintenance_reason"),
        sa.CheckConstraint(
            "released_quantity BETWEEN 0 AND quantity", name="ck_released"
        ),
    )
    op.create_index(
        "ix_maintenance_entries_product_id", "maintenance_entries", ["product_id"]
    )
    op.create_table(
        "product_photos",
        identifier(),
        sa.Column(
            "product_id", sa.Uuid(), sa.ForeignKey("products.id"), nullable=False
        ),
        sa.Column("storage_key", sa.String(40), nullable=False),
        sa.Column("format", sa.String(4), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_principal", sa.Boolean(), nullable=False),
        sa.Column("is_attached", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        timestamp(),
        sa.UniqueConstraint("storage_key", name="uq_photo_storage_key"),
        sa.CheckConstraint("format IN ('JPEG','PNG','WEBP')", name="ck_photo_format"),
        sa.CheckConstraint("size > 0 AND position >= 0", name="ck_photo_size_order"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_photo_hash"),
    )
    op.create_index("ix_product_photos_product_id", "product_photos", ["product_id"])
    op.create_index(
        "uq_product_principal_photo",
        "product_photos",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_principal AND is_attached"),
    )


def downgrade() -> None:
    for table in (
        "product_photos",
        "maintenance_entries",
        "stock_movements",
        "catalog_history",
        "kit_items",
        "kits",
        "products",
    ):
        op.drop_table(table)
