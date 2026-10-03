from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from rentalops_api.auth import AuthService, AuthSettings
from rentalops_api.auth_routes import auth_service
from rentalops_api.catalog import CatalogService
from rentalops_api.catalog_models import ProductPhoto
from rentalops_api.catalog_routes import catalog_service
from rentalops_api.catalog_storage import CatalogError, PhotoStorage
from rentalops_api.database import build_session_factory
from rentalops_api.main import app

from ..unit.test_catalog_storage import synthetic_image

pytestmark = pytest.mark.integration
ORIGIN = "http://localhost:5173"


@pytest.fixture
def catalog_client(migrated_engine, tmp_path: Path):
    factory = build_session_factory(migrated_engine)
    auth = AuthService(
        factory, AuthSettings(ORIGIN, False, "synthetic-catalog-rate-key" * 3)
    )
    auth.create_user("api@example.invalid")
    link = auth.issue_link("api@example.invalid", "access")
    auth.set_password(link, "synthetic catalog pass phrase", "loopback")
    service = CatalogService(factory, PhotoStorage(tmp_path))
    app.dependency_overrides[auth_service] = lambda: auth
    app.dependency_overrides[catalog_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, service, auth
    finally:
        app.dependency_overrides.clear()


def login(client):
    response = client.post(
        "/auth/password/login",
        headers={"Origin": ORIGIN},
        json={
            "email": "api@example.invalid",
            "password": "synthetic catalog pass phrase",
        },
    )
    assert response.status_code == 200
    return response.json()


def create(client):
    response = client.post(
        "/products",
        headers={"Origin": ORIGIN},
        json={
            "name": "Mesa branca",
            "price": "100.01",
            "initial_quantity": 5,
            "observation": "Synthetic observation",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_api_auth_origin_actor_validation_contracts_versions_and_status(
    catalog_client, caplog
):
    client, service, _ = catalog_client
    for path in ("/products", "/kits", f"/products/{uuid4()}", f"/photos/{uuid4()}"):
        assert client.get(path).status_code == 401
    identity = login(client)
    base = {"name": "Synthetic", "price": "1.01", "initial_quantity": 0}
    assert client.post("/products", json=base).status_code == 403
    assert (
        client.post(
            "/products", headers={"Origin": "https://other.invalid"}, json=base
        ).status_code
        == 403
    )
    for field, value in (
        ("actor_id", str(uuid4())),
        ("id", str(uuid4())),
        ("price", 1.01),
        ("initial_quantity", True),
    ):
        assert (
            client.post(
                "/products", headers={"Origin": ORIGIN}, json={**base, field: value}
            ).status_code
            == 422
        )
    product = create(client)
    assert product["created_by"] == identity["user_id"]
    assert product["movements"][0]["session_id"] == identity["session_id"]
    assert (
        product["price"] == "100.01"
        and product["observation"] == "Synthetic observation"
    )
    assert client.get("/products").json()["page_size"] == 25
    for query in ("page_size=101", "page=0", "search=" + "a" * 201):
        assert client.get("/products?" + query).status_code == 422
    assert client.get("/products?search=branca").json()["total"] == 1
    assert client.get(f"/products/{uuid4()}").status_code == 404
    edit = {"name": "Novo nome", "price": "101.01", "expected_version": 1}
    assert (
        client.patch(
            f"/products/{product['id']}", headers={"Origin": ORIGIN}, json=edit
        ).status_code
        == 200
    )
    stale = client.patch(
        f"/products/{product['id']}", headers={"Origin": ORIGIN}, json=edit
    )
    assert stale.status_code == 409
    assert client.delete(f"/products/{product['id']}").status_code == 405
    assert client.get("/products").headers["cache-control"] == "no-store"
    assert "SQL" not in caplog.text and "Synthetic observation" not in caplog.text


def test_api_kit_missing_nested_rejected_and_inactivation_history(catalog_client):
    client, _, _ = catalog_client
    login(client)
    product = create(client)
    payload = {
        "name": "Kit",
        "price": "50.01",
        "items": [{"product_id": product["id"], "quantity": 2}],
    }
    kit = client.post("/kits", headers={"Origin": ORIGIN}, json=payload)
    assert kit.status_code == 201 and kit.json()["price"] == "50.01"
    nested = {**payload, "items": [{"product_id": kit.json()["id"], "quantity": 1}]}
    assert (
        client.post("/kits", headers={"Origin": ORIGIN}, json=nested).status_code == 409
    )
    assert (
        client.post(
            f"/products/{product['id']}/inactivate",
            headers={"Origin": ORIGIN},
            json={"expected_version": 1, "reason": "Retired"},
        ).status_code
        == 200
    )
    assert client.get(f"/kits/{kit.json()['id']}").json()["needs_review"]
    assert (
        client.post(
            f"/kits/{kit.json()['id']}/inactivate",
            headers={"Origin": ORIGIN},
            json={"expected_version": 1, "reason": "Retired kit"},
        ).status_code
        == 200
    )


def test_photo_api_principal_order_detach_and_auth_private_immutable_assets(
    catalog_client,
):
    client, service, auth = catalog_client
    login(client)
    product = create(client)
    path = f"/products/{product['id']}/photos"
    data = synthetic_image("JPEG", exif=True)
    response = client.post(
        path,
        headers={"Origin": ORIGIN},
        data={"expected_version": "1"},
        files={"file": ("../../fake.jpg", data, "image/jpeg")},
    )
    assert response.status_code == 201
    first = response.json()["photos"][0]
    assert first["is_principal"] and "storage_key" not in first
    second_response = client.post(
        path,
        headers={"Origin": ORIGIN},
        data={"expected_version": "2"},
        files={"file": ("new.png", synthetic_image(), "image/png")},
    )
    assert second_response.status_code == 201
    second = next(p for p in second_response.json()["photos"] if p["id"] != first["id"])
    assert not second["is_principal"] and second["id"] != first["id"]
    principal = client.patch(
        path + f"/{second['id']}",
        headers={"Origin": ORIGIN},
        json={"expected_version": 3, "is_principal": True, "order": 0},
    )
    assert (
        principal.status_code == 200
        and next(p for p in principal.json()["photos"] if p["is_principal"])["id"]
        == second["id"]
    )
    previous = client.get(f"/photos/{first['id']}")
    assert (
        previous.status_code == 200 and previous.headers["content-type"] == "image/jpeg"
    )
    assert previous.headers["x-content-type-options"] == "nosniff"
    detached = client.post(
        path + f"/{second['id']}/detach",
        headers={"Origin": ORIGIN},
        json={"expected_version": 4, "reason": "Replace gallery"},
    )
    assert detached.status_code == 200 and detached.json()["photos"][0]["is_principal"]
    assert client.get(f"/photos/{second['id']}").status_code == 200
    assert client.get(f"/photos/{first['id']}").content == previous.content
    assert len(list(service.storage.root.iterdir())) == 2
    client.cookies.clear()
    assert client.get(f"/photos/{first['id']}").status_code == 401


def test_photo_api_validation_missing_storage_and_failure_compensation(catalog_client):
    client, service, _ = catalog_client
    login(client)
    product = create(client)
    path = f"/products/{product['id']}/photos"
    files = {"file": ("synthetic.png", synthetic_image(), "image/png")}
    assert (
        client.post(path, data={"expected_version": "1"}, files=files).status_code
        == 403
    )
    assert (
        client.post(
            path,
            headers={"Origin": ORIGIN},
            data={"expected_version": "1", "actor_id": str(uuid4())},
            files=files,
        ).status_code
        == 422
    )
    service.storage = PhotoStorage(None)
    assert (
        client.post(
            path,
            headers={"Origin": ORIGIN},
            data={"expected_version": "1"},
            files=files,
        ).status_code
        == 503
    )
    assert client.get(f"/photos/{uuid4()}").status_code == 503


def test_photo_db_failure_and_stale_version_remove_only_new_file(catalog_client):
    client, service, auth = catalog_client
    login(client)
    actor = auth.identity(client.cookies.get("rentalops_session"))
    product = create(client)
    identifier = UUID(product["id"])
    old = service.upload_photo(identifier, 1, synthetic_image(), "image/png", actor)
    files_before = {p.name: p.read_bytes() for p in service.storage.root.iterdir()}
    for failure in ("db", "version"):
        if failure == "db":
            with patch.object(
                Session,
                "commit",
                side_effect=OperationalError("synthetic", {}, Exception("synthetic")),
            ):
                with pytest.raises(OperationalError):
                    service.upload_photo(
                        identifier, 2, synthetic_image(), "image/png", actor
                    )
        else:
            with pytest.raises(CatalogError) as caught:
                service.upload_photo(
                    identifier, 1, synthetic_image(), "image/png", actor
                )
            assert caught.value.status == 409
        assert {
            p.name: p.read_bytes() for p in service.storage.root.iterdir()
        } == files_before
        assert service.get("products", identifier) == old
    with service.factory() as db:
        assert len(db.scalars(select(ProductPhoto)).all()) == 1


def test_upload_large_request_and_chunked_body_limit(catalog_client):
    client, _, _ = catalog_client
    login(client)
    product = create(client)
    path = f"/products/{product['id']}/photos"
    data = b"x" * (10 * 1024 * 1024 + 128 * 1024)
    assert (
        client.post(path, headers={"Origin": ORIGIN}, content=data).status_code == 413
    )

    def chunks():
        yield data[: 5 * 1024 * 1024]
        yield data[5 * 1024 * 1024 :]

    assert (
        client.post(
            path,
            headers={
                "Origin": ORIGIN,
                "Content-Type": "multipart/form-data; boundary=x",
            },
            content=chunks(),
        ).status_code
        == 413
    )


def test_uncertain_commit_keeps_referenced_new_asset(catalog_client):
    client, service, auth = catalog_client
    login(client)
    actor = auth.identity(client.cookies.get("rentalops_session"))
    product = create(client)
    original_commit = Session.commit

    def commit_then_disconnect(session):
        original_commit(session)
        raise OperationalError("synthetic unknown result", {}, Exception("synthetic"))

    with patch.object(Session, "commit", commit_then_disconnect):
        with pytest.raises(OperationalError):
            service.upload_photo(
                UUID(product["id"]), 1, synthetic_image(), "image/png", actor
            )
    saved = service.get("products", UUID(product["id"]))
    assert saved["version"] == 2 and len(saved["photos"]) == 1
    assert len(list(service.storage.root.iterdir())) == 1
    data, image_format = service.read_photo(UUID(saved["photos"][0]["id"]))
    assert data and image_format == "PNG"
