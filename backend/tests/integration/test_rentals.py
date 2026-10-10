from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier, Event
from unittest.mock import patch
from uuid import UUID

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from rentalops_api.catalog import CatalogService
from rentalops_api.catalog_contracts import (
    MaintenanceCommand,
    ProductEdit,
    ReasonCommand,
    StockAdjustment,
)
from rentalops_api.catalog_models import Product
from rentalops_api.catalog_storage import PhotoStorage
from rentalops_api.models import Base
from rentalops_api.payment_contracts import CorrectionCommand, RefundCommand
from rentalops_api.quotation_contracts import QuotationSearch
from rentalops_api.quotations import QuotationError
from rentalops_api.rental_contracts import ConfirmationCommand, ConfirmationPreview
from rentalops_api.rental_models import (
    Rental,
    RentalAllocation,
    RentalPending,
    RentalRequest,
)
from rentalops_api.rentals import RentalError, RentalService

from ..conftest import migration_config
from .test_payments import allocation, receive, reconcile, versions
from .test_payments import payments as payment_fixture
from .test_quotations import command_for, create, revision

pytestmark = pytest.mark.integration


@pytest.fixture
def rentals(migrated_engine, tmp_path):
    payments = payment_fixture.__wrapped__(migrated_engine, tmp_path)
    quotations = payments[3]
    with quotations[0].factory.begin() as session:
        vase = session.get(Product, quotations[2]["vase"])
        vase.total_quantity = 6  # 5 apt: the complete saved offer now fits.
    payments[0].clock = quotations[0].clock
    return RentalService(quotations[0].factory, quotations[0].clock), payments


def paid(payments, amount="200.00", balance="0.00"):
    received = receive(payments, amount)
    return reconcile(payments, [allocation(received, balance=balance)])


def confirmation(payments, **changes):
    return ConfirmationCommand.model_validate(
        versions(payments[0], payments[2], **changes)
    )


def counts(service):
    with service.factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Rental, RentalAllocation, RentalRequest, RentalPending)
        )


def test_migration_metadata_roundtrip_and_database_constraints(isolated_engine):
    with isolated_engine.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "head")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0008_rentals"
        )
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )
        command.downgrade(config, "0007_payments")
        assert "rentals" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )


def test_explicit_confirmation_snapshot_demand_unique_replay_and_history(rentals):
    service, payments = rentals
    state = paid(payments)
    assert counts(service) == (0, 0, 0, 0)  # Receipt + reconciliation do not allocate.
    payload = confirmation(payments)
    preview = service.preview(
        payments[2],
        ConfirmationPreview.model_validate(payload.model_dump(exclude={"request_id"})),
    )
    assert preview["deposit_valid"] is True and preview["pending"] is False
    assert sorted(row["demand"] for row in preview["capacity"]) == [2, 5]
    assert counts(service) == (0, 0, 0, 0)  # Preview is read-only.
    result, replay = service.confirm(payments[2], payload, payments[1])
    assert not replay and result["state"] == "confirmed" and result["version"] == 1
    assert result["commercial_snapshot"]["total"] == "400.00"
    assert result["financial_snapshot"] == state
    assert sorted(row["quantity"] for row in result["allocations"]) == [2, 5]
    assert service.confirm(payments[2], payload, payments[1]) == (result, True)
    assert service.get(UUID(result["id"])) == result
    assert service.get(payments[2], by_quotation=True) == result
    history = service.history(UUID(result["id"]), 1, 1)
    assert history["total"] == 1 and history["items"][0]["operation"] == "confirmed"
    assert counts(service) == (1, 2, 1, 0)
    with pytest.raises(RentalError, match="chave") as mismatch:
        service.confirm(
            payments[2],
            payload.model_copy(update={"expected_financial_version": 999}),
            payments[1],
        )
    assert mismatch.value.code == "idempotency_conflict"
    with service.factory.begin() as session:
        with pytest.raises(ProgrammingError):
            with session.begin_nested():
                session.execute(text("UPDATE rentals SET state = 'out'"))
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(text("UPDATE rental_allocations SET quantity = 0"))
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.execute(
                    text("UPDATE rental_allocations SET return_date = '2026-10-01'")
                )


