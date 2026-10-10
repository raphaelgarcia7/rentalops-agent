from uuid import UUID, uuid4

import pytest

from rentalops_api.main import app
from rentalops_api.rental_changes import RentalChangeService
from rentalops_api.rental_routes import rental_service

from .test_payment_api import HEADERS, login
from .test_payments import versions
from .test_rental_api import client as rental_client
from .test_rental_changes import change_command
from .test_rentals import paid

pytestmark = pytest.mark.integration


@pytest.fixture
def client(migrated_engine, tmp_path):
    original = rental_client.__wrapped__(migrated_engine, tmp_path)
    value = next(original)
    payments = value[1]
    service = RentalChangeService(payments[0].factory, payments[3][0].clock)
    app.dependency_overrides[rental_service] = lambda: service
    try:
        yield value, service
    finally:
        original.close()


def test_private_changes_versions_strict_origin_csrf_replay_history_and_no_logs(
    client, caplog
):
    (http, payments, _), service = client
    identifier = uuid4()
    paths = [
        f"/rentals/{identifier}/{operation}"
        for operation in (
            "change-preview",
            "changes",
            "cancellations",
            "resumptions",
            "copy-preview",
        )
    ]
    paths += [
        f"/quotations/{payments[2]}/resumption-preview",
        f"/quotations/{payments[2]}/resumptions",
    ]
    for path in paths:
        assert http.post(path, headers=HEADERS, json={}).status_code == 401
    login((http, payments, client[0][2]))
    for path in paths:
        for headers in ({}, {"Origin": "https://other.invalid"}):
            assert http.post(path, headers=headers, json={}).status_code == 403
    from rentalops_api.catalog_models import Product

    with service.factory.begin() as session:
        session.get(Product, payments[3][2]["vase"]).total_quantity = 6
    paid(payments)
    original = http.post(
        f"/quotations/{payments[2]}/confirm",
        headers=HEADERS,
        json=versions(payments[0], payments[2]),
    ).json()
    identifier = UUID(original["id"])
    payload = change_command((service, payments), original).model_dump(mode="json")
    path = f"/rentals/{identifier}/changes"
    for changes in (
        {"actor_id": str(uuid4())},
        {"expected_rental_version": True},
        {"reason": " "},
    ):
        assert (
            http.post(path, headers=HEADERS, json={**payload, **changes}).status_code
            == 422
        )
    assert (
        http.post(
            path, headers=HEADERS, json={**payload, "expected_financial_version": 999}
        ).status_code
        == 409
    )
    result = http.post(path, headers=HEADERS, json=payload)
    assert result.status_code == 201
    assert result.headers["Cache-Control"] == "no-store"
    assert result.json()["version"] == 2
    replay = http.post(path, headers=HEADERS, json=payload)
    assert replay.status_code == 200 and replay.json() == result.json()
    assert (
        http.post(
            path, headers=HEADERS, json={**payload, "reason": "Changed"}
        ).status_code
        == 409
    )
    assert (
        http.get(f"/rentals/{identifier}/history").json()["items"][1]["reason"]
        == payload["reason"]
    )
    assert (
        http.post(
            f"/rentals/{identifier}/copy-preview",
            headers=HEADERS,
            json={
                "expected_rental_version": 2,
                "expected_quotation_version": 2,
                "expected_financial_version": result.json()["current_financial"][
                    "financial_version"
                ],
            },
        ).status_code
        == 409
    )
    assert all(
        value not in caplog.text
        for value in (
            "Synthetic human agreement",
            "password",
            "receipt_id",
            "customer_id",
        )
    )
