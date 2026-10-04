from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from rentalops_api.auth import Identity
from rentalops_api.catalog_models import Kit, KitItem, Product
from rentalops_api.customer_models import Customer
from rentalops_api.database import build_session_factory
from rentalops_api.models import AuthSession, Base, User
from rentalops_api.quotation_contracts import (
    QuotationDraft,
    QuotationSearch,
    QuotationWrite,
)
from rentalops_api.quotation_models import Quotation, QuotationAudit, QuotationVersion
from rentalops_api.quotations import QuotationError, QuotationService

from ..conftest import migration_config

pytestmark = pytest.mark.integration


@pytest.fixture
def quotations(migrated_engine):
    factory = build_session_factory(migrated_engine)
    now = datetime(2026, 10, 9, 12, tzinfo=UTC)
    with factory.begin() as session:
        user = User(email="synthetic-quotation@example.invalid")
        session.add(user)
        session.flush()
        auth = AuthSession(
            user_id=user.id,
            token_hash=uuid4().hex,
            created_at=now,
            last_activity=now,
            expires_at=now + timedelta(hours=12),
        )
        customer = Customer(
            name="Synthetic quotation customer",
            phone="+5511912345678",
            version=1,
            created_by=user.id,
            updated_by=user.id,
        )
        session.add_all([auth, customer])
        session.flush()
        actor = Identity(user.id, auth.id, auth.expires_at, now + timedelta(hours=1))
        common = {
            "version": 1,
            "is_active": True,
            "created_by": user.id,
            "updated_by": user.id,
        }
        arch = Product(
            name="Synthetic arch",
            price=Decimal("40"),
            total_quantity=3,
            maintenance_quantity=1,
            **common,
        )
        vase = Product(
            name="Synthetic vase",
            price=Decimal("10"),
            total_quantity=5,
            maintenance_quantity=1,
            **common,
        )
        kit = Kit(name="Synthetic kit", price=Decimal("195"), **common)
        session.add_all([arch, vase, kit])
        session.flush()
        session.add_all(
            [
                KitItem(kit_id=kit.id, product_id=arch.id, quantity=1),
                KitItem(kit_id=kit.id, product_id=vase.id, quantity=2),
            ]
        )
        ids = {"customer": customer.id, "arch": arch.id, "vase": vase.id, "kit": kit.id}
    return QuotationService(factory, lambda: now), actor, ids


def draft(quotations, **changes):
    _, _, ids = quotations
    return QuotationDraft.model_validate(
        {
            "customer_id": str(ids["customer"]),
            "pickup_date": "2026-10-10",
            "event_date": "2026-10-11",
            "return_date": "2026-10-13",
            "valid_until": "2026-10-09",
            "lines": [
                {"kind": "kit", "source_id": str(ids["kit"]), "quantity": 2},
                {"kind": "product", "source_id": str(ids["vase"]), "quantity": 1},
            ],
            **changes,
        }
    )


def command_for(service, payload, **changes):
    preview = service.preview(payload)
    return QuotationWrite.model_validate(
        {
            **payload.model_dump(mode="json"),
            "request_id": str(uuid4()),
            "catalog_versions": preview["catalog_versions"],
            **changes,
        }
    )


def create(quotations, **changes):
    service, actor, _ = quotations
    return service.write(command_for(service, draft(quotations, **changes)), actor)[0]


def revision(quotations, saved, **changes):
    return draft(
        quotations,
        quotation_id=saved["id"],
        expected_version=saved["version"],
        lines=[
            {
                "kind": line["kind"],
                "source_id": line["source_id"],
                "quantity": line["quantity"],
                "retained_line_id": line["id"],
            }
            for line in saved["lines"]
        ],
        **changes,
    )


