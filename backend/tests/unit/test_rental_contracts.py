from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from rentalops_api.capacity import simultaneous_segments
from rentalops_api.rental_contracts import ConfirmationCommand


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_quotation_version", True),
        ("expected_quotation_version", 0),
        ("expected_financial_version", "1"),
        ("expected_financial_version", -1),
        ("actor_id", str(uuid4())),
        ("state", "confirmed"),
    ],
)
def test_confirmation_contract_rejects_untrusted_authority(field, value):
    payload = {
        "request_id": str(uuid4()),
        "expected_quotation_version": 1,
        "expected_financial_version": 2,
        field: value,
    }
    with pytest.raises(ValidationError):
        ConfirmationCommand.model_validate(payload)


def test_segments_compare_simultaneous_commitments_and_closed_dates():
    day = lambda value: date(2026, 10, value)  # noqa: E731
    intervals = [
        (day(10), day(13), 2),
        (day(14), day(16), 2),
        (day(13), day(14), 1),
        (day(20), day(21), 99),
    ]
    assert simultaneous_segments(intervals, day(10), day(16)) == [
        (day(10), day(12), 2),
        (day(13), day(13), 3),
        (day(14), day(14), 3),
        (day(15), day(16), 2),
    ]


def test_calendar_next_day_includes_weekend_and_holiday():
    from rentalops_api.quotation_contracts import next_planning_day

    assert next_planning_day(date(2026, 10, 11)) == date(2026, 10, 12)
    assert next_planning_day(date(2026, 10, 12)) == date(2026, 10, 13)
