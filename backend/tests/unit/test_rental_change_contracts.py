from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from rentalops_api.rental_changes import copy_draft, guard_cancellation, guard_change
from rentalops_api.rental_contracts import CancellationCommand, ResumptionCommand
from rentalops_api.rentals import RentalError


def snapshot():
    return {
        "customer_id": str(uuid4()),
        "pickup_date": "2026-10-10",
        "event_date": "2026-10-11",
        "return_date": "2026-10-13",
        "valid_until": "2026-10-09",
        "pickup_time": None,
        "event_time": None,
        "return_time": None,
        "total": "400.00",
        "lines": [
            {
                "id": str(uuid4()),
                "kind": "kit",
                "source_id": str(uuid4()),
                "quantity": 1,
                "unit_price": "400.00",
                "negotiation_reason": "Previous agreement",
                "items": [{"product_id": str(uuid4()), "quantity": 2}],
            }
        ],
    }


def test_future_persisted_out_context_preserves_products_dates_and_checks_extension():
    before = snapshot()
    price = {**before, "total": "500.00"}
    guard_change("out", before, price)
    guard_change("out", before, {**price, "return_date": "2026-10-14"})
    for field, value in [
        ("pickup_date", "2026-10-09"),
        ("event_date", "2026-10-12"),
        ("return_date", "2026-10-12"),
        ("lines", []),
    ]:
        with pytest.raises(RentalError) as error:
            guard_change("out", before, {**before, field: value})
        assert error.value.code == "already_out"
    for state in ("out", "completed"):
        with pytest.raises(RentalError) as error:
            guard_cancellation(state)
        assert error.value.code == "already_out"
    with pytest.raises(RentalError):
        guard_change("completed", before, price)


def test_completed_reference_draft_has_no_identity_price_or_money_transfer():
    before = snapshot()
    preserved = deepcopy(before)
    draft = copy_draft(before, uuid4())
    assert draft.quotation_id is None and draft.expected_version is None
    assert draft.lines[0].unit_price is None
    assert draft.lines[0].retained_line_id is None
    assert draft.lines[0].negotiation_reason is None
    assert draft.lines[0].items is None and draft.discount is None
    assert "payments" not in draft.model_dump()
    assert before == preserved


@pytest.mark.parametrize(
    "changes",
    [
        {"approved": "true"},
        {"reason": " "},
        {"expected_rental_version": True},
        {"actor_id": str(uuid4())},
    ],
)
def test_cancellation_inputs_are_strict_and_actor_cannot_be_supplied(changes):
    with pytest.raises(ValidationError):
        CancellationCommand.model_validate(
            {
                "request_id": str(uuid4()),
                "expected_rental_version": 1,
                "expected_quotation_version": 1,
                "expected_financial_version": 0,
                "reason": "Team decision",
                "approved": True,
                **changes,
            }
        )


def test_resumption_refuses_duplicate_origins_and_non_decimal_money():
    before = snapshot()
    draft = copy_draft(before, uuid4()).model_dump(mode="json")
    receipt_id = str(uuid4())
    payload = {
        "request_id": str(uuid4()),
        "expected_rental_version": 0,
        "expected_quotation_version": 1,
        "expected_financial_version": 0,
        "reason": "Explicit review",
        "payments_reviewed": True,
        "draft": draft,
        "catalog_versions": {"product:synthetic": 1},
        "applications": [
            {"receipt_id": receipt_id, "deposit": "100.00", "balance": "0.00"}
        ],
    }
    with pytest.raises(ValidationError):
        ResumptionCommand.model_validate(
            {**payload, "applications": payload["applications"] * 2}
        )
    with pytest.raises(ValidationError):
        ResumptionCommand.model_validate(
            {
                **payload,
                "applications": [
                    {"receipt_id": receipt_id, "deposit": 100.0, "balance": "0.00"}
                ],
            }
        )
