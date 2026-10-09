from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from rentalops_api.auth import AuthService, AuthSettings
from rentalops_api.auth_routes import auth_service
from rentalops_api.main import app
from rentalops_api.payment_routes import payment_service

from ..unit.test_payment_storage import pdf
from .test_payments import payments as payment_fixture
from .test_payments import versions
from .test_quotations import create

pytestmark = pytest.mark.integration
ORIGIN = "http://localhost:5173"
HEADERS = {"Origin": ORIGIN}


@pytest.fixture
def client(migrated_engine, tmp_path):
    payments = payment_fixture.__wrapped__(migrated_engine, tmp_path)
    service = payments[0]
    auth = AuthService(
        service.factory, AuthSettings(ORIGIN, False, "synthetic-financial-api-key" * 3)
    )
    email = "synthetic-payments-api@example.invalid"
    auth.create_user(email)
    auth.set_password(
        auth.issue_link(email, "access"), "synthetic financial passphrase", "loopback"
    )
    app.dependency_overrides[auth_service] = lambda: auth
    app.dependency_overrides[payment_service] = lambda: service
    try:
        with TestClient(app) as http:
            yield http, payments, email
    finally:
        app.dependency_overrides.clear()


def login(client):
    http, _, email = client
    result = http.post(
        "/auth/password/login",
        headers=HEADERS,
        json={"email": email, "password": "synthetic financial passphrase"},
    )
    assert result.status_code == 200
    return result.json()


def test_all_routes_require_session_origin_and_private_responses(client):
    http, payments, _ = client
    service, _, identifier, *_ = payments
    base = f"/quotations/{identifier}/payments"
    receipt, proof = uuid4(), uuid4()
    paths = [
        base + "/receipts",
        base + f"/receipts/{receipt}/corrections",
        base + "/reconciliations",
        base + "/refunds",
        base + f"/receipts/{receipt}/proofs",
    ]
    for path in [base, base + "/history", base + f"/proofs/{proof}/download"]:
        assert http.get(path).status_code == 401
    for path in paths:
        assert http.post(path, headers=HEADERS, json={}).status_code == 401
    identity = login(client)
    for path in paths:
        for headers in ({}, {"Origin": "https://other.invalid"}):
            assert http.post(path, headers=headers, json={}).status_code == 403
    body = versions(
        service,
        identifier,
        amount="250.00",
        method="pix",
        business_date="2026-10-08",
        observation="Synthetic private observation",
    )
    result = http.post(base + "/receipts", headers=HEADERS, json=body)
    assert result.status_code == 200 and result.headers["Cache-Control"] == "no-store"
    state = result.json()
    assert state["receipts"][0]["actor_id"] == identity["user_id"]
    assert state["receipts"][0]["session_id"] == identity["session_id"]
    assert not state["deposit_validated"] and state["pending"] == "250.00"
    assert http.post(base + "/receipts", headers=HEADERS, json=body).json() == state
    assert (
        http.post(
            base + "/receipts", headers=HEADERS, json={**body, "amount": "251.00"}
        ).status_code
        == 409
    )
    reconcile = versions(
        service,
        identifier,
        applications=[
            {
                "receipt_id": state["receipts"][0]["id"],
                "deposit": "200.00",
                "balance": "50.00",
            }
        ],
        reason="Synthetic explicit conference",
    )
    result = http.post(base + "/reconciliations", headers=HEADERS, json=reconcile)
    assert result.status_code == 200 and result.json()["balance_remaining"] == "150.00"
    assert http.get(base + "/history").json()["total"] == 2
    assert http.get(base + "/history?page_size=101").status_code == 422
    assert http.get(f"/quotations/{uuid4()}/payments").status_code == 404