@pytest.mark.parametrize("amounts", [[], ["100.00"], ["100.00", "100.00"], ["200.00"]])
def test_money_without_explicit_valid_reconciliation_cannot_confirm(rentals, amounts):
    service, payments = rentals
    for amount in amounts:
        receive(payments, amount)
    with pytest.raises(RentalError) as error:
        service.confirm(payments[2], confirmation(payments), payments[1])
    assert error.value.code == "deposit_required"
    assert counts(service) == (0, 0, 0, 0)
    assert len(payments[0].get(payments[2])["receipts"]) == len(amounts)


def test_stale_financial_commercial_expiry_and_backdate_guards(rentals):
    service, payments = rentals
    paid(payments)
    payload = confirmation(payments)
    receive(payments, "1.00")
    with pytest.raises(RentalError) as error:
        service.confirm(payments[2], payload, payments[1])
    assert error.value.code == "version_conflict"
    quote_service, actor, _ = payments[3]
    changed = quote_service.write(
        command_for(
            quote_service,
            revision(payments[3], payments[4]),
            reason="Synthetic revision",
        ),
        actor,
        payments[2],
    )[0]
    with pytest.raises(RentalError) as error:
        service.confirm(payments[2], payload, actor)
    assert error.value.code == "version_conflict"
    assert changed["version"] == 2
    with pytest.raises(RentalError) as error:
        service.confirm(payments[2], confirmation(payments), actor)
    assert error.value.code == "deposit_required"
    service.clock = lambda: datetime(2026, 10, 10, 12, tzinfo=UTC)
    with pytest.raises(RentalError) as error:
        service.confirm(payments[2], confirmation(payments), actor)
    assert error.value.code == "expired"
    # A valid saved offer must still refuse a pickup day that has passed.
    offer = create(payments[3], valid_until="2026-10-10")
    service.clock = lambda: datetime(2026, 10, 14, 12, tzinfo=UTC)
    with pytest.raises(RentalError) as error:
        service.preview(
            UUID(offer["id"]),
            ConfirmationPreview(
                expected_quotation_version=1, expected_financial_version=0
            ),
        )
    assert error.value.code == "pickup_passed"


def test_capacity_conflict_preserves_money_pending_replay_and_no_partial_allocation(
    rentals,
):
    service, payments = rentals
    paid(payments, "400.00", "200.00")
    with service.factory.begin() as session:
        session.get(Product, payments[3][2]["vase"]).maintenance_quantity = 2
    payload = confirmation(payments)
    with pytest.raises(RentalError) as failure:
        service.confirm(payments[2], payload, payments[1])
    assert failure.value.code == "capacity_conflict"
    assert sorted(row["shortage"] for row in failure.value.data["capacity"]) == [0, 1]
    assert counts(service) == (0, 0, 1, 1)
    with service.factory.begin() as session:
        session.get(Product, payments[3][2]["vase"]).maintenance_quantity = 1
    with pytest.raises(RentalError) as replay:
        service.confirm(payments[2], payload, payments[1])
    assert replay.value.data == failure.value.data
    assert payments[0].get(payments[2])["net_received"] == "400.00"
    result, _ = service.confirm(payments[2], confirmation(payments), payments[1])
    assert result["state"] == "confirmed"
    assert result["inventory_pending"] is False
    assert result["pending"][0]["resolved"] is True


