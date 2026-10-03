import logging
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from rentalops_api.auth import AuthService, AuthSettings
from rentalops_api.auth_routes import auth_service
from rentalops_api.customer_routes import customer_service
from rentalops_api.customers import CustomerService
from rentalops_api.database import build_session_factory
from rentalops_api.main import app

from ..unit.test_customer_contracts import synthetic_cpf

pytestmark = pytest.mark.integration
ORIGIN = "http://localhost:5173"
HEADERS = {"Origin": ORIGIN}
BASE = {"name": "Synthetic customer", "phone": "(11) 91234-5678"}


@pytest.fixture
def customer_client(migrated_engine):
    factory = build_session_factory(migrated_engine)
    auth = AuthService(
        factory, AuthSettings(ORIGIN, False, "synthetic-customer-rate-key" * 3)
    )
    for email in ("first@example.invalid", "second@example.invalid"):
        auth.create_user(email)
        auth.set_password(
            auth.issue_link(email, "access"), "synthetic customer phrase", "loopback"
        )
    service = CustomerService(factory)
    app.dependency_overrides[auth_service] = lambda: auth
    app.dependency_overrides[customer_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, service, auth
    finally:
        app.dependency_overrides.clear()


def login(client, email="first@example.invalid"):
    response = client.post(
        "/auth/password/login",
        headers=HEADERS,
        json={"email": email, "password": "synthetic customer phrase"},
    )
    assert response.status_code == 200
    return response.json()


def create(client, **fields):
    response = client.post("/customers", headers=HEADERS, json={**BASE, **fields})
    assert response.status_code == 201
    return response


def test_real_session_access_origin_and_server_actor(customer_client):
    client, _, _ = customer_client
    for method, path, payload in (
        ("POST", "/customers", BASE),
        ("POST", "/customers/search", {}),
        ("GET", f"/customers/{uuid4()}", None),
        ("PATCH", f"/customers/{uuid4()}", {"expected_version": 1}),
    ):
        response = client.request(method, path, headers=HEADERS, json=payload)
        assert response.status_code == 401
        assert "existing_ids" not in response.json()
    first = login(client)
    for origin in (None, "https://other.invalid"):
        for path in ("/customers", "/customers/search"):
            response = client.post(
                path,
                headers={} if origin is None else {"Origin": origin},
                json=BASE if path == "/customers" else {},
            )
            assert response.status_code == 403
    response = create(client)
    record = response.json()
    assert response.headers["Location"] == f"/customers/{record['id']}"
    assert record["created_by"] == first["user_id"]
    assert record["history"][0]["session_id"] == first["session_id"]
    second = login(client, "second@example.invalid")
    updated = client.patch(
        f"/customers/{record['id']}",
        headers=HEADERS,
        json={"expected_version": 1, "name": "Synthetic changed"},
    )
    assert updated.status_code == 200
    assert updated.json()["created_by"] == first["user_id"]
    assert updated.json()["updated_by"] == second["user_id"]
    assert updated.json()["history"][-1]["actor_id"] == second["user_id"]
    assert client.delete(f"/customers/{record['id']}").status_code == 405


def test_secure_invalid_missing_extra_inputs_field_errors_no_echo(
    customer_client, caplog
):
    for logger in ("rentalops_api", "uvicorn.access", "uvicorn.error"):
        caplog.set_level(logging.INFO, logger=logger)
    client, _, _ = customer_client
    login(client)
    document = synthetic_cpf()
    for field in (
        "id",
        "created_by",
        "updated_by",
        "actor_id",
        "created_at",
        "updated_at",
        "version",
        "cnpj",
    ):
        response = client.post(
            "/customers", headers=HEADERS, json={**BASE, field: document}
        )
        assert response.status_code == 422 and document not in response.text
    response = client.post(
        "/customers", headers=HEADERS, json={**BASE, "cpf": document[:-1] + "0"}
    )
    assert response.status_code == 422 and response.json()["fields"] == ["cpf"]
    assert document[:-1] not in response.text
    for payload in ({}, {"name": "Synthetic"}, {"phone": BASE["phone"]}):
        assert (
            client.post("/customers", headers=HEADERS, json=payload).status_code == 422
        )
    for payload in (
        {"page_size": 101},
        {"page": 0},
        {"phone": "invalid"},
        {"cpf": "invalid"},
        {"page_size": "25"},
    ):
        assert (
            client.post("/customers/search", headers=HEADERS, json=payload).status_code
            == 422
        )
    url_response = client.post(
        "/customers/search", params={"cpf": document}, headers=HEADERS, json={}
    )
    assert url_response.status_code == 422 and document not in url_response.text
    assert document not in caplog.text and BASE["phone"] not in caplog.text


def test_shared_contact_cpf_conflicts_drafts_versions_and_generic_errors(
    customer_client, caplog
):
    for logger in ("rentalops_api", "uvicorn.access", "uvicorn.error"):
        caplog.set_level(logging.INFO, logger=logger)
    client, service, _ = customer_client
    login(client)
    first = create(client, cpf=synthetic_cpf()).json()
    shared = client.post(
        "/customers", headers=HEADERS, json={**BASE, "name": "Distinct"}
    )
    assert shared.status_code == 409 and shared.json()["code"] == "shared_contact"
    assert shared.json()["existing_ids"] == [first["id"]]
    second = create(
        client,
        name="Distinct",
        acknowledged_shared_contact=shared.json()["existing_ids"],
    ).json()
    assert second["id"] != first["id"]
    duplicate = client.post(
        "/customers",
        headers=HEADERS,
        json={**BASE, "phone": "(21) 91234-5678", "cpf": synthetic_cpf()},
    )
    assert duplicate.status_code == 409 and duplicate.json()["existing_ids"] == [
        first["id"]
    ]
    assert synthetic_cpf() not in duplicate.text
    repeated = client.patch(
        f"/customers/{second['id']}",
        headers=HEADERS,
        json={
            "expected_version": 1,
            "cpf": synthetic_cpf(),
            "notes": "Must not commit",
        },
    )
    assert repeated.status_code == 409 and repeated.json()["code"] == "duplicate_cpf"
    assert client.get(f"/customers/{second['id']}").json()["notes"] is None
    assert (
        client.patch(
            f"/customers/{first['id']}",
            headers=HEADERS,
            json={"expected_version": 1, "notes": "Synthetic saved"},
        ).status_code
        == 200
    )
    stale = client.patch(
        f"/customers/{first['id']}",
        headers=HEADERS,
        json={"expected_version": 1, "notes": "Do not overwrite"},
    )
    assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
    assert client.get(f"/customers/{uuid4()}").status_code == 404
    assert (
        client.patch(
            f"/customers/{uuid4()}", headers=HEADERS, json={"expected_version": 1}
        ).status_code
        == 404
    )
    with patch.object(
        service,
        "search",
        side_effect=OperationalError("Private SQL", {}, Exception("private payload")),
    ):
        failure = client.post("/customers/search", headers=HEADERS, json={})
    assert failure.status_code == 503 and failure.json() == {
        "detail": "Serviço indisponível."
    }
    for response in (shared, duplicate, repeated, stale, failure):
        assert response.headers["cache-control"] == "no-store"
        assert (
            BASE["phone"] not in response.text and synthetic_cpf() not in response.text
        )
    assert synthetic_cpf() not in caplog.text and "Private SQL" not in caplog.text


def test_search_only_body_stable_pagination_and_private_responses(customer_client):
    client, _, _ = customer_client
    login(client)
    record = create(client, cpf=synthetic_cpf()).json()
    for filters in (
        {},
        {"name": "customer"},
        {"phone": "+55 11 91234-5678"},
        {"cpf": synthetic_cpf()},
    ):
        response = client.post("/customers/search", headers=HEADERS, json=filters)
        assert response.status_code == 200
        assert response.json()["items"][0]["id"] == record["id"]
        assert set(response.json()["items"][0]) == {"id", "name", "phone", "version"}
        assert response.json()["page_size"] == 25
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
    assert (
        client.post("/customers/search", headers=HEADERS, json={"page": 2}).json()[
            "items"
        ]
        == []
    )
    assert client.get("/customers").status_code == 405
    assert not any("__test" in path for path in app.openapi()["paths"])
