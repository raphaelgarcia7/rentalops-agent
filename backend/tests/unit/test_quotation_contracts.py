from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from rentalops_api.quotation_contracts import (
    QuotationDiscount,
    QuotationDraft,
    QuotationSearch,
    commercial_totals,
    next_planning_day,
    validity_state,
)


def draft(**changes):
    return QuotationDraft.model_validate(
        {
            "customer_id": str(uuid4()),
            "pickup_date": "2026-10-10",
            "event_date": "2026-10-11",
            "return_date": "2026-10-13",
            "valid_until": "2026-10-09",
            "lines": [{"kind": "product", "source_id": str(uuid4()), "quantity": 1}],
            **changes,
        }
    )


@pytest.mark.parametrize(
    "price,kind,value,total,deposit,balance",
    [
        ("400.00", "amount", "40.00", "360.00", "180.00", "180.00"),
        ("400.00", "percent", "10", "360.00", "180.00", "180.00"),
        ("100.01", "amount", "0", "100.01", "50.01", "50.00"),
        ("0.05", "percent", "10", "0.04", "0.02", "0.02"),
        ("0.01", "amount", "0", "0.01", "0.01", "0.00"),
    ],
)
def test_exact_totals(price, kind, value, total, deposit, balance):
    result = commercial_totals(
        [(1, Decimal(price))],
        QuotationDiscount(
            kind=kind, value=value, reason="Synthetic negotiated discount"
        ),
    )
    assert result["total"] == total
    assert result["estimated_deposit"] == deposit
    assert result["estimated_balance"] == balance
    assert Decimal(deposit) + Decimal(balance) == Decimal(total)


@pytest.mark.parametrize(
    "value", [-1, 1.0, "NaN", "Infinity", "-0.01", "1.001", "100.01"]
)
def test_invalid_percent(value):
    with pytest.raises(ValidationError):
        QuotationDiscount(kind="percent", value=value, reason="Synthetic")


@pytest.mark.parametrize(
    "price,quantity,kind,value",
    [
        ("0", 1, "amount", "0"),
        ("1", 1, "amount", "2"),
        ("1", 1, "percent", "100"),
        ("9999999999.99", 2, "amount", "0"),
    ],
)
def test_total_zero_discount_excess_and_overflow(price, quantity, kind, value):
    with pytest.raises(ValueError):
        commercial_totals(
            [(quantity, Decimal(price))],
            QuotationDiscount(kind=kind, value=value, reason="Synthetic"),
        )


def test_reason_single_discount_internal_fields_and_limits():
    with pytest.raises(ValidationError):
        QuotationDiscount(kind="amount", value="1")
    with pytest.raises(ValidationError):
        draft(total="2.00")
    with pytest.raises(ValidationError):
        draft(
            discount={
                "kind": "percent",
                "value": "10",
                "reason": "Synthetic",
                "amount": "2",
            }
        )
    for quantity in (0, -1, True, 1.0, 2147483648):
        with pytest.raises(ValidationError):
            draft(
                lines=[
                    {"kind": "product", "source_id": str(uuid4()), "quantity": quantity}
                ]
            )
    with pytest.raises(ValidationError):
        draft(lines=[])
    with pytest.raises(ValidationError):
        draft(
            lines=[{"kind": "product", "source_id": str(uuid4()), "quantity": 1}] * 1001
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"pickup_date": "2026-10-12"},
        {"return_date": "2026-10-10"},
        {"valid_until": "2026-10-11"},
        {"pickup_date": "10/10/2026"},
        {"event_date": "2026-10-10T00:00:00Z"},
        {"pickup_time": "12:30:00"},
        {"event_time": "25:00"},
        {"event_time": time(12, 30, 15)},
        {"return_date": "9999-12-31"},
        {
            "event_date": "2026-10-10",
            "return_date": "2026-10-10",
            "pickup_time": "13:00",
            "return_time": "12:00",
        },
    ],
)
def test_date_and_time_contract(changes):
    with pytest.raises(ValidationError):
        draft(**changes)


def test_same_day_optional_times_local_inclusive_validity_and_return_day():
    result = draft(
        event_date="2026-10-10",
        return_date="2026-10-10",
        valid_until="2026-10-10",
        pickup_time="12:00",
        return_time="12:00",
    )
    assert result.event_time is None
    assert result.model_dump(mode="json")["pickup_time"] == "12:00"
    assert QuotationDraft.model_validate(result.model_dump(mode="json")) == result
    assert (
        validity_state(
            result.valid_until, datetime(2026, 10, 11, 2, 59, 59, tzinfo=UTC)
        )["state"]
        == "current"
    )
    assert (
        validity_state(result.valid_until, datetime(2026, 10, 11, 3, tzinfo=UTC))[
            "requires_revision"
        ]
        is True
    )
    assert next_planning_day(date(2026, 10, 13)) == date(2026, 10, 14)
    with pytest.raises(ValueError):
        validity_state(result.valid_until, datetime(2026, 10, 10))


@pytest.mark.parametrize(
    "changes", [{"page": 0}, {"page": True}, {"page_size": 101}, {"name": "private"}]
)
def test_search_limits_and_private_filter_rejection(changes):
    with pytest.raises(ValidationError):
        QuotationSearch.model_validate(changes)