def test_real_simultaneous_overlap_closed_boundaries_and_quotation_regression(rentals):
    service, payments = rentals
    paid(payments)
    service.confirm(payments[2], confirmation(payments), payments[1])
    quotations = payments[3]
    for day, expected in [(13, 5), (14, 0), (20, 0)]:
        offer = create(
            quotations,
            pickup_date=f"2026-10-{day}",
            event_date=f"2026-10-{day}",
            return_date=f"2026-10-{day}",
        )
        vase = next(
            row
            for row in offer["capacity"]
            if row["product_id"] == str(quotations[2]["vase"])
        )
        assert vase["shortage"] == expected
    # Two commitments on separate periods must not sum to ten units.
    offer = create(
        quotations,
        pickup_date="2026-10-14",
        event_date="2026-10-15",
        return_date="2026-10-16",
    )
    p2 = (*payments[:2], UUID(offer["id"]), quotations, offer)
    paid(p2)
    service.confirm(p2[2], confirmation(p2), p2[1])
    broad = create(
        quotations,
        pickup_date="2026-10-10",
        event_date="2026-10-11",
        return_date="2026-10-16",
    )
    assert sorted(row["committed"] for row in broad["capacity"]) == [2, 5]
    assert (
        len(
            quotations[0].search(
                QuotationSearch(customer_id=quotations[2]["customer"])
            )["items"]
        )
        == 6
    )


def test_confirmed_snapshot_guard_catalog_and_financial_issues_keep_allocation(
    rentals, tmp_path
):
    service, payments = rentals
    paid(payments)
    payload = confirmation(payments)
    original, _ = service.confirm(payments[2], payload, payments[1])
    catalog = CatalogService(service.factory, PhotoStorage(tmp_path))
    pid = payments[3][2]["vase"]
    catalog.maintenance(
        pid,
        MaintenanceCommand(
            expected_version=1, quantity=1, reason="Synthetic maintenance"
        ),
        payments[1],
    )
    catalog.adjust_stock(
        pid,
        StockAdjustment(
            expected_version=2,
            operation="withdrawal",
            quantity=1,
            reason="Synthetic decrease",
        ),
        payments[1],
    )
    catalog.inactivate(
        "products",
        pid,
        ReasonCommand(expected_version=3, reason="Synthetic inactive"),
        payments[1],
    )
    catalog.edit_product(
        pid,
        ProductEdit(
            expected_version=4, name="Synthetic changed catalog name", price="999.00"
        ),
        payments[1],
    )
    from ..unit.test_catalog_storage import synthetic_image

    catalog.upload_photo(pid, 5, synthetic_image(), "image/png", payments[1])
    current = service.get(UUID(original["id"]))
    assert current["inventory_pending"] and len(current["pending"]) == 2
    assert current["commercial_snapshot"] == original["commercial_snapshot"]
    assert current["allocations"] == original["allocations"]
    with pytest.raises(QuotationError) as guard:
        command_for(payments[3][0], revision(payments[3], payments[4]))
    assert guard.value.code == "already_confirmed"
    receipt_id = UUID(payments[0].get(payments[2])["receipts"][0]["id"])
    correction = CorrectionCommand.model_validate(
        versions(
            payments[0],
            payments[2],
            amount="100.00",
            method="cash",
            business_date="2026-10-08",
            reason="Synthetic correction",
        )
    )
    payments[0].write(payments[2], "correction", correction, payments[1], receipt_id)
    refund = RefundCommand.model_validate(
        versions(
            payments[0],
            payments[2],
            receipt_id=str(receipt_id),
            amount="10.00",
            method="cash",
            business_date="2026-10-08",
            reason="Synthetic real refund record",
        )
    )
    payments[0].write(payments[2], "refund", refund, payments[1])
    current = service.get(UUID(original["id"]))
    assert current["financial_pending"] and len(current["pending"]) == 4
    assert current["financial_snapshot"] == original["financial_snapshot"]
    assert current["allocations"] == original["allocations"]
    # Replay succeeds even after corrections, catalog inactivation and expiry.
    service.clock = lambda: datetime(2026, 11, 1, 12, tzinfo=UTC)
    assert service.confirm(payments[2], payload, payments[1]) == (original, True)


