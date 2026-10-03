"""Deterministic customer use cases with short transactions and atomic versions."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rentalops_api.auth import Identity
from rentalops_api.customer_contracts import (
    CustomerCreate,
    CustomerEdit,
    CustomerSearch,
)
from rentalops_api.customer_models import Customer, CustomerAudit
from rentalops_api.database import session_scope


class CustomerError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        existing_ids: list[UUID] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.existing_ids = existing_ids or []
        super().__init__(message)


def customer_view(record: Customer) -> dict[str, object]:
    return {
        field: getattr(record, field)
        for field in (
            "id",
            "name",
            "phone",
            "email",
            "notes",
            "cpf",
            "rg",
            "address",
            "version",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
    }


class CustomerService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def _shared_contact(
        self,
        session: Session,
        phone: str,
        acknowledged: list[UUID],
        identifier: UUID | None,
    ) -> None:
        # The hash is only a transaction lock key, never a trace or stored identifier.
        lock_key = int.from_bytes(sha256(phone.encode()).digest()[:8], signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        query = select(Customer.id).where(Customer.phone == phone)
        if identifier is not None:
            query = query.where(Customer.id != identifier)
        existing = list(session.scalars(query.order_by(Customer.id)))
        if not set(existing).issubset(acknowledged):
            raise CustomerError(
                409,
                "shared_contact",
                "Este contato já está em outro cadastro. "
                "Consulte antes de confirmar uma pessoa distinta.",
                existing,
            )

    def _audit(
        self, session: Session, record: Customer, actor: Identity, changed: list[str]
    ) -> None:
        session.add(
            CustomerAudit(
                customer_id=record.id,
                actor_id=actor.user_id,
                session_id=actor.session_id,
                version=record.version,
                changed_fields=sorted(changed),
            )
        )

    def _detail(self, session: Session, record: Customer) -> dict[str, object]:
        entries = session.scalars(
            select(CustomerAudit)
            .where(CustomerAudit.customer_id == record.id)
            .order_by(CustomerAudit.version, CustomerAudit.id)
        )
        return {
            **customer_view(record),
            "history": [
                {
                    key: getattr(entry, key)
                    for key in (
                        "id",
                        "actor_id",
                        "session_id",
                        "version",
                        "changed_fields",
                        "created_at",
                    )
                }
                for entry in entries
            ],
        }

    def _cpf_conflict(self, error: IntegrityError, cpf: str | None) -> None:
        diagnostic = getattr(error.orig, "diag", None)
        if getattr(diagnostic, "constraint_name", None) != "uq_customers_cpf":
            raise error
        with session_scope(self.factory) as session:
            identifier = session.scalar(select(Customer.id).where(Customer.cpf == cpf))
        raise CustomerError(
            409,
            "duplicate_cpf",
            "CPF já cadastrado. Consulte o cliente existente.",
            [identifier] if identifier else [],
        ) from None

    def create(self, payload: CustomerCreate, actor: Identity) -> dict[str, object]:
        try:
            with session_scope(self.factory) as session:
                self._shared_contact(
                    session, payload.phone, payload.acknowledged_shared_contact, None
                )
                fields = payload.model_dump(exclude={"acknowledged_shared_contact"})
                record = Customer(
                    **fields, created_by=actor.user_id, updated_by=actor.user_id
                )
                session.add(record)
                session.flush()
                self._audit(
                    session,
                    record,
                    actor,
                    [key for key, value in fields.items() if value is not None],
                )
                session.flush()
                result = self._detail(session, record)
                session.commit()
                return result
        except IntegrityError as error:
            self._cpf_conflict(error, payload.cpf)
            raise AssertionError("Unreachable") from None

    def edit(
        self, identifier: UUID, payload: CustomerEdit, actor: Identity
    ) -> dict[str, object]:
        fields = payload.model_dump(
            exclude={"expected_version", "acknowledged_shared_contact"},
            exclude_unset=True,
        )
        try:
            with session_scope(self.factory) as session:
                current = session.get(Customer, identifier)
                if current is None:
                    raise CustomerError(404, "not_found", "Cliente não encontrado.")
                if current.version != payload.expected_version:
                    raise CustomerError(
                        409,
                        "stale_version",
                        "Outra pessoa alterou este cliente. Seu rascunho foi mantido; "
                        "consulte a versão atual.",
                    )
                if isinstance(fields.get("address"), dict):
                    address = {**(current.address or {}), **fields["address"]}
                    fields["address"] = address if any(address.values()) else None
                phone = fields.get("phone", current.phone)
                assert isinstance(phone, str)
                if phone != current.phone:
                    self._shared_contact(
                        session, phone, payload.acknowledged_shared_contact, identifier
                    )
                changed = [
                    key
                    for key, value in fields.items()
                    if getattr(current, key) != value
                ]
                updated = session.scalar(
                    update(Customer)
                    .where(
                        Customer.id == identifier,
                        Customer.version == payload.expected_version,
                    )
                    .values(
                        **fields,
                        version=Customer.version + 1,
                        updated_by=actor.user_id,
                        updated_at=datetime.now(UTC),
                    )
                    .returning(Customer)
                    .execution_options(populate_existing=True)
                )
                if updated is None:
                    raise CustomerError(
                        409,
                        "stale_version",
                        "Outra pessoa alterou este cliente. Seu rascunho foi mantido; "
                        "consulte a versão atual.",
                    )
                self._audit(session, updated, actor, changed)
                session.flush()
                result = self._detail(session, updated)
                session.commit()
                return result
        except IntegrityError as error:
            cpf = fields.get("cpf")
            self._cpf_conflict(error, cpf if isinstance(cpf, str) else None)
            raise AssertionError("Unreachable") from None

    def get(self, identifier: UUID) -> dict[str, object]:
        with session_scope(self.factory) as session:
            record = session.scalar(
                select(Customer)
                .where(Customer.id == identifier)
                .with_for_update(read=True)
            )
            if record is None:
                raise CustomerError(404, "not_found", "Cliente não encontrado.")
            return self._detail(session, record)

    def search(self, payload: CustomerSearch) -> dict[str, object]:
        conditions = []
        if payload.name:
            conditions.append(Customer.name.icontains(payload.name, autoescape=True))
        if payload.phone:
            conditions.append(Customer.phone == payload.phone)
        if payload.cpf:
            conditions.append(Customer.cpf == payload.cpf)
        with session_scope(self.factory) as session:
            total = session.scalar(
                select(func.count()).select_from(Customer).where(*conditions)
            )
            records = session.scalars(
                select(Customer)
                .where(*conditions)
                .order_by(Customer.name, Customer.id)
                .offset((payload.page - 1) * payload.page_size)
                .limit(payload.page_size)
            )
            return {
                "items": [
                    {
                        key: getattr(record, key)
                        for key in ("id", "name", "phone", "version")
                    }
                    for record in records
                ],
                "total": total,
                "page": payload.page,
                "page_size": payload.page_size,
            }
