"""Cross-module operational reads and issues within the caller's transaction."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from rentalops_api.auth import Identity
from rentalops_api.capacity import capacity_view
from rentalops_api.catalog_models import Product
from rentalops_api.rental_models import Rental, RentalAllocation, RentalPending


def rental_for_quotation(
    session: Session, identifier: UUID, *, locked: bool = False
) -> Rental | None:
    query = select(Rental).where(Rental.quotation_id == identifier)
    if locked:
        # A caller may have read the identity before waiting on quotation locks.
        # Refresh from the locked row, not the session's pre-lock identity map.
        query = query.with_for_update().execution_options(populate_existing=True)
    return session.scalar(query)


def pending_rows(session: Session, identifier: UUID) -> list[dict[str, object]]:
    rental = rental_for_quotation(session, identifier)
    confirmed = rental is not None and rental.state in {"confirmed", "out", "completed"}
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "source": row.source,
            "source_version": row.source_version,
            "details": row.details,
            "actor_id": str(row.actor_id),
            "created_at": row.created_at.isoformat(),
            "resolved": confirmed and row.source.startswith("confirmation:"),
        }
        for row in session.scalars(
            select(RentalPending)
            .where(RentalPending.quotation_id == identifier)
            .order_by(RentalPending.created_at, RentalPending.id)
        )
    ]


def rental_summary(session: Session, identifier: UUID) -> dict[str, object] | None:
    rental = rental_for_quotation(session, identifier)
    if rental is None:
        return None
    kinds = {
        row["kind"] for row in pending_rows(session, identifier) if not row["resolved"]
    }
    return {
        "id": str(rental.id),
        "version": rental.version,
        "state": rental.state,
        "inventory_pending": "inventory" in kinds,
        "financial_pending": "financial" in kinds,
    }


def record_pending(
    session: Session,
    identifier: UUID,
    quotation_version: int,
    kind: str,
    source: str,
    source_version: int,
    details: dict[str, object],
    actor: Identity,
    now: datetime | None = None,
) -> None:
    session.execute(
        insert(RentalPending)
        .values(
            quotation_id=identifier,
            quotation_version=quotation_version,
            kind=kind,
            source=source,
            source_version=source_version,
            details=details,
            actor_id=actor.user_id,
            session_id=actor.session_id,
            created_at=now or datetime.now(UTC),
        )
        .on_conflict_do_nothing(constraint="uq_rental_pending_origin")
    )


def record_inventory_impact(
    session: Session, product: Product, actor: Identity
) -> None:
    """Caller holds the product lock. Read immutable allocations, lock no header."""
    rows = session.execute(
        select(RentalAllocation, Rental)
        .join(Rental, Rental.id == RentalAllocation.rental_id)
        .where(RentalAllocation.product_id == product.id)
    ).all()
    for allocation, rental in rows:
        capacity = capacity_view(
            session,
            {product.id: product},
            {product.id: allocation.quantity},
            allocation.pickup_date,
            allocation.return_date,
            exclude_rental=rental.id,
        )
        if capacity[0]["shortage"]:
            record_pending(
                session,
                rental.quotation_id,
                rental.quotation_version,
                "inventory",
                f"product:{product.id}",
                product.version,
                {"capacity": capacity},
                actor,
            )
