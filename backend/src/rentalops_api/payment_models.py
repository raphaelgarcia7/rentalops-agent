"""Financial revisions, immutable money events and scoped private attachments."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
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


class PaymentAccount(Base):
    __tablename__ = "payment_accounts"
    __table_args__ = (
        CheckConstraint("version >= 0", name="ck_payment_account_version"),
        ForeignKeyConstraint(
            ["quotation_id", "reconciled_quotation_version"],
            ["quotation_versions.quotation_id", "quotation_versions.number"],
        ),
    )
    quotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("quotations.id"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, default=0)
    reconciled_quotation_version: Mapped[int | None] = mapped_column(Integer)
    requires_reconciliation: Mapped[bool] = mapped_column(Boolean, default=False)


class Receipt(Base):
    __tablename__ = "payment_receipts"
    __table_args__ = (
        UniqueConstraint("id", "quotation_id", name="uq_payment_receipt_account"),
        CheckConstraint("revision >= 1", name="ck_payment_receipt_revision"),
        ForeignKeyConstraint(
            ["id", "revision"],
            [
                "payment_receipt_revisions.receipt_id",
                "payment_receipt_revisions.number",
            ],
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
            name="fk_payment_receipt_current",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_accounts.quotation_id")
    )
    revision: Mapped[int] = mapped_column(Integer)


class ReceiptRevision(Base):
    __tablename__ = "payment_receipt_revisions"
    __table_args__ = (
        CheckConstraint("number >= 1 AND amount > 0", name="ck_receipt_revision_money"),
        CheckConstraint(
            "method IN ('pix','cash','card')", name="ck_receipt_revision_method"
        ),
        CheckConstraint(
            "number = 1 OR length(btrim(reason)) BETWEEN 1 AND 1000",
            name="ck_receipt_revision_reason",
        ),
    )
    receipt_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_receipts.id"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(4))
    business_date: Mapped[date] = mapped_column(Date)
    observation: Mapped[str | None] = mapped_column(String(2000))
    reason: Mapped[str | None] = mapped_column(String(1000))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PaymentRefund(Base):
    __tablename__ = "payment_refunds"
    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_id", "quotation_id"],
            ["payment_receipts.id", "payment_receipts.quotation_id"],
        ),
        CheckConstraint("amount > 0", name="ck_payment_refund_money"),
        CheckConstraint(
            "method IN ('pix','cash','card')", name="ck_payment_refund_method"
        ),
        CheckConstraint(
            "length(btrim(reason)) BETWEEN 1 AND 1000", name="ck_payment_refund_reason"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_accounts.quotation_id")
    )
    receipt_id: Mapped[UUID] = mapped_column(Uuid)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(4))
    business_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(1000))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PaymentProof(Base):
    __tablename__ = "payment_proofs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_id", "quotation_id"],
            ["payment_receipts.id", "payment_receipts.quotation_id"],
        ),
        CheckConstraint("size BETWEEN 1 AND 10000000", name="ck_payment_proof_size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_payment_proof_digest"),
        CheckConstraint(
            "content_type IN ('application/pdf','image/jpeg','image/png')",
            name="ck_payment_proof_type",
        ),
        UniqueConstraint("storage_key", name="uq_payment_proof_key"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_accounts.quotation_id")
    )
    receipt_id: Mapped[UUID] = mapped_column(Uuid)
    storage_key: Mapped[str] = mapped_column(String(42))
    content_type: Mapped[str] = mapped_column(String(20))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PaymentHistory(Base):
    __tablename__ = "payment_history"
    __table_args__ = (
        UniqueConstraint(
            "quotation_id", "financial_version", name="uq_payment_history_version"
        ),
        ForeignKeyConstraint(
            ["quotation_id", "quotation_version"],
            ["quotation_versions.quotation_id", "quotation_versions.number"],
        ),
        CheckConstraint("financial_version >= 1", name="ck_payment_history_version"),
        Index("ix_payment_history_order", "quotation_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    quotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("payment_accounts.quotation_id")
    )
    financial_version: Mapped[int] = mapped_column(Integer)
    quotation_version: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    reason: Mapped[str | None] = mapped_column(String(1000))
    before: Mapped[dict[str, object]] = mapped_column(JSON)
    after: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["quotation_id", "financial_version"],
            ["payment_history.quotation_id", "payment_history.financial_version"],
        ),
        ForeignKeyConstraint(
            ["receipt_id", "quotation_id"],
            ["payment_receipts.id", "payment_receipts.quotation_id"],
        ),
        CheckConstraint(
            "deposit >= 0 AND balance >= 0", name="ck_payment_allocation_money"
        ),
    )
    quotation_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    financial_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    deposit: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    __table_args__ = (
        CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'", name="ck_payment_request_hash"
        ),
        ForeignKeyConstraint(
            ["quotation_id", "financial_version"],
            ["payment_history.quotation_id", "payment_history.financial_version"],
        ),
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    quotation_id: Mapped[UUID] = mapped_column(Uuid)
    financial_version: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict[str, object]] = mapped_column(JSON)
