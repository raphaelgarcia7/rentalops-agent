from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from rentalops_api.payment_contracts import ReceiptCommand, ReconciliationCommand
from rentalops_api.quotation_contracts import SAO_PAULO


def receipt_body(**changes):
    return {
        "request_id": str(uuid4()),
        "expected_financial_version": 0,
        "expected_quotation_version": 1,
        "amount": "200.00",
        "method": "pix",
        "business_date": "2026-10-08",
        **changes,
    }


@pytest.mark.parametrize(
    "amount",
    [
        0,
        100.1,
        "1",
        "1.0",
        "1.001",
        "0.00",
        "-1.00",
        "NaN",
        "Infinity",
        "10000000000.00",
        "1e2",
    ],
)
def test_exact_positive_money_contract(amount):
    with pytest.raises(ValidationError):
        ReceiptCommand.model_validate(receipt_body(amount=amount))


@pytest.mark.parametrize(
    "changes",
    [
        {"actor_id": str(uuid4())},
        {"method": "bank"},
        {"expected_financial_version": True},
        {"expected_financial_version": -1},
        {"expected_quotation_version": "1"},
        {"request_id": "invalid"},
        {"business_date": "08/10/2026"},
        {"observation": "x" * 2001},
    ],
)
def test_extra_fields_strict_versions_dates_uuid_and_limits(changes):
    with pytest.raises(ValidationError):
        ReceiptCommand.model_validate(receipt_body(**changes))


def test_business_date_cannot_be_future_and_maximum_is_exact():
    future = datetime.now(UTC).astimezone(SAO_PAULO).date() + timedelta(days=1)
    with pytest.raises(ValidationError):
        ReceiptCommand.model_validate(receipt_body(business_date=future.isoformat()))
    assert (
        str(ReceiptCommand.model_validate(receipt_body(amount="9999999999.99")).amount)
        == "9999999999.99"
    )


def test_complete_distribution_unique_origin_and_reason():
    receipt = str(uuid4())
    body = {
        "request_id": str(uuid4()),
        "expected_financial_version": 1,
        "expected_quotation_version": 1,
        "reason": "Synthetic agreement",
        "applications": [
            {"receipt_id": receipt, "deposit": "200.00", "balance": "50.00"}
        ],
    }
    assert len(ReconciliationCommand.model_validate(body).applications) == 1
    for change in (
        {"applications": body["applications"] * 2},
        {"reason": "  "},
        {"reason": "x" * 1001},
    ):
        with pytest.raises(ValidationError):
            ReconciliationCommand.model_validate({**body, **change})
