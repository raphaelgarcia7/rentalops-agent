import logging
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from rentalops_api.auth import AuthService, AuthSettings
from rentalops_api.auth_routes import auth_service
from rentalops_api.main import app
from rentalops_api.quotation_models import QuotationAudit
from rentalops_api.quotation_routes import quotation_service

from .test_quotations import draft
from .test_quotations import quotations as quotation_fixture

pytestmark = pytest.mark.integration
ORIGIN = "http://localhost:5173"
HEADERS = {"Origin": ORIGIN}


@pytest.fixture
def quotations(migrated_engine):
    return quotation_fixture.__wrapped__(migrated_engine)


@pytest.fixture
def client(quotations):
    service, _, _ = quotations
    auth = AuthService(
        service.factory, AuthSettings(ORIGIN, False, "synthetic-quote-rate-key" * 3)
    )
    auth.create_user("synthetic-api@example.invalid")
    auth.set_password(
        auth.issue_link("synthetic-api@example.invalid", "access"),
        "synthetic quotation passphrase",
        "loopback",
    )
    app.dependency_overrides[auth_service] = lambda: auth
    app.dependency_overrides[quotation_service] = lambda: service
    try:
        with TestClient(app) as http:
            yield http, service
    finally:
        app.dependency_overrides.clear()


def login(http):
    result = http.post(
        "/auth/password/login",
        headers=HEADERS,
        json={
            "email": "synthetic-api@example.invalid",
            "password": "synthetic quotation passphrase",
        },
    )
    assert result.status_code == 200
    return result.json()


def test_real_auth_csrf_statuses_private_replay_and_actor(client, quotations):
    http, service = client
    body = draft(quotations).model_dump(mode="json")
    identifier = str(uuid4())
    for method, path in [
        ("POST", "/quotations/preview"),
        ("POST", "/quotations/search"),
        ("POST", "/quotations"),
        ("GET", f"/quotations/{identifier}"),
        ("GET", f"/quotations/{identifier}/versions"),
        ("GET", f"/quotations/{identifier}/versions/1"),
        ("POST", f"/quotations/{identifier}/versions"),
    ]:
        assert (
            http.request(
                method, path, headers=HEADERS, json=body if method == "POST" else None
            ).status_code
            == 401
        )
    identity = login(http)
    for path in (
        "/quotations/preview",
        "/quotations/search",
        "/quotations",
        f"/quotations/{identifier}/versions",
    ):
        for headers in ({}, {"Origin": "https://other.invalid"}):
            assert http.post(path, headers=headers, json=body).status_code == 403
    preview = http.post("/quotations/preview", headers=HEADERS, json=body)
    assert preview.status_code == 200 and preview.headers["Cache-Control"] == "no-store"
    write = {
        **body,
        "request_id": str(uuid4()),
        "catalog_versions": preview.json()["catalog_versions"],
    }
    result = http.post("/quotations", headers=HEADERS, json=write)
    assert result.status_code == 201
    saved = result.json()
    assert result.headers["Location"] == f"/quotations/{saved['id']}"
    assert (
        saved["actor_id"] == identity["user_id"]
        and saved["session_id"] == identity["session_id"]
    )
    repeated = http.post("/quotations", headers=HEADERS, json=write)
    assert repeated.status_code == 200 and repeated.json() == saved
    assert (
        http.post(
            "/quotations", headers=HEADERS, json={**write, "reason": "different"}
        ).status_code
        == 409
    )
    for path in (
        f"/quotations/{identifier}",
        f"/quotations/{identifier}/versions",
        f"/quotations/{saved['id']}/versions/999",
    ):
        assert http.get(path).status_code == 404
    assert http.get(f"/quotations/{saved['id']}").json()["version"] == 1
    assert http.get(f"/quotations/{saved['id']}/versions/1").status_code == 200
    assert len(http.get(f"/quotations/{saved['id']}/versions").json()) == 1
    assert (
        http.post(
            "/quotations/search",
            headers=HEADERS,
            json={"customer_id": saved["customer_id"]},
        ).json()["total"]
        == 1
    )
    with service.factory() as session:
        audit = session.scalar(select(QuotationAudit))
        assert audit.actor_id == uuid_from(identity["user_id"])


def uuid_from(value):
    from uuid import UUID

    return UUID(value)


def test_errors_no_input_echo_logs_sql_or_pii_and_body_search(
    client, quotations, caplog
):
    http, service = client
    login(http)
    for logger in ("rentalops_api", "uvicorn.access", "uvicorn.error"):
        caplog.set_level(logging.INFO, logger=logger)
    body = draft(quotations).model_dump(mode="json")
    sentinel = "PRIVATE_SYNTHETIC_DO_NOT_ECHO"
    for field in (
        "total",
        "actor_id",
        "session_id",
        "created_at",
        "version",
        "arbitrary",
    ):
        result = http.post(
            "/quotations/preview", headers=HEADERS, json={**body, field: sentinel}
        )
        assert result.status_code == 422 and sentinel not in result.text
        assert result.json()["fields"] == ["input"]
    for invalid in ({"page_size": 101}, {"page": True}, {"name": sentinel}):
        result = http.post("/quotations/search", headers=HEADERS, json=invalid)
        assert result.status_code == 422 and sentinel not in result.text
    assert (
        http.post(
            f"/quotations/search?name={sentinel}", headers=HEADERS, json={}
        ).status_code
        == 422
    )
    with patch.object(
        service,
        "preview",
        side_effect=OperationalError(sentinel, {}, Exception(sentinel)),
    ):
        result = http.post("/quotations/preview", headers=HEADERS, json=body)
    assert result.status_code == 503 and result.json() == {
        "detail": "Serviço indisponível."
    }
    assert sentinel not in result.text and sentinel not in caplog.text