def test_migration_head_constraints_metadata_repeat_rollback(isolated_engine):
    with isolated_engine.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "0005_customers")
        previous = set(inspect(connection).get_table_names())
        command.upgrade(config, "head")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0006_quotations"
        )
        assert set(inspect(connection).get_table_names()) == previous | {
            "quotations",
            "quotation_versions",
            "quotation_lines",
            "quotation_components",
            "quotation_audit",
            "quotation_requests",
        }
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )
        command.upgrade(config, "head")
        assert {i["name"] for i in inspect(connection).get_indexes("quotations")} == {
            "ix_quotations_customer",
            "ix_quotations_order",
        }
        assert len(inspect(connection).get_foreign_keys("quotation_lines")) == 3
        command.downgrade(config, "0005_customers")
        assert set(inspect(connection).get_table_names()) == previous
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT count(*) FROM quotations")) == 0


def test_demand_money_pending_no_stock_effect_snapshot_history(quotations):
    service, actor, ids = quotations
    saved = create(
        quotations,
        discount={"kind": "percent", "value": "10", "reason": "Synthetic discount"},
    )
    capacity = {entry["product_id"]: entry for entry in saved["capacity"]}
    assert capacity[str(ids["arch"])]["demand"] == 2
    assert capacity[str(ids["vase"])] == {
        "product_id": str(ids["vase"]),
        "name": "Synthetic vase",
        "demand": 5,
        "apt": 4,
        "shortage": 1,
    }
    assert saved["stock_pending"] is True
    assert saved["total"] == "360.00"
    assert saved["estimated_deposit"] == saved["estimated_balance"] == "180.00"
    assert saved["actor_id"] == str(actor.user_id)
    assert saved["session_id"] == str(actor.session_id)
    assert saved["planning_available_from"] == "2026-10-14"
    with service.factory.begin() as session:
        assert session.get(Product, ids["vase"]).total_quantity == 5
        kit = session.get(Kit, ids["kit"])
        kit.price, kit.version = Decimal("999"), 2
    retained = revision(quotations, saved)
    updated, _ = service.write(
        command_for(service, retained, reason="Synthetic revision"),
        actor,
        UUID(saved["id"]),
    )
    assert updated["subtotal"] == "400.00"
    assert service.get(UUID(saved["id"]), 1)["total"] == "360.00"
    assert len(service.versions(UUID(saved["id"]))) == 2
    assert updated["version"] == 2 and updated["id"] == saved["id"]
    with service.factory.begin() as session:
        audit = session.scalar(
            select(QuotationAudit).where(QuotationAudit.version == 2)
        )
        assert audit.changed_fields == ["dates", "validity", "lines", "discount"]
    fresh = draft(quotations, quotation_id=saved["id"], expected_version=2)
    assert service.preview(fresh)["subtotal"] == "2008.00"


def test_custom_composition_price_explicit_and_catalog_unchanged(quotations):
    service, _, ids = quotations
    line = {
        "kind": "kit",
        "source_id": str(ids["kit"]),
        "quantity": 2,
        "items": [{"product_id": str(ids["vase"]), "quantity": 1}],
        "negotiation_reason": "Synthetic custom composition",
    }
    with pytest.raises(QuotationError):
        service.preview(draft(quotations, lines=[line]))
    saved = create(quotations, lines=[{**line, "unit_price": "100.01"}])
    assert saved["subtotal"] == "200.02"
    assert saved["capacity"][0]["demand"] == 2
    with service.factory() as session:
        assert session.get(Kit, ids["kit"]).price == Decimal("195")
        assert len(session.scalars(select(KitItem)).all()) == 2


@pytest.mark.parametrize("kind", ["product", "kit", "component"])
def test_inactive_rejects_new_and_revision_keeps_historical(quotations, kind):
    service, actor, ids = quotations
    saved = create(quotations)
    with service.factory.begin() as session:
        target = session.get(
            Kit if kind == "kit" else Product,
            ids["kit"] if kind == "kit" else ids["vase"],
        )
        target.is_active = False
        target.version += 1
    for payload in (draft(quotations), revision(quotations, saved)):
        with pytest.raises(QuotationError) as error:
            service.preview(payload)
        assert error.value.status == 422
    assert service.get(UUID(saved["id"]), 1)["lines"][0]["unit_price"] == "195.00"


