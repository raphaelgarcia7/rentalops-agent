"""Versioned changes under the confirmation lock order and one short transaction."""

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from rentalops_api.auth import Identity
from rentalops_api.catalog_models import Product
from rentalops_api.database import session_scope
from rentalops_api.payment_contracts import ReconciliationCommand
from rentalops_api.quotation_contracts import SAO_PAULO, QuotationDraft, validity_state
from rentalops_api.quotation_models import Quotation, QuotationVersion
from rentalops_api.quotations import QuotationService
from rentalops_api.rental_contracts import (
    CancellationCommand,
    ChangeCommand,
    ChangePreview,
    RentalVersions,
    ResumptionCommand,
)
from rentalops_api.rental_effects import record_pending, rental_for_quotation
from rentalops_api.rental_models import (
    Rental,
    RentalAllocation,
    RentalHistory,
    RentalRequest,
)
from rentalops_api.rentals import (
    RentalError,
    RentalService,
    snapshot_demand,
    version_conflict,
)


def guard_change(
    state: str, before: dict[str, object], after: dict[str, object]
) -> None:
    """#14 supplies persisted out/completed states when that module exists.

    No command here manufactures a handover or a completed rental.
    """
    if state not in {"confirmed", "review", "out"}:
        raise RentalError(
            409, "invalid_state", "Esta locação exige retomada ou uma nova proposta."
        )
    if state == "out":

        def delivered(snapshot: dict[str, object]) -> list[dict[str, object]]:
            return [
                {key: line[key] for key in ("kind", "source_id", "quantity", "items")}
                for line in cast(list[dict[str, object]], snapshot["lines"])
            ]

        if (
            delivered(before) != delivered(after)
            or any(
                before[key] != after[key]
                for key in ("pickup_date", "event_date", "pickup_time", "event_time")
            )
            or date.fromisoformat(str(after["return_date"]))
            < date.fromisoformat(str(before["return_date"]))
            or (
                before["return_date"] == after["return_date"]
                and before.get("return_time") is not None
                and (
                    after.get("return_time") is None
                    or str(after["return_time"]) < str(before["return_time"])
                )
            )
        ):
            raise RentalError(
                409,
                "already_out",
                "Produtos já entregues não podem ser removidos ou substituídos. "
                "Complementos exigem nova locação; devolução antecipada "
                "usa a conferência real.",
            )


def guard_cancellation(state: str) -> None:
    if state in {"out", "completed"}:
        raise RentalError(
            409,
            "already_out",
            "A saída já foi registrada. Combine a devolução antecipada "
            "e registre o recebimento real.",
        )
    if state not in {"confirmed", "review"}:
        raise RentalError(409, "invalid_state", "A locação já está cancelada.")


def copy_draft(snapshot: dict[str, object], customer_id: UUID) -> QuotationDraft:
    """References only; current catalog prices resolve on the normal #10 preview."""
    return QuotationDraft.model_validate(
        {
            **{
                key: value
                for key, value in snapshot.items()
                if key in QuotationDraft.model_fields
                and key not in {"lines", "quotation_id", "expected_version", "discount"}
            },
            "customer_id": customer_id,
            "lines": [
                {
                    "kind": row["kind"],
                    "source_id": row["source_id"],
                    "quantity": row["quantity"],
                }
                for row in cast(list[dict[str, object]], snapshot["lines"])
            ],
            "discount": None,
        }
    )


