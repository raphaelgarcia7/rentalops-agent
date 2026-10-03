from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from rentalops_api.auth import Identity
from rentalops_api.catalog import CatalogService
from rentalops_api.catalog_contracts import (
    KitCreate,
    KitEdit,
    MaintenanceCommand,
    ProductCreate,
    ProductEdit,
    ReasonCommand,
    StockAdjustment,
)
from rentalops_api.catalog_models import CatalogHistory, KitItem, Product, StockMovement
from rentalops_api.catalog_storage import CatalogError, PhotoStorage
from rentalops_api.database import build_session_factory
from rentalops_api.models import AuthSession, Base, User

from ..conftest import migration_config

pytestmark = pytest.mark.integration


@pytest.fixture
def catalog(migrated_engine, tmp_path: Path):
    factory = build_session_factory(migrated_engine)
    now = datetime.now(UTC)
    with factory.begin() as db:
        user = User(email="catalog@example.invalid")
        db.add(user)
        db.flush()
        session = AuthSession(
            user_id=user.id,
            token_hash=uuid4().hex,
            created_at=now,
            last_activity=now,
            expires_at=now + timedelta(hours=12),
        )
        db.add(session)
        db.flush()
        actor = Identity(
            user.id, session.id, now + timedelta(hours=12), now + timedelta(hours=1)
        )
    return CatalogService(factory, PhotoStorage(tmp_path)), actor


def create(catalog, name="Vaso branco", quantity=5, **fields):
    service, actor = catalog
    return service.create_product(
        ProductCreate(name=name, price="100.01", initial_quantity=quantity, **fields),
        actor,
    )


def error(status, operation):
    with pytest.raises(CatalogError) as caught:
        operation()
    assert caught.value.status == status


def test_incremental_catalog_upgrade_repeat_and_rollback_preserves_auth(
    isolated_engine,
):
    with isolated_engine.begin() as db:
        config = migration_config(db)
        command.upgrade(config, "0003_password_set_limits")
        db.execute(
            text("INSERT INTO users(email) VALUES ('preserved@example.invalid')")
        )
        identifier = db.scalar(text("SELECT id FROM users"))
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        assert compare_metadata(MigrationContext.configure(db), Base.metadata) == []
        command.downgrade(config, "0003_password_set_limits")
        assert db.scalar(text("SELECT id FROM users")) == identifier
        assert "products" not in inspect(db).get_table_names()
        command.upgrade(config, "head")
        assert db.scalar(text("SELECT id FROM users")) == identifier


def test_minimum_optionals_initial_movement_exact_money_and_independent_variants(
    catalog,
):
    service, actor = catalog
    white = create(
        catalog,
        observation="Conferir tampo",
        color="Branca",
        replacement_value="200.01",
    )
    black = create(catalog, "Vaso preto", 2)
    assert white["price"] == "100.01" and white["observation"] == "Conferir tampo"
    assert white["movements"][0]["operation"] == "initial"
    assert white["movements"][0]["actor_id"] == str(actor.user_id)
    assert white["movements"][0]["session_id"] == str(actor.session_id)
    changed = service.adjust_stock(
        UUID(white["id"]),
        StockAdjustment(
            expected_version=1, operation="entry", quantity=2, reason="Received"
        ),
        actor,
    )
    assert changed["total_quantity"] == 7 and changed["version"] == 2
    assert service.get("products", UUID(black["id"]))["total_quantity"] == 2
    assert create(catalog, "Estoque zero", 0)["apt_quantity"] == 0


