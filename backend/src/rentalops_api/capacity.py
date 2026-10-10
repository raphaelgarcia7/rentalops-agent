"""Daily capacity by simultaneous segments, shared by quotations and rentals."""

from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalops_api.catalog_models import Product
from rentalops_api.rental_models import RentalAllocation


def simultaneous_segments(
    intervals: list[tuple[date, date, int]], start: date, end: date
) -> list[tuple[date, date, int]]:
    """Closed dates; bounded sweep avoids iterating every day of long rentals."""
    events: dict[date, int] = defaultdict(int)
    events[start] = 0
    for pickup, returned, quantity in intervals:
        if pickup > end or returned < start:
            continue
        events[max(start, pickup)] += quantity
        if returned < end:
            events[returned + timedelta(days=1)] -= quantity
    dates = sorted(events)
    result = []
    committed = 0
    for index, day in enumerate(dates):
        committed += events[day]
        until = dates[index + 1] - timedelta(days=1) if index + 1 < len(dates) else end
        result.append((day, until, committed))
    return result


def capacity_view(
    session: Session,
    products: dict[UUID, Product],
    demand: dict[UUID, int],
    start: date,
    end: date,
    *,
    exclude_rental: UUID | None = None,
) -> list[dict[str, object]]:
    query = select(RentalAllocation).where(
        RentalAllocation.product_id.in_(demand),
        RentalAllocation.pickup_date <= end,
        RentalAllocation.return_date >= start,
    )
    if exclude_rental:
        query = query.where(RentalAllocation.rental_id != exclude_rental)
    intervals: dict[UUID, list[tuple[date, date, int]]] = defaultdict(list)
    for row in session.scalars(query):
        intervals[row.product_id].append(
            (row.pickup_date, row.return_date, row.quantity)
        )
    result: list[dict[str, object]] = []
    for pid, quantity in sorted(demand.items()):
        product = products[pid]
        apt = product.total_quantity - product.maintenance_quantity
        segments = simultaneous_segments(intervals[pid], start, end)
        committed = max(value for _, _, value in segments)
        available = max(0, apt - committed)
        result.append(
            {
                "product_id": str(pid),
                "name": product.name,
                "demand": quantity,
                "apt": apt,
                "committed": committed,
                "available": available,
                "shortage": max(0, quantity + committed - apt),
                "conflicts": [
                    {
                        "start": first.isoformat(),
                        "end": last.isoformat(),
                        "committed": count,
                        "available": max(0, apt - count),
                        "shortage": max(0, quantity + count - apt),
                    }
                    for first, last, count in segments
                    if quantity + count > apt
                ],
            }
        )
    return result
