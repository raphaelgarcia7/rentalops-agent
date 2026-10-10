"""Quotation use cases: deterministic snapshots, revisions and safe replay."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from rentalops_api.auth import Identity
from rentalops_api.capacity import capacity_view
from rentalops_api.catalog_contracts import MAX_QUANTITY, aggregate_items
from rentalops_api.catalog_models import Kit, KitItem, Product
from rentalops_api.customer_models import Customer
from rentalops_api.database import session_scope
from rentalops_api.quotation_contracts import (
    SAO_PAULO,
    QuotationDraft,
    QuotationSearch,
    QuotationWrite,
    commercial_totals,
    next_planning_day,
    validity_state,
)
from rentalops_api.quotation_models import (
    Quotation,
    QuotationAudit,
    QuotationComponent,
    QuotationLine,
    QuotationRequest,
    QuotationVersion,
)
from rentalops_api.rental_effects import rental_for_quotation, rental_summary


class QuotationError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def invalid(message: str) -> QuotationError:
    return QuotationError(422, "invalid_offer", message)


def conflict(code: str = "version_conflict") -> QuotationError:
    return QuotationError(
        409,
        code,
        "Os dados mudaram. Consulte a versão atual e faça nova prévia; "
        "seu rascunho foi mantido.",
    )


class QuotationService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.factory = factory
        self.clock = clock or (lambda: datetime.now(UTC))

    def _quotation(
        self, session: Session, identifier: UUID, locked: bool = False
    ) -> Quotation:
        query = select(Quotation).where(Quotation.id == identifier)
        if locked:
            query = query.with_for_update()
        result = session.scalar(query)
        if result is None:
            raise QuotationError(404, "not_found", "Orçamento não encontrado.")
        return result

    def _resolve(
        self,
        session: Session,
        payload: QuotationDraft,
        *,
        rental_id: UUID | None = None,
        exclusive_products: bool = False,
    ) -> dict[str, object]:
        if session.get(Customer, payload.customer_id) is None:
            raise QuotationError(404, "customer_not_found", "Cliente não encontrado.")
        old_lines: dict[UUID, QuotationLine] = {}
        if payload.quotation_id:
            header = self._quotation(session, payload.quotation_id)
            rental = rental_for_quotation(session, header.id)
            if rental is not None and rental.id != rental_id:
                raise QuotationError(
                    409,
                    "already_confirmed",
                    "Reserva confirmada. A revisão comercial exige o fluxo "
                    "de alteração da locação, previsto na entrega #13.",
                )
            if header.customer_id != payload.customer_id:
                raise invalid("O cliente vinculado ao orçamento não pode ser trocado.")
            if header.current_version != payload.expected_version:
                raise conflict()
            old_lines = {
                line.id: line
                for line in session.scalars(
                    select(QuotationLine).where(
                        QuotationLine.quotation_id == header.id,
                        QuotationLine.version == header.current_version,
                    )
                )
            }
        # Match catalog lock order: kits first, then their actual products.
        # Shared locks permit parallel quotations without permitting a stale write.
        kit_ids = {line.source_id for line in payload.lines if line.kind == "kit"}
        kits = {
            k.id: k
            for k in session.scalars(
                select(Kit)
                .where(Kit.id.in_(kit_ids))
                .order_by(Kit.id)
                .with_for_update(read=True)
            )
        }
        kit_items: dict[UUID, dict[UUID, int]] = {}
        for item in session.scalars(select(KitItem).where(KitItem.kit_id.in_(kit_ids))):
            kit_items.setdefault(item.kit_id, {})[item.product_id] = item.quantity
        product_ids = {
            line.source_id for line in payload.lines if line.kind == "product"
        }
        product_ids.update(pid for items in kit_items.values() for pid in items)
        product_ids.update(
            item.product_id for line in payload.lines for item in line.items or []
        )
        for line in old_lines.values():
            product_ids.update(
                UUID(str(item["product_id"]))
                for item in cast(list[dict[str, object]], line.snapshot["items"])
            )
        products = {
            p.id: p
            for p in session.scalars(
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update(read=not exclusive_products)
            )
        }
        versions: dict[str, int] = {}
        resolved: list[dict[str, object]] = []
        demand: dict[UUID, int] = {}
        for entry in payload.lines:
            source = (
                products.get(entry.source_id)
                if entry.kind == "product"
                else kits.get(entry.source_id)
            )
            if source is None:
                raise invalid("Item do catálogo não encontrado.")
            if not source.is_active:
                raise invalid("Substitua o item inativo antes de salvar.")
            versions[f"{entry.kind}:{source.id}"] = source.version
            original = (
                old_lines.get(entry.retained_line_id)
                if entry.retained_line_id
                else None
            )
            if entry.retained_line_id and original is None:
                raise invalid("Linha preservada não pertence à revisão vigente.")
            if (
                original
                and (
                    original.product_id if entry.kind == "product" else original.kit_id
                )
                != source.id
            ):
                raise invalid(
                    "A origem da linha preservada não pode ser "
                    "substituída silenciosamente."
                )
            standard = (
                {source.id: 1}
                if entry.kind == "product"
                else kit_items.get(source.id, {})
            )
            if not standard or any(not products[pid].is_active for pid in standard):
                raise invalid(
                    "O kit precisa de revisão no catálogo: "
                    "substitua os componentes inativos."
                )
            old_snapshot = original.snapshot if original else None
            old_components = (
                {
                    UUID(str(item["product_id"])): int(str(item["quantity"]))
                    for item in cast(list[dict[str, object]], old_snapshot["items"])
                }
                if old_snapshot
                else standard
            )
            components = (
                aggregate_items(entry.items)
                if entry.items is not None
                else old_components
            )
            price = (
                entry.unit_price
                if entry.unit_price is not None
                else original.unit_price
                if original
                else source.price
            )
            base_price = original.unit_price if original else source.price
            customized = components != old_components
            negotiated = price != base_price or customized
            if customized and entry.kind == "kit" and entry.unit_price is None:
                raise invalid("Defina explicitamente o preço do kit personalizado.")
            if negotiated and not entry.negotiation_reason:
                raise invalid("Preço ou composição negociada exige motivo.")
            items: list[dict[str, object]] = []
            for pid, quantity in sorted(components.items()):
                product = products.get(pid)
                if product is None or not product.is_active:
                    raise invalid(
                        "Substitua o produto inexistente ou inativo da composição."
                    )
                versions[f"product:{pid}"] = product.version
                demand[pid] = demand.get(pid, 0) + quantity * entry.quantity
                if demand[pid] > MAX_QUANTITY:
                    raise invalid("A demanda excede o limite de quantidade.")
                old_item = (
                    next(
                        (
                            item
                            for item in cast(
                                list[dict[str, object]], old_snapshot["items"]
                            )
                            if item["product_id"] == str(pid)
                        ),
                        None,
                    )
                    if old_snapshot and not customized
                    else None
                )
                items.append(
                    {
                        "product_id": str(pid),
                        "quantity": quantity,
                        "name": old_item["name"] if old_item else product.name,
                        "source_version": old_item["source_version"]
                        if old_item
                        else product.version,
                    }
                )
            resolved.append(
                {
                    "kind": entry.kind,
                    "source_id": str(source.id),
                    "quantity": entry.quantity,
                    "unit_price": format(price, ".2f"),
                    "name": old_snapshot["name"] if old_snapshot else source.name,
                    "source_version": original.source_version
                    if original
                    else source.version,
                    "items": items,
                    "negotiation_reason": entry.negotiation_reason
                    or (
                        old_snapshot.get("negotiation_reason") if old_snapshot else None
                    ),
                }
            )
        try:
            totals = commercial_totals(
                [
                    (int(str(line["quantity"])), Decimal(str(line["unit_price"])))
                    for line in resolved
                ],
                payload.discount,
            )
        except ValueError:
            raise invalid(
                "Confira os valores: total mínimo R$ 0,01 e limites monetários."
            ) from None
        snapshot = payload.model_dump(
            mode="json", exclude={"lines", "quotation_id", "expected_version"}
        )
        # Write subclasses must not leak replay data into the commercial snapshot.
        for key in ("request_id", "catalog_versions", "reason"):
            snapshot.pop(key, None)
        snapshot.update(
            {
                "lines": resolved,
                "catalog_versions": versions,
                **totals,
                "planning_available_from": next_planning_day(
                    payload.return_date
                ).isoformat(),
            }
        )
        capacity = self._capacity(
            session,
            products,
            demand,
            payload.pickup_date,
            payload.return_date,
            exclude_rental=rental_id,
        )
        return {
            **snapshot,
            **validity_state(payload.valid_until, self.clock()),
            "capacity": capacity,
            "capacity_mode": "simultaneous_allocations",
            "capacity_checked_at": self.clock().isoformat(),
            "stock_pending": any(item["shortage"] for item in capacity),
        }

    def _capacity(
        self,
        session: Session,
        products: dict[UUID, Product],
        demand: dict[UUID, int],
        start: date,
        end: date,
        exclude_rental: UUID | None = None,
    ) -> list[dict[str, object]]:
        return capacity_view(
            session, products, demand, start, end, exclude_rental=exclude_rental
        )

    def preview(self, payload: QuotationDraft) -> dict[str, object]:
        with session_scope(self.factory) as session:
            return self._resolve(session, payload)

    def write(
        self, payload: QuotationWrite, actor: Identity, identifier: UUID | None = None
    ) -> tuple[dict[str, object], bool]:
        if identifier is None and (
            payload.quotation_id
            or payload.expected_version
            or any(line.retained_line_id for line in payload.lines)
        ):
            raise invalid("Nova proposta não pode declarar uma revisão existente.")
        if identifier is not None and (
            payload.quotation_id != identifier
            or not payload.expected_version
            or not payload.reason
        ):
            raise invalid("Informe a revisão vigente e o motivo da nova versão.")
        operation = "create" if identifier is None else f"revise:{identifier}"
        digest = hashlib.sha256(
            json.dumps(
                payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        key = int.from_bytes(
            hashlib.sha256(
                f"{actor.user_id}:{operation}:{payload.request_id}".encode()
            ).digest()[:8],
            "big",
            signed=True,
        )
        with session_scope(self.factory) as session:
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            replay = session.get(
                QuotationRequest, (actor.user_id, operation, payload.request_id)
            )
            if replay:
                if replay.payload_hash != digest:
                    raise conflict("idempotency_conflict")
                return replay.result, True
            header = (
                self._quotation(session, identifier, True)
                if identifier
                else Quotation(
                    id=uuid4(),
                    customer_id=payload.customer_id,
                    current_version=1,
                    created_at=self.clock(),
                )
            )
            if identifier and header.current_version != payload.expected_version:
                raise conflict()
            if (
                identifier
                and rental_for_quotation(session, header.id, locked=True) is not None
            ):
                raise QuotationError(
                    409,
                    "already_confirmed",
                    "Reserva confirmada. A revisão comercial exige o fluxo "
                    "de alteração da locação, previsto na entrega #13.",
                )
            snapshot = self._resolve(session, payload)
            if snapshot["catalog_versions"] != payload.catalog_versions:
                raise conflict("catalog_conflict")
            number = header.current_version + 1 if identifier else 1
            version = self.persist_revision(
                session,
                header,
                payload,
                snapshot,
                actor,
                number=number,
                reason=payload.reason,
            )
            result = self._view(session, header, version)
            session.add(
                QuotationRequest(
                    actor_id=actor.user_id,
                    operation=operation,
                    request_id=payload.request_id,
                    payload_hash=digest,
                    quotation_id=header.id,
                    version=number,
                    result=result,
                )
            )
            session.commit()
            return result, False

    def persist_revision(
        self,
        session: Session,
        header: Quotation,
        payload: QuotationDraft,
        snapshot: dict[str, object],
        actor: Identity,
        *,
        number: int,
        reason: str | None,
    ) -> QuotationVersion:
        """Persist a resolved snapshot inside the owning business transaction."""
        header.current_version = number
        session.add(header)
        session.flush()
        commercial = {
            key: value
            for key, value in snapshot.items()
            if key
            not in {
                "capacity",
                "capacity_mode",
                "capacity_checked_at",
                "stock_pending",
                "state",
                "expired",
                "requires_revision",
            }
        }
        lines = cast(list[dict[str, object]], commercial["lines"])
        for line in lines:
            line["id"] = str(uuid4())
        version = QuotationVersion(
            quotation_id=header.id,
            number=number,
            pickup_date=payload.pickup_date,
            event_date=payload.event_date,
            return_date=payload.return_date,
            valid_until=payload.valid_until,
            **{
                name: Decimal(str(snapshot[name]))
                for name in (
                    "subtotal",
                    "discount_amount",
                    "total",
                    "estimated_deposit",
                    "estimated_balance",
                )
            },
            snapshot=commercial,
            reason=reason,
            actor_id=actor.user_id,
            session_id=actor.session_id,
            created_at=self.clock(),
        )
        session.add(version)
        session.flush()
        for position, line in enumerate(lines):
            lid = UUID(str(line["id"]))
            session.add(
                QuotationLine(
                    id=lid,
                    quotation_id=header.id,
                    version=number,
                    position=position,
                    product_id=UUID(str(line["source_id"]))
                    if line["kind"] == "product"
                    else None,
                    kit_id=UUID(str(line["source_id"]))
                    if line["kind"] == "kit"
                    else None,
                    quantity=int(str(line["quantity"])),
                    unit_price=Decimal(str(line["unit_price"])),
                    source_version=int(str(line["source_version"])),
                    snapshot=line,
                )
            )
            session.flush()
            for component in cast(list[dict[str, object]], line["items"]):
                session.add(
                    QuotationComponent(
                        line_id=lid,
                        product_id=UUID(str(component["product_id"])),
                        quantity=int(str(component["quantity"])),
                        source_version=int(str(component["source_version"])),
                        source_name=str(component["name"]),
                    )
                )
        session.add(
            QuotationAudit(
                quotation_id=header.id,
                version=number,
                actor_id=actor.user_id,
                session_id=actor.session_id,
                operation="created" if number == 1 else "revised",
                changed_fields=["dates", "validity", "lines", "discount"],
                created_at=self.clock(),
            )
        )
        session.flush()
        return version

    def _view(
        self, session: Session, header: Quotation, version: QuotationVersion
    ) -> dict[str, object]:
        demand: dict[UUID, int] = {}
        for line in cast(list[dict[str, object]], version.snapshot["lines"]):
            for component in cast(list[dict[str, object]], line["items"]):
                pid = UUID(str(component["product_id"]))
                demand[pid] = demand.get(pid, 0) + int(
                    str(component["quantity"])
                ) * int(str(line["quantity"]))
        products = {
            p.id: p
            for p in session.scalars(select(Product).where(Product.id.in_(demand)))
        }
        rental = rental_summary(session, header.id)
        capacity = self._capacity(
            session,
            products,
            demand,
            version.pickup_date,
            version.return_date,
            UUID(str(rental["id"])) if rental else None,
        )
        return {
            **version.snapshot,
            "id": str(header.id),
            "customer_id": str(header.customer_id),
            "version": version.number,
            "current_version": header.current_version,
            "reason": version.reason,
            "actor_id": str(version.actor_id),
            "session_id": str(version.session_id),
            "created_at": header.created_at.isoformat(),
            "revised_at": version.created_at.isoformat(),
            **validity_state(version.valid_until, self.clock()),
            "capacity": capacity,
            "capacity_mode": "simultaneous_allocations",
            "capacity_checked_at": self.clock().isoformat(),
            "stock_pending": any(int(str(item["shortage"])) > 0 for item in capacity),
            "rental": rental,
        }

    def get(self, identifier: UUID, number: int | None = None) -> dict[str, object]:
        with session_scope(self.factory) as session:
            header = self._quotation(session, identifier)
            version = session.get(
                QuotationVersion,
                (identifier, header.current_version if number is None else number),
            )
            if version is None:
                raise QuotationError(404, "not_found", "Versão não encontrada.")
            return self._view(session, header, version)

    def versions(self, identifier: UUID) -> list[dict[str, object]]:
        with session_scope(self.factory) as session:
            header = self._quotation(session, identifier)
            return [
                self._view(session, header, version)
                for version in session.scalars(
                    select(QuotationVersion)
                    .where(QuotationVersion.quotation_id == identifier)
                    .order_by(QuotationVersion.number.desc())
                )
            ]

    def guard_current_validity(
        self, identifier: UUID, expected_version: int
    ) -> dict[str, object]:
        result = self.get(identifier)
        if result["version"] != expected_version:
            raise conflict()
        if result["expired"]:
            raise QuotationError(
                409, "expired", "Orçamento vencido: crie nova revisão antes de fechar."
            )
        return result

    def search(self, payload: QuotationSearch) -> dict[str, object]:
        with session_scope(self.factory) as session:
            filters = []
            for name in ("customer_id", "quotation_id"):
                value = getattr(payload, name)
                if value:
                    filters.append(
                        (
                            Quotation.customer_id
                            if name == "customer_id"
                            else Quotation.id
                        )
                        == value
                    )
            for name in ("pickup_date", "event_date", "return_date", "valid_until"):
                value = getattr(payload, name)
                if value:
                    filters.append(getattr(QuotationVersion, name) == value)
            if payload.state:
                today = self.clock().astimezone(SAO_PAULO).date()
                filters.append(
                    QuotationVersion.valid_until < today
                    if payload.state == "expired"
                    else QuotationVersion.valid_until >= today
                )
            query = (
                select(Quotation, QuotationVersion)
                .join(
                    QuotationVersion,
                    (QuotationVersion.quotation_id == Quotation.id)
                    & (QuotationVersion.number == Quotation.current_version),
                )
                .where(*filters)
            )
            total = (
                session.scalar(select(func.count()).select_from(query.subquery())) or 0
            )
            rows = session.execute(
                query.order_by(Quotation.created_at.desc(), Quotation.id)
                .offset((payload.page - 1) * payload.page_size)
                .limit(payload.page_size)
            )
            return {
                "items": [
                    self._view(session, header, version) for header, version in rows
                ],
                "total": total,
                "page": payload.page,
                "page_size": payload.page_size,
            }
