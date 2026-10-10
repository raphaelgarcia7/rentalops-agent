from uuid import UUID, uuid4

import pytest

from rentalops_api.catalog_models import Product
from rentalops_api.main import app
from rentalops_api.quotation_routes import quotation_service
from rentalops_api.rental_routes import rental_service
from rentalops_api.rentals import RentalService

from .test_payment_api import HEADERS, login
from .test_payment_api import client as payment_client
from .test_payments import allocation, receive, reconcile, versions
from .test_quotations import draft

pytestmark = pytest.mark.integration


@pytest.fixture
def client(migrated_engine, tmp_path):
    original = payment_client.__wrapped__(migrated_engine, tmp_path)
    value = next(original)
    payments = value[1]
    quote = payments[3][0]
    payments[0].clock = quote.clock
    app.dependency_overrides[rental_service] = lambda: RentalService(
        quote.factory, quote.clock
    )
    app.dependency_overrides[quotation_service] = lambda: quote
    try:
        yield value
    finally:
        original.close()


def test_every_operational_route_session_origin_version_private_history_and_privacy(
    client, caplog
):
    http, payments, _ = client
    identifier = payments[2]
    base = f"/quotations/{identifier}"
    preview = base + "/confirmation-preview"
    confirm = base + "/confirm"
    paths = [
        f"/rentals/{uuid4()}",
        f"/rentals/{uuid4()}/history",
        f"/rentals/by-quotation/{identifier}",
    ]
    for path in paths:
        assert http.get(path).status_code == 401
    for path in (preview, confirm):
        assert http.post(path, headers=HEADERS, json={}).status_code == 401
    login(client)
    for path in (preview, confirm):
        for headers in ({}, {"Origin": "https://other.invalid"}):
            assert http.post(path, headers=headers, json={}).status_code == 403
    received = receive(payments)
    reconcile(payments, [allocation(received)])
    payload = versions(payments[0], identifier)
    fields = {key: value for key, value in payload.items() if key != "request_id"}
    result = http.post(preview, headers=HEADERS, json=fields)
    assert result.status_code == 200 and result.json()["deposit_valid"]
    assert result.json()["pending"]
    assert result.headers["Cache-Control"] == "no-store"
    failed = http.post(confirm, headers=HEADERS, json=payload)
    assert failed.status_code == 409 and failed.json()["code"] == "capacity_conflict"
    assert failed.json()["capacity"][0]["conflicts"] is not None
    assert "customer_id" not in str(failed.json())
    with payments[0].factory.begin() as session:
        session.get(Product, payments[3][2]["vase"]).total_quantity = 6
    payload = versions(payments[0], identifier)
    result = http.post(confirm, headers=HEADERS, json=payload)
    assert result.status_code == 201
    rental = result.json()
    availability = http.post(
        "/quotations/preview",
        headers=HEADERS,
        json=draft(payments[3]).model_dump(mode="json"),
    )
    assert availability.status_code == 200
    assert sorted(row["committed"] for row in availability.json()["capacity"]) == [2, 5]
    assert all(row["available"] == 0 for row in availability.json()["capacity"])
    assert http.post(confirm, headers=HEADERS, json=payload).json() == rental
    assert http.post(confirm, headers=HEADERS, json=payload).status_code == 200
    assert (
        http.post(
            confirm, headers=HEADERS, json={**payload, "expected_financial_version": 99}
        ).status_code
        == 409
    )
    assert http.get(f"/rentals/{rental['id']}").json() == rental
    assert http.get(f"/rentals/by-quotation/{identifier}").json() == rental
    history = http.get(f"/rentals/{rental['id']}/history?page=1&page_size=1")
    assert history.status_code == 200 and history.json()["total"] == 1
    assert history.headers["Cache-Control"] == "no-store"
    assert http.get(f"/rentals/{rental['id']}/history?page_size=101").status_code == 422
    for path in paths:
        if str(identifier) not in path:
            assert http.get(path).status_code == 404
    assert http.get(f"/rentals/by-quotation/{uuid4()}").status_code == 404
    assert (
        http.post(
            preview, headers=HEADERS, json={**fields, "expected_quotation_version": 99}
        ).status_code
        == 409
    )
    assert (
        http.post(
            preview, headers=HEADERS, json={**fields, "actor_id": str(uuid4())}
        ).status_code
        == 422
    )
    summaries = http.post(
        "/quotations/search",
        headers=HEADERS,
        json={"customer_id": str(payments[3][2]["customer"])},
    )
    assert summaries.json()["items"][0]["rental"]["id"] == rental["id"]
    assert UUID(rental["id"])
    assert all(
        value not in caplog.text
        for value in ("password", "receipt", "synthetic-payments-api")
    )