def test_private_proof_download_content_replay_alien_link_and_upload_limits(
    client, caplog
):
    http, payments, _ = client
    service, _, identifier, quotations, _ = payments
    login(client)
    base = f"/quotations/{identifier}/payments"
    state = http.post(
        base + "/receipts",
        headers=HEADERS,
        json=versions(
            service,
            identifier,
            amount="200.00",
            method="cash",
            business_date="2026-10-08",
        ),
    ).json()
    receipt = state["receipts"][0]["id"]
    upload = base + f"/receipts/{receipt}/proofs"
    body = {key: str(value) for key, value in versions(service, identifier).items()}
    for extra in ({"actor_id": "PRIVATE_SYNTHETIC_SENTINEL"},):
        assert (
            http.post(
                upload,
                headers=HEADERS,
                data={**body, **extra},
                files={"file": ("synthetic.pdf", pdf(), "application/pdf")},
            ).status_code
            == 422
        )
    result = http.post(
        upload,
        headers=HEADERS,
        data=body,
        files={
            "file": ("../../PRIVATE_SYNTHETIC_SENTINEL.pdf", pdf(), "application/pdf")
        },
    )
    assert result.status_code == 200 and not result.json()["deposit_validated"]
    proof = result.json()["receipts"][0]["proofs"][0]
    assert "storage_key" not in proof and "path" not in proof
    repeated = http.post(
        upload,
        headers=HEADERS,
        data=body,
        files={"file": ("different-filename.pdf", pdf(), "application/pdf")},
    )
    assert repeated.json() == result.json()
    path = base + f"/proofs/{proof['id']}/download"
    downloaded = http.get(path)
    assert downloaded.content == pdf()
    assert downloaded.headers["Content-Disposition"].startswith("attachment;")
    assert downloaded.headers["Cache-Control"] == "no-store"
    assert downloaded.headers["X-Content-Type-Options"] == "nosniff"
    alien = create(quotations)["id"]
    assert (
        http.get(
            f"/quotations/{alien}/payments/proofs/{proof['id']}/download"
        ).status_code
        == 404
    )
    newbody = {key: str(value) for key, value in versions(service, identifier).items()}
    assert (
        http.post(
            upload,
            headers=HEADERS,
            data=newbody,
            files={
                "file": (
                    "invalid.pdf",
                    b"PRIVATE_SYNTHETIC_SENTINEL",
                    "application/pdf",
                )
            },
        ).status_code
        == 422
    )
    assert (
        http.post(
            upload,
            headers=HEADERS,
            data=newbody,
            files={"file": ("huge.pdf", b"x" * 10_000_001, "application/pdf")},
        ).status_code
        == 413
    )
    assert (
        http.post(
            upload, headers={**HEADERS, "Content-Length": "10065537"}, content=b"x"
        ).status_code
        == 413
    )
    with patch.object(service.storage, "read", side_effect=service_error()):
        assert http.get(path).status_code == 503
    assert "PRIVATE_SYNTHETIC_SENTINEL" not in caplog.text
    http.cookies.clear()
    assert http.get(path).status_code == 401


def service_error():
    from rentalops_api.payment_errors import PaymentError

    return PaymentError(503, "storage_unavailable", "Comprovante indisponível.")


def test_no_sensitive_input_echo_and_receipt_does_not_require_working_storage(
    client, caplog
):
    http, payments, _ = client
    service, _, identifier, *_ = payments
    login(client)
    base = f"/quotations/{identifier}/payments"
    body = versions(
        service, identifier, amount="200.00", method="pix", business_date="2026-10-08"
    )
    for change in (
        {"actor_id": "PRIVATE_SYNTHETIC_SENTINEL"},
        {"amount": "PRIVATE_SYNTHETIC_SENTINEL"},
        {"observation": "PRIVATE_SYNTHETIC_SENTINEL" * 100},
    ):
        result = http.post(base + "/receipts", headers=HEADERS, json={**body, **change})
        assert (
            result.status_code == 422
            and "PRIVATE_SYNTHETIC_SENTINEL" not in result.text
        )
    with patch.object(service.storage, "checked_path", side_effect=service_error()):
        assert (
            http.post(base + "/receipts", headers=HEADERS, json=body).status_code == 200
        )
    assert "PRIVATE_SYNTHETIC_SENTINEL" not in caplog.text