class RentalChangeService(RentalService):
    def _context(
        self,
        session: Session,
        identifier: UUID,
        payload: RentalVersions,
        *,
        locked: bool,
        by_quotation: bool = False,
    ) -> tuple[Quotation, QuotationVersion, Rental | None, dict[str, object]]:
        if by_quotation:
            quotation_id = identifier
        else:
            existing = session.get(Rental, identifier)
            if existing is None:
                raise RentalError(404, "not_found", "Locação não encontrada.")
            quotation_id = existing.quotation_id
        query = select(Quotation).where(Quotation.id == quotation_id)
        if locked:
            query = query.with_for_update()
        header = session.scalar(query)
        if header is None:
            raise RentalError(404, "not_found", "Orçamento não encontrado.")
        rental = rental_for_quotation(session, header.id, locked=locked)
        if (
            header.current_version != payload.expected_quotation_version
            or (rental.version if rental else 0) != payload.expected_rental_version
        ):
            raise version_conflict()
        offer = session.get(QuotationVersion, (header.id, header.current_version))
        assert offer is not None
        financial = self.payments.confirmation_summary(
            session, header, offer, locked=locked
        )
        if financial["financial_version"] != payload.expected_financial_version:
            raise version_conflict()
        return header, offer, rental, financial

    def _proposal(
        self,
        session: Session,
        header: Quotation,
        rental: Rental | None,
        payload: ChangePreview,
        *,
        locked: bool,
    ) -> dict[str, object]:
        draft = payload.draft
        if (
            draft.quotation_id != header.id
            or draft.expected_version != header.current_version
            or draft.customer_id != header.customer_id
        ):
            raise RentalError(
                422, "invalid_offer", "Revise a proposta e o cliente da mesma locação."
            )
        if rental is None or rental.state != "out":
            today = self.clock().astimezone(SAO_PAULO).date()
            if draft.pickup_date < today or draft.valid_until < today:
                raise RentalError(
                    422,
                    "expired",
                    "Revise a validade e as datas atuais antes de continuar.",
                )
        proposal = QuotationService(self.factory, self.clock)._resolve(
            session,
            draft,
            rental_id=rental.id if rental else None,
            exclusive_products=locked,
        )
        return proposal

    def change_preview(
        self,
        identifier: UUID,
        payload: ChangePreview,
        *,
        by_quotation: bool = False,
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            header, offer, rental, financial = self._context(
                session, identifier, payload, locked=False, by_quotation=by_quotation
            )
            proposal = self._proposal(session, header, rental, payload, locked=False)
            if rental and rental.state in {"confirmed", "out", "review"}:
                guard_change(rental.state, offer.snapshot, proposal)
            elif rental and rental.state != "cancelled":
                raise RentalError(
                    409, "invalid_state", "Locação concluída exige nova proposta."
                )
            total = Decimal(str(proposal["total"]))
            net = Decimal(str(financial["net_received"]))
            deposit_due = (
                min(rental.confirmation_deposit, total)
                if rental and rental.state in {"confirmed", "out"}
                else Decimal(str(proposal["estimated_deposit"]))
            )
            return {
                "before": offer.snapshot,
                "after": proposal,
                "financial": {
                    "net_received": format(net, ".2f"),
                    "remaining": format(max(Decimal(0), total - net), ".2f"),
                    "excess": format(max(Decimal(0), net - total), ".2f"),
                    "deposit_due": format(deposit_due, ".2f"),
                    "balance_due": format(total - deposit_due, ".2f"),
                    "historical_deposit": format(rental.confirmation_deposit, ".2f")
                    if rental
                    else str(financial["estimated_deposit"]),
                    "requires_payment_review": not rental
                    or rental.state in {"cancelled", "review"},
                },
                "expected_rental_version": rental.version if rental else 0,
                "expected_quotation_version": header.current_version,
                "expected_financial_version": financial["financial_version"],
                "requires_new_signature": True,
                "readonly": True,
            }

    def command(
        self,
        identifier: UUID,
        operation: Literal["change", "cancel", "resume"],
        payload: ChangeCommand | CancellationCommand | ResumptionCommand,
        actor: Identity,
        *,
        by_quotation: bool = False,
    ) -> tuple[dict[str, object], bool]:
        op = f"{operation}:{identifier}"
        digest = hashlib.sha256(
            json.dumps(
                payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        lock = int.from_bytes(
            hashlib.sha256(
                f"rental:{actor.user_id}:{op}:{payload.request_id}".encode()
            ).digest()[:8],
            "big",
            signed=True,
        )
        failure: RentalError | None = None
        with session_scope(self.factory) as session, session.no_autoflush:
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
            replay = session.get(RentalRequest, (actor.user_id, op, payload.request_id))
            if replay:
                if replay.payload_hash != digest:
                    raise RentalError(
                        409,
                        "idempotency_conflict",
                        "A chave já foi usada com outros dados. "
                        "Reconcile a tentativa original.",
                    )
                if replay.status == 409:
                    raise RentalError(
                        409,
                        str(replay.result["code"]),
                        str(replay.result["detail"]),
                        capacity=replay.result.get("capacity", []),
                    )
                return replay.result, True
            header, old_offer, rental, financial = self._context(
                session, identifier, payload, locked=True, by_quotation=by_quotation
            )
            before = (
                self._view(session, rental, header)
                if rental
                else {"commercial_snapshot": old_offer.snapshot, "financial": financial}
            )
            proposal: dict[str, object] | None = None
            if operation == "cancel":
                assert isinstance(payload, CancellationCommand) and rental is not None
                guard_cancellation(rental.state)
                # Product union order matches confirmations and catalog edits.
                list(
                    session.scalars(
                        select(Product)
                        .where(Product.id.in_(snapshot_demand(old_offer.snapshot)))
                        .order_by(Product.id)
                        .with_for_update()
                    )
                )
                if payload.approved:
                    session.execute(
                        delete(RentalAllocation).where(
                            RentalAllocation.rental_id == rental.id
                        )
                    )
                    rental.state = "cancelled"
                rental.financial_version = payload.expected_financial_version or None
                rental.financial_snapshot = financial
                event = "cancelled" if payload.approved else "cancel_requested"
            else:
                assert isinstance(payload, ChangeCommand)
                if operation == "resume":
                    if (
                        not isinstance(payload, ResumptionCommand)
                        or not payload.payments_reviewed
                    ):
                        raise RentalError(
                            422,
                            "review_required",
                            "Confira explicitamente preços e aplicações "
                            "financeiras da revisão.",
                        )
                    if (rental and rental.state != "cancelled") or (
                        not rental
                        and not validity_state(old_offer.valid_until, self.clock())[
                            "expired"
                        ]
                    ):
                        raise RentalError(
                            409,
                            "invalid_state",
                            "Retome somente locação cancelada ou orçamento vencido. "
                            "Concluída exige nova proposta.",
                        )
                elif rental is None:
                    raise RentalError(404, "not_found", "Locação não encontrada.")
                proposal = self._proposal(session, header, rental, payload, locked=True)
                if proposal["catalog_versions"] != payload.catalog_versions:
                    raise RentalError(
                        409,
                        "catalog_conflict",
                        "O catálogo mudou. Consulte e faça nova prévia.",
                    )
                if operation == "change":
                    assert rental is not None
                    guard_change(rental.state, old_offer.snapshot, proposal)
                    if any(
                        row["shortage"]
                        for row in cast(list[dict[str, object]], proposal["capacity"])
                    ):
                        failure = RentalError(
                            409,
                            "capacity_conflict",
                            "Capacidade insuficiente. O compromisso "
                            "e a versão anteriores foram preservados.",
                            capacity=proposal["capacity"],
                        )
                event = "resumed" if operation == "resume" else "changed"
            if failure:
                result: dict[str, object] = {
                    "code": failure.code,
                    "detail": failure.message,
                    **failure.data,
                }
                status = 409
            else:
                if proposal is not None:
                    assert isinstance(payload, ChangeCommand)
                    if rental is None:
                        rental = Rental(
                            id=uuid4(),
                            quotation_id=header.id,
                            quotation_version=old_offer.number,
                            financial_version=payload.expected_financial_version
                            or None,
                            confirmation_deposit=old_offer.estimated_deposit,
                            version=1,
                            state="review",
                            commercial_snapshot=old_offer.snapshot,
                            financial_snapshot=financial,
                            actor_id=actor.user_id,
                            session_id=actor.session_id,
                            checked_at=self.clock(),
                        )
                    new_offer = QuotationService(
                        self.factory, self.clock
                    ).persist_revision(
                        session,
                        header,
                        payload.draft,
                        proposal,
                        actor,
                        number=header.current_version + 1,
                        reason=payload.reason,
                    )
                    reconciliation = (
                        ReconciliationCommand(
                            request_id=payload.request_id,
                            expected_quotation_version=new_offer.number,
                            expected_financial_version=payload.expected_financial_version,
                            applications=payload.applications,
                            reason=payload.reason,
                        )
                        if isinstance(payload, ResumptionCommand)
                        else None
                    )
                    revised = self.payments.revise_commercial(
                        session,
                        header,
                        new_offer,
                        financial,
                        actor,
                        payload.reason,
                        reconciliation,
                    )
                    if operation == "resume":
                        rental.state = "review"
                    rental.quotation_version = new_offer.number
                    rental.financial_version = int(str(revised["financial_version"]))
                    rental.commercial_snapshot = new_offer.snapshot
                    rental.financial_snapshot = revised
                    if operation == "change" and rental.state in {"confirmed", "out"}:
                        session.execute(
                            delete(RentalAllocation).where(
                                RentalAllocation.rental_id == rental.id
                            )
                        )
                        session.add_all(
                            [
                                RentalAllocation(
                                    rental_id=rental.id,
                                    product_id=pid,
                                    quantity=qty,
                                    pickup_date=new_offer.pickup_date,
                                    return_date=new_offer.return_date,
                                )
                                for pid, qty in snapshot_demand(
                                    new_offer.snapshot
                                ).items()
                            ]
                        )
                    if revised["requires_reconciliation"]:
                        record_pending(
                            session,
                            header.id,
                            new_offer.number,
                            "financial",
                            "rental:revision",
                            rental.financial_version,
                            {
                                "remaining": revised["remaining"],
                                "excess": revised["excess"],
                            },
                            actor,
                            self.clock(),
                        )
                assert rental is not None
                # New review headers are inserted as v1; existing headers advance.
                if "id" in before:
                    rental.version += 1
                rental.actor_id, rental.session_id = actor.user_id, actor.session_id
                rental.checked_at = self.clock()
                session.add(rental)
                session.flush()
                result = self._view(session, rental, header)
                session.add(
                    RentalHistory(
                        rental_id=rental.id,
                        version=rental.version,
                        operation=event,
                        reason=payload.reason,
                        before=before,
                        after=result,
                        actor_id=actor.user_id,
                        session_id=actor.session_id,
                        created_at=self.clock(),
                    )
                )
                status = 201
            session.add(
                RentalRequest(
                    actor_id=actor.user_id,
                    operation=op,
                    request_id=payload.request_id,
                    payload_hash=digest,
                    status=status,
                    result=result,
                )
            )
            session.commit()
        if failure:
            raise failure
        return result, False

    def copy_preview(
        self, identifier: UUID, payload: RentalVersions
    ) -> dict[str, object]:
        with session_scope(self.factory) as session:
            header, offer, rental, _ = self._context(
                session, identifier, payload, locked=False
            )
            if rental is None or rental.state != "completed":
                raise RentalError(
                    409,
                    "invalid_state",
                    "Somente locação concluída pode servir de referência "
                    "para uma nova proposta.",
                )
            draft = copy_draft(offer.snapshot, header.customer_id)
            return {
                "reference_rental_id": str(rental.id),
                "draft": draft.model_dump(mode="json"),
                "payments_transferred": "0.00",
                "readonly": True,
            }
