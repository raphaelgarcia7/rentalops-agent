"""Confirmed commitments, immutable confirmation results and operational issues."""

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


class Rental(Base):
    __tablename__ = "rentals"
    __table_args__ = (
        UniqueConstraint("quotation_id", name="uq_rental_quotation"),
        ForeignKeyConstraint(
            ["quotation_id", "quotation_version"],
            ["quotation_versions.quotation_id", "quotation_versions.number"],
        ),
        ForeignKeyConstraint(
            ["quotation_id", "financial_version"],
            ["payment_history.quotation_id", "payment_history.financial_version"],
        ),
        CheckConstraint(
            "version >= 1 AND state IN ('confirmed','cancelled','review')",
            name="ck_rental_state",
        ),
        CheckConstraint("confirmation_deposit > 0", name="ck_rental_deposit"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(Uuid)
    quotation_version: Mapped[int] = mapped_column(Integer)
    financial_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmation_deposit: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(20), default="confirmed")
    commercial_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    financial_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RentalAllocation(Base):
    __tablename__ = "rental_allocations"
    __table_args__ = (
        CheckConstraint(
            "quantity BETWEEN 1 AND 2147483647", name="ck_rental_allocation_qty"
        ),
        CheckConstraint(
            "pickup_date <= return_date", name="ck_rental_allocation_interval"
        ),
        Index(
            "ix_rental_allocation_period", "product_id", "pickup_date", "return_date"
        ),
    )
    rental_id: Mapped[UUID] = mapped_column(ForeignKey("rentals.id"), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    pickup_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[date] = mapped_column(Date)


class RentalPending(Base):
    __tablename__ = "rental_pending"
    __table_args__ = (
        # Refer only to the immutable version, never the locked quotation/rental
        # header. Catalog commands hold product locks: an FK to either header
        # would introduce a reverse KEY SHARE lock during their inserts.
        ForeignKeyConstraint(
            ["quotation_id", "quotation_version"],
            ["quotation_versions.quotation_id", "quotation_versions.number"],
        ),
        UniqueConstraint(
            "quotation_id",
            "kind",
            "source",
            "source_version",
            name="uq_rental_pending_origin",
        ),
        CheckConstraint(
            "kind IN ('inventory','financial') AND source_version >= 1",
            name="ck_rental_pending_kind",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(Uuid)
    quotation_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(100))
    source_version: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class RentalHistory(Base):
    __tablename__ = "rental_history"
    __table_args__ = (
        UniqueConstraint("rental_id", "version", name="uq_rental_history_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rental_id: Mapped[UUID] = mapped_column(ForeignKey("rentals.id"))
    version: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(1000))
    before: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    after: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RentalRequest(Base):
    __tablename__ = "rental_requests"
    __table_args__ = (
        CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'", name="ck_rental_request_hash"
        ),
        CheckConstraint("status IN (201,409)", name="ck_rental_request_status"),
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    operation: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict[str, object]] = mapped_column(JSON)
