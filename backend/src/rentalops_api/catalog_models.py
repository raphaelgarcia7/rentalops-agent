"""Catalog persistence. Product units are complete rental items."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from rentalops_api.models import Base


class CatalogRecord:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class Product(CatalogRecord, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 200", name="ck_product_name"
        ),
        CheckConstraint("price >= 0", name="ck_product_price"),
        CheckConstraint("version >= 1", name="ck_product_version"),
        CheckConstraint("replacement_value >= 0", name="ck_product_replacement"),
        CheckConstraint(
            "total_quantity >= 0 AND maintenance_quantity BETWEEN 0 AND total_quantity",
            name="ck_product_stock",
        ),
        Index("ix_products_name_id", "name", "id"),
    )
    total_quantity: Mapped[int] = mapped_column(Integer)
    maintenance_quantity: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(String(4000))
    category: Mapped[str | None] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(100))
    dimensions: Mapped[str | None] = mapped_column(String(200))
    replacement_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    observation: Mapped[str | None] = mapped_column(String(4000))


class Kit(CatalogRecord, Base):
    __tablename__ = "kits"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 200", name="ck_kit_name"),
        CheckConstraint("price >= 0", name="ck_kit_price"),
        CheckConstraint("version >= 1", name="ck_kit_version"),
        Index("ix_kits_name_id", "name", "id"),
    )


class KitItem(Base):
    __tablename__ = "kit_items"
    __table_args__ = (CheckConstraint("quantity >= 1", name="ck_kit_item_quantity"),)
    kit_id: Mapped[UUID] = mapped_column(ForeignKey("kits.id"), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer)


class CatalogHistory(Base):
    __tablename__ = "catalog_history"
    __table_args__ = (
        CheckConstraint(
            "(product_id IS NULL) <> (kit_id IS NULL)", name="ck_history_target"
        ),
        CheckConstraint("length(btrim(reason)) > 0", name="ck_history_reason"),
        Index("ix_history_product", "product_id", "created_at", "id"),
        Index("ix_history_kit", "kit_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"))
    kit_id: Mapped[UUID | None] = mapped_column(ForeignKey("kits.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    operation: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('initial','entry','withdrawal','correction',"
            "'maintenance','release')",
            name="ck_stock_operation",
        ),
        CheckConstraint("length(btrim(reason)) > 0", name="ck_stock_reason"),
        CheckConstraint("quantity >= 0", name="ck_stock_quantity"),
        CheckConstraint(
            "total_after >= 0 AND maintenance_after BETWEEN 0 AND total_after",
            name="ck_stock_after",
        ),
        Index("ix_stock_product", "product_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    operation: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer)
    total_after: Mapped[int] = mapped_column(Integer)
    maintenance_after: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class MaintenanceEntry(Base):
    __tablename__ = "maintenance_entries"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_maintenance_quantity"),
        CheckConstraint("length(btrim(reason)) > 0", name="ck_maintenance_reason"),
        CheckConstraint("released_quantity BETWEEN 0 AND quantity", name="ck_released"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    released_quantity: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ProductPhoto(Base):
    __tablename__ = "product_photos"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_photo_storage_key"),
        CheckConstraint("format IN ('JPEG','PNG','WEBP')", name="ck_photo_format"),
        CheckConstraint("size > 0 AND position >= 0", name="ck_photo_size_order"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_photo_hash"),
        Index(
            "uq_product_principal_photo",
            "product_id",
            unique=True,
            postgresql_where=text("is_principal AND is_attached"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(40))
    format: Mapped[str] = mapped_column(String(4))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer)
    is_principal: Mapped[bool] = mapped_column(Boolean)
    is_attached: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
