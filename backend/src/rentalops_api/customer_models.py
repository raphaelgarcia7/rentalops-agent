"""Customer identity and metadata-only audit; no rental state is invented."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from rentalops_api.models import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("cpf", name="uq_customers_cpf"),
        CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 200", name="ck_customer_name"
        ),
        CheckConstraint("phone ~ '^\\+[1-9][0-9]{6,14}$'", name="ck_customer_phone"),
        CheckConstraint("cpf IS NULL OR cpf ~ '^[0-9]{11}$'", name="ck_customer_cpf"),
        CheckConstraint("version >= 1", name="ck_customer_version"),
        Index("ix_customers_name_id", "name", "id"),
        Index("ix_customers_phone", "phone"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(320))
    notes: Mapped[str | None] = mapped_column(String(4000))
    cpf: Mapped[str | None] = mapped_column(String(11))
    rg: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[dict[str, str | None] | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class CustomerAudit(Base):
    __tablename__ = "customer_audit"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_customer_audit_version"),
        Index("ix_customer_audit_customer", "customer_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("auth_sessions.id"))
    version: Mapped[int] = mapped_column(Integer)
    changed_fields: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