def test_catalog_stale_conflict_and_expected_version(quotations):
    service, actor, ids = quotations
    command = command_for(service, draft(quotations))
    with service.factory.begin() as session:
        product = session.get(Product, ids["vase"])
        product.price, product.version = Decimal("12"), 2
    with pytest.raises(QuotationError) as error:
        service.write(command, actor)
    assert error.value.code == "catalog_conflict"
    with service.factory() as session:
        assert session.scalar(select(func_count(Quotation))) == 0
    saved = create(quotations)
    first = command_for(service, revision(quotations, saved), reason="Synthetic first")
    service.write(first, actor, UUID(saved["id"]))
    second = first.model_copy(update={"request_id": uuid4()})
    with pytest.raises(QuotationError) as error:
        service.write(second, actor, UUID(saved["id"]))
    assert error.value.code == "version_conflict"
    assert service.write(first, actor, UUID(saved["id"]))[1] is True


def func_count(model):
    from sqlalchemy import func

    return func.count(model.id)


@pytest.mark.parametrize("operation", ["create", "revise"])
def test_sequential_and_concurrent_replay_single_audit_and_changed_payload_conflict(
    quotations, operation
):
    service, actor, _ = quotations
    saved = create(quotations) if operation == "revise" else None
    payload = revision(quotations, saved) if saved else draft(quotations)
    command = command_for(
        service, payload, reason="Synthetic replay" if saved else None
    )
    identifier = UUID(saved["id"]) if saved else None
    barrier = Barrier(2)

    def write():
        barrier.wait()
        return service.write(command, actor, identifier)

    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda _: write(), range(2)))
    assert sorted(replay for _, replay in results) == [False, True]
    assert results[0][0] == results[1][0]
    assert service.write(command, actor, identifier) == (results[0][0], True)
    with service.factory() as session:
        assert session.scalar(select(func_count(QuotationAudit))) == (2 if saved else 1)
    changed = command.model_copy(update={"reason": "Different synthetic content"})
    with pytest.raises(QuotationError) as error:
        service.write(changed, actor, identifier)
    assert error.value.code == "idempotency_conflict"


def test_concurrent_revisions_one_winner(quotations):
    service, actor, _ = quotations
    saved = create(quotations)
    commands = [
        command_for(service, revision(quotations, saved), reason=f"Synthetic {i}")
        for i in range(2)
    ]
    barrier = Barrier(2)

    def write(command):
        barrier.wait()
        try:
            return service.write(command, actor, UUID(saved["id"]))[0]["version"]
        except QuotationError as error:
            return error.status

    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(write, commands))
    assert sorted(results) == [2, 409]
    assert len(service.versions(UUID(saved["id"]))) == 2


def test_transaction_commit_failure_rolls_back_whole_revision(quotations):
    service, actor, _ = quotations
    saved = create(quotations)
    command = command_for(
        service, revision(quotations, saved), reason="Synthetic failed revision"
    )
    with patch.object(
        Session, "commit", side_effect=OperationalError("private sql", {}, Exception())
    ):
        with pytest.raises(OperationalError):
            service.write(command, actor, UUID(saved["id"]))
    assert service.get(UUID(saved["id"]))["version"] == 1
    with service.factory() as session:
        assert session.scalar(select(func_count(QuotationAudit))) == 1
    assert service.write(command, actor, UUID(saved["id"]))[0]["version"] == 2