def test_stock_maintenance_partial_release_history_and_rollback(catalog):
    service, actor = catalog
    product = create(catalog)
    identifier = UUID(product["id"])
    maintained = service.maintenance(
        identifier,
        MaintenanceCommand(expected_version=1, quantity=1, reason="Repair"),
        actor,
    )
    assert maintained["total_quantity"] == 5 and maintained["apt_quantity"] == 4
    entry = UUID(maintained["maintenance"][0]["id"])
    error(
        422,
        lambda: service.adjust_stock(
            identifier,
            StockAdjustment(
                expected_version=2, operation="correction", quantity=0, reason="Count"
            ),
            actor,
        ),
    )
    error(
        422,
        lambda: service.maintenance(
            identifier,
            MaintenanceCommand(expected_version=2, quantity=5, reason="Repair"),
            actor,
        ),
    )
    error(
        422,
        lambda: service.release(
            identifier,
            entry,
            MaintenanceCommand(expected_version=2, quantity=2, reason="Ready"),
            actor,
        ),
    )
    assert service.get("products", identifier) == maintained
    released = service.release(
        identifier,
        entry,
        MaintenanceCommand(expected_version=2, quantity=1, reason="Ready"),
        actor,
    )
    assert released["apt_quantity"] == 5 and released["maintenance_quantity"] == 0
    error(
        422,
        lambda: service.release(
            identifier,
            entry,
            MaintenanceCommand(expected_version=3, quantity=1, reason="Again"),
            actor,
        ),
    )
    withdrawn = service.adjust_stock(
        identifier,
        StockAdjustment(
            expected_version=3, operation="withdrawal", quantity=1, reason="Broken"
        ),
        actor,
    )
    corrected = service.adjust_stock(
        identifier,
        StockAdjustment(
            expected_version=4, operation="correction", quantity=0, reason="Count"
        ),
        actor,
    )
    assert withdrawn["total_quantity"] == 4 and corrected["total_quantity"] == 0
    assert {row["operation"] for row in corrected["movements"]} == {
        "initial",
        "maintenance",
        "release",
        "withdrawal",
        "correction",
    }
    assert all(
        row["reason"] and row["actor_id"] == str(actor.user_id)
        for row in corrected["movements"]
    )


def test_failed_movement_commit_restores_stock_history_and_next_operation(catalog):
    service, actor = catalog
    product = create(catalog)
    identifier = UUID(product["id"])
    with patch.object(
        Session,
        "commit",
        side_effect=OperationalError("synthetic", {}, Exception("synthetic")),
    ):
        with pytest.raises(OperationalError):
            service.adjust_stock(
                identifier,
                StockAdjustment(
                    expected_version=1,
                    operation="entry",
                    quantity=2,
                    reason="Synthetic",
                ),
                actor,
            )
    assert service.get("products", identifier) == product
    assert (
        service.adjust_stock(
            identifier,
            StockAdjustment(
                expected_version=1, operation="entry", quantity=1, reason="Recovered"
            ),
            actor,
        )["total_quantity"]
        == 6
    )


def test_two_concurrent_adjustments_keep_one_version_and_one_movement(catalog):
    service, actor = catalog
    product = create(catalog, quantity=1)
    identifier = UUID(product["id"])
    barrier = Barrier(2)

    def adjust(_):
        barrier.wait(timeout=10)
        try:
            service.adjust_stock(
                identifier,
                StockAdjustment(
                    expected_version=1,
                    operation="withdrawal",
                    quantity=1,
                    reason="Race",
                ),
                actor,
            )
            return 200
        except CatalogError as failure:
            return failure.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(adjust, range(2))) == [200, 409]
    saved = service.get("products", identifier)
    assert saved["total_quantity"] == 0 and saved["version"] == 2
    assert len(saved["movements"]) == 2