@pytest.mark.parametrize("single_unit", [False, True])
def test_two_postgres_connections_last_capacity_and_replay_concurrency(
    rentals, single_unit
):
    service, payments = rentals
    changes = {}
    if single_unit:
        arch = payments[3][2]["arch"]
        with service.factory.begin() as session:
            product = session.get(Product, arch)
            product.total_quantity, product.maintenance_quantity = 1, 0
        changes = {
            "lines": [
                {
                    "kind": "product",
                    "source_id": str(arch),
                    "quantity": 1,
                    "unit_price": "400.00",
                    "negotiation_reason": "Synthetic agreed single unit",
                }
            ]
        }
        first = create(payments[3], **changes)
        payments = (*payments[:2], UUID(first["id"]), payments[3], first)
    paid(payments)
    offer = create(payments[3], **changes)
    p2 = (*payments[:2], UUID(offer["id"]), payments[3], offer)
    paid(p2)
    barrier = Barrier(2)

    def compete(item):
        barrier.wait()
        try:
            return service.confirm(item[2], confirmation(item), item[1])[0]
        except RentalError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(compete, [payments, p2]))
    assert sum(isinstance(row, dict) for row in outcomes) == 1
    assert outcomes.count("capacity_conflict") == 1
    assert counts(service)[:2] == (1, 1 if single_unit else 2)
    assert payments[0].get(payments[2])["net_received"] == "200.00"
    assert payments[0].get(p2[2])["net_received"] == "200.00"


def test_same_request_concurrent_and_commit_failure_roll_back_all(rentals):
    service, payments = rentals
    paid(payments)
    payload = confirmation(payments)
    with patch.object(
        Session, "commit", side_effect=RuntimeError("Synthetic commit failure")
    ):
        with pytest.raises(RuntimeError):
            service.confirm(payments[2], payload, payments[1])
    assert counts(service) == (0, 0, 0, 0)
    barrier = Barrier(2)

    def confirm(_):
        barrier.wait()
        return service.confirm(payments[2], payload, payments[1])

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(confirm, range(2)))
    assert outcomes[0][0] == outcomes[1][0]
    assert sorted(row[1] for row in outcomes) == [False, True]
    assert counts(service) == (1, 2, 1, 0)


@pytest.mark.parametrize(
    "operation",
    [
        "correction",
        "reconciliation",
        "refund",
        "revision",
        "decrease",
        "maintenance",
    ],
)
def test_confirmation_races_payment_revision_and_stock(rentals, tmp_path, operation):
    service, payments = rentals
    paid(payments)
    payload = confirmation(payments)
    barrier = Barrier(2)
    quote_service, actor, _ = payments[3]
    revision_payload = command_for(
        quote_service,
        revision(payments[3], payments[4]),
        reason="Synthetic concurrent revision",
    )
    receipt = payments[0].get(payments[2])["receipts"][0]
    correction = CorrectionCommand.model_validate(
        versions(
            payments[0],
            payments[2],
            amount="100.00",
            method="cash",
            business_date="2026-10-08",
            reason="Synthetic concurrent correction",
        )
    )

    def confirm():
        barrier.wait()
        try:
            return service.confirm(payments[2], payload, actor)[0]
        except RentalError as error:
            return error.code

    def mutate():
        barrier.wait()
        try:
            if operation == "correction":
                return payments[0].write(
                    payments[2], operation, correction, actor, UUID(receipt["id"])
                )[0]
            if operation == "reconciliation":
                return reconcile(payments, [allocation(payments[0].get(payments[2]))])
            if operation == "refund":
                refund = RefundCommand.model_validate(
                    versions(
                        payments[0],
                        payments[2],
                        receipt_id=receipt["id"],
                        amount="1.00",
                        method="pix",
                        business_date="2026-10-08",
                        reason="Synthetic race refund",
                    )
                )
                return payments[0].write(payments[2], "refund", refund, actor)[0]
            if operation == "revision":
                return quote_service.write(revision_payload, actor, payments[2])[0]
            catalog = CatalogService(service.factory, PhotoStorage(tmp_path))
            if operation == "maintenance":
                return catalog.maintenance(
                    payments[3][2]["vase"],
                    MaintenanceCommand(
                        expected_version=1,
                        quantity=1,
                        reason="Synthetic race maintenance",
                    ),
                    actor,
                )
            return catalog.adjust_stock(
                payments[3][2]["vase"],
                StockAdjustment(
                    expected_version=1,
                    operation="withdrawal",
                    quantity=1,
                    reason="Synthetic concurrent loss",
                ),
                actor,
            )
        except QuotationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1, f2 = pool.submit(confirm), pool.submit(mutate)
        result, changed = f1.result(), f2.result()
    if isinstance(result, dict):
        current = service.get(UUID(result["id"]))
        assert current["state"] == "confirmed"
        if operation == "revision":
            assert changed == "already_confirmed"
        elif operation != "reconciliation":
            kind = "financial" if operation in {"correction", "refund"} else "inventory"
            assert current[f"{kind}_pending"]
    else:
        assert result in {"version_conflict", "capacity_conflict", "deposit_required"}
        assert counts(service)[0] == 0