def test_database_immutability_money_quantity_fk_and_guard(quotations):
    service, actor, _ = quotations
    saved = create(quotations)
    for table in (
        "quotation_versions",
        "quotation_lines",
        "quotation_components",
        "quotation_audit",
        "quotation_requests",
    ):
        with pytest.raises(ProgrammingError), service.factory.begin() as session:
            session.execute(text(f"DELETE FROM {table}"))
    with pytest.raises(IntegrityError), service.factory.begin() as session:
        session.add(Quotation(id=uuid4(), customer_id=uuid4(), current_version=0))
    with pytest.raises(IntegrityError), service.factory.begin() as session:
        session.add(
            QuotationVersion(
                quotation_id=UUID(saved["id"]),
                number=2,
                pickup_date=datetime(2026, 10, 10),
                event_date=datetime(2026, 10, 11),
                return_date=datetime(2026, 10, 13),
                valid_until=datetime(2026, 10, 9),
                subtotal=1,
                discount_amount=0,
                total=0,
                estimated_deposit=0,
                estimated_balance=0,
                snapshot={},
                actor_id=actor.user_id,
                session_id=actor.session_id,
            )
        )
    assert service.guard_current_validity(UUID(saved["id"]), 1)["state"] == "current"
    service.clock = lambda: datetime(2026, 10, 10, 3, tzinfo=UTC)
    with pytest.raises(QuotationError) as error:
        service.guard_current_validity(UUID(saved["id"]), 1)
    assert error.value.code == "expired"
    assert service.search(QuotationSearch(state="expired"))["total"] == 1
    renewed = revision(quotations, saved, valid_until="2026-10-10")
    updated, _ = service.write(
        command_for(service, renewed, reason="Synthetic validity renewal"),
        actor,
        UUID(saved["id"]),
    )
    assert updated["state"] == "current"
    assert service.get(UUID(saved["id"]), 1)["expired"] is True


def test_capacity_refresh_retained_commercial_fields_and_limits(quotations):
    service, _, ids = quotations
    saved = create(quotations)
    with service.factory.begin() as session:
        vase = session.get(Product, ids["vase"])
        vase.maintenance_quantity = 0
        vase.price = Decimal("14.00")
        vase.version += 1
    refreshed = service.get(UUID(saved["id"]))
    assert refreshed["stock_pending"] is False
    assert refreshed["lines"] == saved["lines"]
    assert refreshed["total"] == saved["total"]
    excessive = draft(
        quotations,
        lines=[{"kind": "kit", "source_id": str(ids["kit"]), "quantity": 2147483647}],
    )
    with pytest.raises(QuotationError) as error:
        service.preview(excessive)
    assert error.value.status == 422
    for pid in (uuid4(), ids["kit"]):
        with pytest.raises(QuotationError):
            service.preview(
                draft(
                    quotations,
                    lines=[
                        {
                            "kind": "kit",
                            "source_id": str(ids["kit"]),
                            "quantity": 1,
                            "unit_price": "99",
                            "items": [{"product_id": str(pid), "quantity": 1}],
                            "negotiation_reason": "Synthetic invalid reference",
                        }
                    ],
                )
            )


def test_search_stable_order_pagination_filters_and_client_binding(quotations):
    service, actor, ids = quotations
    for _ in range(26):
        create(quotations)
    page = service.search(QuotationSearch(customer_id=ids["customer"]))
    page2 = service.search(QuotationSearch(customer_id=ids["customer"], page=2))
    assert page["total"] == 26 and len(page["items"]) == 25 and len(page2["items"]) == 1
    all_ids = [item["id"] for item in page["items"] + page2["items"]]
    assert len(set(all_ids)) == 26 and all_ids == sorted(all_ids)
    assert (
        service.search(
            QuotationSearch(
                event_date="2026-10-11",
                pickup_date="2026-10-10",
                return_date="2026-10-13",
                valid_until="2026-10-09",
            )
        )["total"]
        == 26
    )
    assert service.search(QuotationSearch(quotation_id=UUID(all_ids[0])))["total"] == 1
    assert service.search(QuotationSearch(customer_id=uuid4()))["items"] == []
    with service.factory.begin() as session:
        other = Customer(
            name="Synthetic different customer",
            phone="+5511912345678",
            version=1,
            created_by=actor.user_id,
            updated_by=actor.user_id,
        )
        session.add(other)
        session.flush()
        other_id = other.id
    saved = service.get(UUID(all_ids[0]))
    with pytest.raises(QuotationError) as error:
        service.preview(
            revision(quotations, saved).model_copy(update={"customer_id": other_id})
        )
    assert error.value.status == 422