def test_kit_aggregation_own_price_missing_nested_and_review(catalog):
    service, actor = catalog
    product = create(catalog)
    identifier = UUID(product["id"])
    kit = service.save_kit(
        KitCreate(
            name="Kit festa",
            price="50.01",
            items=[
                {"product_id": identifier, "quantity": 1},
                {"product_id": identifier, "quantity": 2},
            ],
        ),
        actor,
    )
    kit_id = UUID(kit["id"])
    assert kit["items"][0]["quantity"] == 3 and "total_quantity" not in kit
    edited = service.edit_product(
        identifier, ProductEdit(name="Vaso", price="200", expected_version=1), actor
    )
    assert service.get("kits", kit_id)["price"] == "50.01"
    for missing in [uuid4(), kit_id]:
        error(
            409,
            lambda missing=missing: service.save_kit(
                KitCreate(
                    name="Invalid",
                    price="1",
                    items=[{"product_id": missing, "quantity": 1}],
                ),
                actor,
            ),
        )
    service.inactivate(
        "products",
        identifier,
        ReasonCommand(expected_version=edited["version"], reason="Retired"),
        actor,
    )
    flagged = service.get("kits", kit_id)
    assert flagged["needs_review"] and flagged["items"][0]["product_id"] == str(
        identifier
    )
    error(
        409,
        lambda: service.save_kit(
            KitEdit(
                name="Kit",
                price="40",
                expected_version=1,
                items=[{"product_id": identifier, "quantity": 1}],
            ),
            actor,
            kit_id,
        ),
    )
    assert service.get("kits", kit_id) == flagged
    replacement = create(catalog, "Substituto")
    revised = service.save_kit(
        KitEdit(
            name="Kit revisado",
            price="40.01",
            expected_version=1,
            items=[{"product_id": UUID(replacement["id"]), "quantity": 2}],
        ),
        actor,
        kit_id,
    )
    assert not revised["needs_review"] and revised["price"] == "40.01"
    assert len(revised["history"]) == 2
    old = next(row for row in revised["history"] if row["operation"] == "created")
    assert old["snapshot"]["items"][0]["product_id"] == str(identifier)


def test_inactivation_edit_audit_no_loss_and_stale_409(catalog):
    service, actor = catalog
    original = create(catalog)
    identifier = UUID(original["id"])
    edited = service.edit_product(
        identifier,
        ProductEdit(
            name="Novo nome", price="0.01", observation="Saved", expected_version=1
        ),
        actor,
    )
    error(
        409,
        lambda: service.edit_product(
            identifier, ProductEdit(name="Stale", price="1", expected_version=1), actor
        ),
    )
    inactive = service.inactivate(
        "products",
        identifier,
        ReasonCommand(expected_version=2, reason="Retired"),
        actor,
    )
    assert not inactive["is_active"] and len(inactive["history"]) == 3
    assert inactive["movements"] == original["movements"]
    assert edited["observation"] == "Saved"
    assert any(
        row["snapshot"]["name"] == original["name"] for row in inactive["history"]
    )
    error(404, lambda: service.get("products", uuid4()))
    error(
        404,
        lambda: service.release(
            identifier,
            uuid4(),
            MaintenanceCommand(expected_version=3, reason="Ready", quantity=1),
            actor,
        ),
    )


def test_postgres_constraints_references_and_no_hard_delete(catalog):
    service, actor = catalog
    product = create(catalog)
    identifier = UUID(product["id"])
    for values in (
        {"total_quantity": -1},
        {"maintenance_quantity": 6},
        {"maintenance_quantity": -1},
        {"price": -1},
        {"name": " "},
        {"version": 0},
    ):
        with pytest.raises(IntegrityError), service.factory.begin() as db:
            db.query(Product).filter_by(id=identifier).update(values)
    with pytest.raises(IntegrityError), service.factory.begin() as db:
        db.add(KitItem(kit_id=uuid4(), product_id=identifier, quantity=1))
    with pytest.raises(IntegrityError), service.factory.begin() as db:
        db.delete(db.get(Product, identifier))
    with service.factory() as db:
        assert len(db.scalars(select(StockMovement)).all()) == 1
        assert len(db.scalars(select(CatalogHistory)).all()) == 1


def test_stable_pagination_search_literals_and_default_limit(catalog):
    service, _ = catalog
    identifiers = [create(catalog, "Mesmo nome")["id"] for _ in range(28)]
    first = service.list_records("products", "Mesmo", 1, 25)
    second = service.list_records("products", "Mesmo", 2, 25)
    assert (
        first["total"] == 28 and len(first["items"]) == 25 and len(second["items"]) == 3
    )
    assert [row["id"] for row in first["items"] + second["items"]] == sorted(
        identifiers
    )
    assert service.list_records("products", "%", 1, 25)["total"] == 0
