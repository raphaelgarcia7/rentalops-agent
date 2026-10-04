"""Immutable commercial revisions, relational source references and safe replay."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from rentalops_api.models import Base


class Quotation(Base):
    __tablename__ = "quotations"
    __table_args__ = (
        CheckConstraint("current_version >= 1", name="ck_quotation_version"),
        ForeignKeyConstraint(
            ["id", "current_version"],
            ["quotation_versions.quotation_id", "quotation_versions.number"],
            name="fk_quotation_current",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        Index("ix_quotations_customer", "customer_id", "created_at", "id"),
        Index("ix_quotations_order", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"))
    current_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class QuotationVersion(Base):
    __tablename__ = "quotation_versions"
    __table_args__ = (
        CheckConstraint("number >= 1", name="ck_quotation_revision"),
        CheckConstraint(
            "pickup_date <= event_date AND event_date <= return_date "
            "AND valid_until <= pickup_date",
            name="ck_quotation_dates",
        ),
        CheckConstraint(
            "subtotal >= 0 AND discount_amount >= 0 AND discount_amount <= subtotal "
            "AND total = subtotal - discount_amount AND total >= 0.01 "
            "AND estimated_deposit >= 0.01 AND estimated_balance >= 0 "
            "AND estimated_deposit + estimated_balance = total",
            name="ck_quotation_money",
        ),
        CheckConstraint(
            "reason IS NULL OR length(btrim(reason)) BETWEEN 1 AND 4000",
            name="ck_quotation_reason",
        ),
        Index("ix_quotation_versions_validity", "valid_until"),
    )
    quotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("quotations.id"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    pickup_date: Mapped[date] = mapped_column(Date)
    event_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    estimated_deposit: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    estimated_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(4000))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class QuotationLine(Base):
    __tablename__ = "quotation_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quotation_id", "version"],
            ["quotation_versions.quotation_id", "quotation_versions.number"],
        ),
        UniqueConstraint(
            "quotation_id", "version", "position", name="uq_quotation_line_position"
        ),
        CheckConstraint(
            "(product_id IS NULL) <> (kit_id IS NULL)", name="ck_quotation_line_source"
        ),
        CheckConstraint(
            "quantity BETWEEN 1 AND 2147483647 AND unit_price >= 0 "
            "AND position >= 0 AND source_version >= 1",
            name="ck_quotation_line_values",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"))
    kit_id: Mapped[UUID | None] = mapped_column(ForeignKey("kits.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    source_version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON)


class QuotationComponent(Base):
    __tablename__ = "quotation_components"
    __table_args__ = (
        CheckConstraint(
            "quantity BETWEEN 1 AND 2147483647 AND source_version >= 1",
            name="ck_quotation_component_values",
        ),
    )
    line_id: Mapped[UUID] = mapped_column(
        ForeignKey("quotation_lines.id"), primary_key=True
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    source_version: Mapped[int] = mapped_column(Integer)
    source_name: Mapped[str] = mapped_column(String(200))


class QuotationAudit(Base):
    __tablename__ = "quotation_audit"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quotation_id", "version"],
            ["quotation_versions.quotation_id", "quotation_versions.number"],
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    operation: Mapped[str] = mapped_column(String(20))
    changed_fields: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class QuotationRequest(Base):
    __tablename__ = "quotation_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quotation_id", "version"],
            ["quotation_versions.quotation_id", "quotation_versions.number"],
        ),
        CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'", name="ck_quotation_request_hash"
        ),
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    operation: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    quotation_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict[str, object]] = mapped_column(JSON)