def test_inventory_pending_insert_never_locks_quotation_after_product(
    rentals, tmp_path
):
    service, payments = rentals
    paid(payments)
    service.confirm(payments[2], confirmation(payments), payments[1])
    offer = create(payments[3])
    p2 = (*payments[:2], UUID(offer["id"]), payments[3], offer)
    paid(p2)
    stock_holds_product, confirmation_waits_product = Event(), Event()
    from rentalops_api.rental_effects import record_inventory_impact

    def impact(session, product, actor):
        stock_holds_product.set()
        assert confirmation_waits_product.wait(5)
        return record_inventory_impact(session, product, actor)

    def observe(connection, cursor, statement, parameters, context, executemany):
        if (
            "FROM products" in statement
            and "FOR UPDATE" in statement
            and stock_holds_product.is_set()
        ):
            confirmation_waits_product.set()

    event.listen(service.factory.kw["bind"], "before_cursor_execute", observe)

    def stock():
        return CatalogService(service.factory, PhotoStorage(tmp_path)).maintenance(
            payments[3][2]["vase"],
            MaintenanceCommand(
                expected_version=1, quantity=1, reason="Synthetic lock order"
            ),
            payments[1],
        )

    def confirm():
        assert stock_holds_product.wait(5)
        with pytest.raises(RentalError) as failure:
            service.confirm(p2[2], confirmation(p2), p2[1])
        assert failure.value.code == "capacity_conflict"

    try:
        with patch("rentalops_api.catalog.record_inventory_impact", side_effect=impact):
            with ThreadPoolExecutor(max_workers=2) as pool:
                a, b = pool.submit(stock), pool.submit(confirm)
                a.result()
                b.result()
    finally:
        event.remove(service.factory.kw["bind"], "before_cursor_execute", observe)
    assert service.get(payments[2], by_quotation=True)["inventory_pending"]


def test_stock_impact_and_movement_roll_back_together(rentals, tmp_path):
    service, payments = rentals
    paid(payments)
    service.confirm(payments[2], confirmation(payments), payments[1])
    catalog = CatalogService(service.factory, PhotoStorage(tmp_path))
    pid = payments[3][2]["vase"]
    before = catalog.get("products", pid)
    with patch.object(
        CatalogService,
        "_commit_product",
        side_effect=RuntimeError("Synthetic rollback"),
    ):
        with pytest.raises(RuntimeError):
            catalog.maintenance(
                pid,
                MaintenanceCommand(
                    expected_version=1,
                    quantity=1,
                    reason="Synthetic rolled back damage",
                ),
                payments[1],
            )
    assert catalog.get("products", pid) == before
    assert service.get(payments[2], by_quotation=True)["pending"] == []
