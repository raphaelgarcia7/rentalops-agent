"""Explicit confirmation: replay, versions, payment, product locks and stock."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from rentalops_api.auth import Identity
from rentalops_api.capacity import capacity_view
from rentalops_api.catalog_models import Kit, Product
from rentalops_api.database import session_scope
from rentalops_api.payments import PaymentService
from rentalops_api.quotation_contracts import SAO_PAULO, validity_state
from rentalops_api.quotation_models import Quotation, QuotationVersion
from rentalops_api.rental_contracts import (
    ConfirmationCommand,
    ConfirmationPreview,
    RentalView,
)
from rentalops_api.rental_effects import (
    pending_rows,
    record_pending,
    rental_for_quotation,
    rental_summary,
)
from rentalops_api.rental_models import (
    Rental,
    RentalAllocation,
    RentalHistory,
    RentalRequest,
)


class RentalError(Exception):
    def __init__(self, status: int, code: str, message: str, **data: object) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.data = data


def version_conflict() -> RentalError:
    return RentalError(
        409,
        "version_conflict",
        "Os dados mudaram. Consulte o financeiro e faça uma nova prévia.",
    )


def snapshot_demand(snapshot: dict[str, object]) -> dict[UUID, int]:
    demand: dict[UUID, int] = {}
    for line in cast(list[dict[str, object]], snapshot["lines"]):
        for item in cast(list[dict[str, object]], line["items"]):
            pid = UUID(str(item["product_id"]))
            demand[pid] = demand.get(pid, 0) + int(str(item["quantity"])) * int(
                str(line["quantity"])
            )
    return demand


class RentalService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.factory = factory
        self.clock = clock or (lambda: datetime.now(UTC))
        self.payments = PaymentService(factory, clock=self.clock)

    def _check(
        self,
        session: Session,
        identifier: UUID,
        payload: ConfirmationPreview,
        *,
        locked: bool,
    ) -> tuple[
        Quotation,
        QuotationVersion,
        dict[str, object],
        list[dict[str, object]],
        Rental | None,
    ]:
        query = select(Quotation).where(Quotation.id == identifier)
        if locked:
            query = query.with_for_update()
        header = session.scalar(query)
        if header is None:
            raise RentalError(404, "not_found", "Orçamento não encontrado.")
        if header.current_version != payload.expected_quotation_version:
            raise version_conflict()
        rental = rental_for_quotation(session, identifier, locked=locked)
        if (
            rental
            and rental.state == "review"
            and rental.version != payload.expected_rental_version
        ):
            raise version_conflict()
        offer = session.get(QuotationVersion, (identifier, header.current_version))
        assert offer is not None
        if offer.pickup_date < self.clock().astimezone(SAO_PAULO).date():
            raise RentalError(
                409,
                "pickup_passed",
                "A retirada prevista já passou. Revise as datas antes de confirmar.",
            )
        if validity_state(offer.valid_until, self.clock())["expired"]:
            raise RentalError(
                409,
                "expired",
                "Orçamento vencido: revise a proposta antes de confirmar.",
            )
        financial = self.payments.confirmation_summary(
            session, header, offer, locked=locked
        )
        if financial["financial_version"] != payload.expected_financial_version:
            raise version_conflict()
        deposit_sources = [
            row
            for row in cast(list[dict[str, object]], financial["receipts"])
            if Decimal(str(row["applied_deposit"])) > 0
        ]
        financial["deposit_validated"] = bool(
            financial["deposit_validated"]
            and len(deposit_sources) == 1
            and Decimal(str(deposit_sources[0]["applied_deposit"]))
            == offer.estimated_deposit
            and Decimal(str(deposit_sources[0]["net"]))
            >= Decimal(str(deposit_sources[0]["applied_deposit"]))
            + Decimal(str(deposit_sources[0]["applied_balance"]))
        )
        demand = snapshot_demand(offer.snapshot)
        # No price/composition rewriting. Locks only stabilize active status and
        # physical capacity; the persisted quotation is the commercial authority.
        kit_ids = [
            UUID(str(line["source_id"]))
            for line in cast(list[dict[str, object]], offer.snapshot["lines"])
            if line["kind"] == "kit"
        ]
        kits_query = select(Kit).where(Kit.id.in_(kit_ids)).order_by(Kit.id)
        products_query = (
            select(Product).where(Product.id.in_(demand)).order_by(Product.id)
        )
        if locked:
            kits_query = kits_query.with_for_update(read=True)
            products_query = products_query.with_for_update()
        kits = list(session.scalars(kits_query))
        products = {row.id: row for row in session.scalars(products_query)}
        if any(not row.is_active for row in kits) or any(
            not row.is_active for row in products.values()
        ):
            raise RentalError(
                409,
                "inactive_catalog",
                "Há item inativo. Revise a proposta com a equipe antes de confirmar.",
            )
        capacity = capacity_view(
            session,
            products,
            demand,
            offer.pickup_date,
            offer.return_date,
            exclude_rental=rental.id if rental else None,
        )
        return header, offer, financial, capacity, rental

    def preview(
        self, identifier: UUID, payload: ConfirmationPreview
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            header, offer, financial, capacity, _ = self._check(
                session, identifier, payload, locked=False
            )
            return {
                "quotation_id": str(header.id),
                "quotation_version": offer.number,
                "financial_version": financial["financial_version"],
                "deposit_valid": financial["deposit_validated"],
                "pending": not financial["deposit_validated"]
                or any(row["shortage"] for row in capacity),
                "capacity": capacity,
                "checked_at": self.clock().isoformat(),
                "readonly": True,
            }

    def confirm(
        self, identifier: UUID, payload: ConfirmationCommand, actor: Identity
    ) -> tuple[dict[str, object], bool]:
        operation = f"confirm:{identifier}"
        digest = hashlib.sha256(
            json.dumps(
                payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        key = int.from_bytes(
            hashlib.sha256(
                f"rental:{actor.user_id}:{operation}:{payload.request_id}".encode()
            ).digest()[:8],
            "big",
            signed=True,
        )
        error: RentalError | None = None
        with session_scope(self.factory) as session:
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            replay = session.get(
                RentalRequest, (actor.user_id, operation, payload.request_id)
            )
            if replay:
                if replay.payload_hash != digest:
                    raise RentalError(
                        409,
                        "idempotency_conflict",
                        "A chave já foi usada com outros dados. "
                        "Consulte a tentativa original.",
                    )
                if replay.status == 409:
                    raise RentalError(
                        409,
                        str(replay.result["code"]),
                        str(replay.result["detail"]),
                        capacity=replay.result["capacity"],
                    )
                return replay.result, True
            header, offer, financial, capacity, existing = self._check(
                session, identifier, payload, locked=True
            )
            if existing and existing.state != "review":
                raise RentalError(
                    409,
                    "already_confirmed",
                    "Reserva já confirmada. Consulte a locação; "
                    "alterações comerciais exigem o fluxo de alteração.",
                )
            if not financial["deposit_validated"]:
                raise RentalError(
                    409,
                    "deposit_required",
                    "Concilie um sinal completo em um único recebimento líquido "
                    "da versão vigente. Pagamento e comprovante não confirmam reserva.",
                )
            if any(row["shortage"] for row in capacity):
                error = RentalError(
                    409,
                    "capacity_conflict",
                    "Capacidade insuficiente. O dinheiro recebido foi preservado; "
                    "a equipe deve combinar a solução com o cliente.",
                    capacity=capacity,
                )
                result: dict[str, object] = {
                    "code": error.code,
                    "detail": error.message,
                    "capacity": capacity,
                }
                record_pending(
                    session,
                    identifier,
                    offer.number,
                    "inventory",
                    f"confirmation:{payload.request_id}",
                    offer.number,
                    {"capacity": capacity},
                    actor,
                    self.clock(),
                )
                status = 409
            else:
                before = self._view(session, existing, header) if existing else {}
                rental = existing or Rental(
                    id=uuid4(),
                    quotation_id=identifier,
                    quotation_version=offer.number,
                    financial_version=payload.expected_financial_version,
                    version=1,
                    confirmation_deposit=offer.estimated_deposit,
                    state="confirmed",
                    commercial_snapshot=offer.snapshot,
                    financial_snapshot=financial,
                    actor_id=actor.user_id,
                    session_id=actor.session_id,
                    checked_at=self.clock(),
                )
                if existing:
                    rental.version += 1
                    rental.state = "confirmed"
                    rental.confirmation_deposit = offer.estimated_deposit
                    rental.quotation_version = offer.number
                    rental.financial_version = payload.expected_financial_version
                    rental.commercial_snapshot = offer.snapshot
                    rental.financial_snapshot = financial
                    rental.actor_id, rental.session_id = actor.user_id, actor.session_id
                    rental.checked_at = self.clock()
                session.add(rental)
                session.flush()
                session.add_all(
                    [
                        RentalAllocation(
                            rental_id=rental.id,
                            product_id=pid,
                            quantity=quantity,
                            pickup_date=offer.pickup_date,
                            return_date=offer.return_date,
                        )
                        for pid, quantity in snapshot_demand(offer.snapshot).items()
                    ]
                )
                session.add(
                    RentalHistory(
                        rental_id=rental.id,
                        version=rental.version,
                        operation="confirmed",
                        reason="Confirmação após revisão" if existing else None,
                        before=before,
                        after={
                            "commercial": offer.snapshot,
                            "financial": financial,
                            "state": "confirmed",
                        },
                        actor_id=actor.user_id,
                        session_id=actor.session_id,
                        created_at=self.clock(),
                    )
                )
                session.flush()
                result = self._view(session, rental, header)
                status = 201
            session.add(
                RentalRequest(
                    actor_id=actor.user_id,
                    operation=operation,
                    request_id=payload.request_id,
                    payload_hash=digest,
                    status=status,
                    result=result,
                )
            )
            session.commit()
        if error:
            raise error
        return result, False

    def _view(
        self, session: Session, rental: Rental, header: Quotation
    ) -> dict[str, object]:
        current_offer = session.get(
            QuotationVersion, (header.id, header.current_version)
        )
        assert current_offer is not None
        return RentalView.model_validate(
            {
                **(rental_summary(session, header.id) or {}),
                "quotation_id": str(header.id),
                "customer_id": str(header.customer_id),
                "quotation_version": rental.quotation_version,
                "financial_version": rental.financial_version or 0,
                "confirmation_deposit": format(rental.confirmation_deposit, ".2f"),
                "signature_commercial_version": rental.quotation_version,
                "current_financial": self.payments.confirmation_summary(
                    session, header, current_offer
                ),
                "commercial_snapshot": rental.commercial_snapshot,
                "financial_snapshot": rental.financial_snapshot,
                "allocations": [
                    {
                        "product_id": str(row.product_id),
                        "quantity": row.quantity,
                        "pickup_date": row.pickup_date.isoformat(),
                        "return_date": row.return_date.isoformat(),
                    }
                    for row in session.scalars(
                        select(RentalAllocation)
                        .where(RentalAllocation.rental_id == rental.id)
                        .order_by(RentalAllocation.product_id)
                    )
                ],
                "pending": pending_rows(session, header.id),
                "actor_id": str(rental.actor_id),
                "session_id": str(rental.session_id),
                "checked_at": rental.checked_at.isoformat(),
            }
        ).model_dump(mode="json")

    def get(self, identifier: UUID, *, by_quotation: bool = False) -> dict[str, object]:
        with session_scope(self.factory) as session:
            rental = (
                rental_for_quotation(session, identifier)
                if by_quotation
                else session.get(Rental, identifier)
            )
            if rental is None:
                raise RentalError(
                    404, "not_found", "Locação confirmada não encontrada."
                )
            header = session.get(Quotation, rental.quotation_id)
            assert header is not None
            return self._view(session, rental, header)

    def history(
        self, identifier: UUID, page: int = 1, page_size: int = 50
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            if session.get(Rental, identifier) is None:
                raise RentalError(404, "not_found", "Locação não encontrada.")
            condition = RentalHistory.rental_id == identifier
            total = (
                session.scalar(
                    select(func.count()).select_from(RentalHistory).where(condition)
                )
                or 0
            )
            rows = session.scalars(
                select(RentalHistory)
                .where(condition)
                .order_by(RentalHistory.version)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return {
                "items": [
                    {
                        "id": str(row.id),
                        "version": row.version,
                        "operation": row.operation,
                        "reason": row.reason,
                        "before": row.before,
                        "after": row.after,
                        "actor_id": str(row.actor_id),
                        "session_id": str(row.session_id),
                        "created_at": row.created_at.isoformat(),
                    }
                    for row in rows
                ],
                "page": page,
                "page_size": page_size,
                "total": total,
            }
