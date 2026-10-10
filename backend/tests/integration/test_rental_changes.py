from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from rentalops_api.models import Base
from rentalops_api.payment_contracts import CorrectionCommand, RefundCommand
from rentalops_api.payment_errors import PaymentError
from rentalops_api.payment_models import PaymentRefund, Receipt
from rentalops_api.quotation_models import QuotationVersion
from rentalops_api.quotations import QuotationError
from rentalops_api.rental_changes import RentalChangeService
from rentalops_api.rental_contracts import (
    CancellationCommand,
    ChangeCommand,
    ChangePreview,
    ResumptionCommand,
)
from rentalops_api.rental_models import Rental
from rentalops_api.rentals import RentalError

from ..conftest import migration_config
from .test_payments import allocation, receive, versions
from .test_quotations import create, revision
from .test_rentals import confirmation, paid
from .test_rentals import rentals as rental_fixture

pytestmark = pytest.mark.integration


@pytest.fixture
def changes(migrated_engine, tmp_path):
    rentals, payments = rental_fixture.__wrapped__(migrated_engine, tmp_path)
    return RentalChangeService(rentals.factory, rentals.clock), payments


def confirmed(changes):
    service, payments = changes
    paid(payments)
    return service.confirm(payments[2], confirmation(payments), payments[1])[0]


def preview_input(changes, rental, total=None, **dates):
    service, payments = changes
    quotation = payments[3][0].get(payments[2])
    draft = revision(payments[3], quotation, **dates)
    if total is not None:
        # Two kits and one vase: negotiated kit price leaves the avulso intact.
        lines = list(draft.lines)
        lines[0] = lines[0].model_copy(
            update={
                "unit_price": (total - 10) / 2,
                "negotiation_reason": "Synthetic revised price",
            }
        )
        draft = draft.model_copy(update={"lines": lines})
    return ChangePreview(
        draft=draft,
        expected_quotation_version=quotation["version"],
        expected_financial_version=payments[0].get(payments[2])["financial_version"],
        expected_rental_version=rental["version"] if rental else 0,
    )


def change_command(changes, rental, **changeset):
    preview = preview_input(changes, rental, **changeset)
    value = changes[0].change_preview(UUID(rental["id"]), preview)
    return ChangeCommand.model_validate(
        {
            **preview.model_dump(mode="json"),
            "catalog_versions": value["after"]["catalog_versions"],
            "reason": "Synthetic human agreement",
            "request_id": str(uuid4()),
        }
    )


def cancel(changes, rental, approved=True):
    service, payments = changes
    current = payments[0].get(payments[2])
    return service.command(
        UUID(rental["id"]),
        "cancel",
        CancellationCommand(
            expected_rental_version=rental["version"],
            expected_quotation_version=current["quotation_version"],
            expected_financial_version=current["financial_version"],
            approved=approved,
            reason="Synthetic team cancellation",
            request_id=uuid4(),
        ),
        payments[1],
    )[0]


def test_chg01_increase_reduction_original_deposit_excess_immutable_replay(changes):
    from decimal import Decimal

    service, payments = changes
    original = confirmed(changes)
    identifier = UUID(original["id"])
    payload = change_command(changes, original, total=Decimal("500"))
    before_preview = service.get(identifier)
    preview = service.change_preview(
        identifier,
        ChangePreview.model_validate(
            payload.model_dump(include=set(ChangePreview.model_fields))
        ),
    )
    assert preview["financial"]["remaining"] == "300.00"
    assert service.get(identifier) == before_preview
    increased, replay = service.command(identifier, "change", payload, payments[1])
    assert not replay and increased["version"] == 2
    assert increased["current_financial"]["remaining"] == "300.00"
    assert increased["current_financial"]["estimated_deposit"] == "200.00"
    assert increased["current_financial"]["deposit_validated"] is True
    assert increased["allocations"] == original["allocations"]
    smaller = change_command(changes, increased, total=Decimal("150"))
    reduced, _ = service.command(identifier, "change", smaller, payments[1])
    assert reduced["current_financial"]["remaining"] == "0.00"
    assert reduced["current_financial"]["excess"] == "50.00"
    assert reduced["financial_pending"] is True
    assert service.command(identifier, "change", payload, payments[1]) == (
        increased,
        True,
    )
    history = service.history(identifier)
    assert history["total"] == 3
    assert history["items"][1]["before"]["commercial_snapshot"]["total"] == "400.00"
    assert history["items"][2]["after"]["commercial_snapshot"]["total"] == "150.00"
    assert history["items"][2]["actor_id"] == str(payments[1].user_id)
    assert history["items"][2]["reason"] == "Synthetic human agreement"
    with service.factory() as session:
        assert session.scalar(select(func.count()).select_from(Receipt)) == 1
        assert session.scalar(select(func.count()).select_from(PaymentRefund)) == 0
        assert session.get(QuotationVersion, (payments[2], 1)).total == Decimal("400")
    with pytest.raises(RentalError) as error:
        service.command(
            identifier,
            "change",
            payload.model_copy(update={"reason": "Changed payload"}),
            payments[1],
        )
    assert error.value.code == "idempotency_conflict"


def test_chg02_conflict_stale_replay_rollback_preserve_old_commitment(changes):
    service, payments = changes
    original = confirmed(changes)
    identifier = UUID(original["id"])
    payload = change_command(changes, original)
    draft = payload.draft.model_copy(
        update={
            "lines": [
                row.model_copy(update={"quantity": 3}) for row in payload.draft.lines
            ]
        }
    )
    over = payload.model_copy(update={"draft": draft})
    with pytest.raises(RentalError) as error:
        service.command(identifier, "change", over, payments[1])
    assert error.value.code == "capacity_conflict"
    assert service.get(identifier) == original
    with pytest.raises(RentalError) as replay:
        service.command(identifier, "change", over, payments[1])
    assert replay.value.data == error.value.data
    payload = payload.model_copy(update={"request_id": uuid4()})
    with patch.object(
        Session, "commit", side_effect=RuntimeError("synthetic rollback")
    ):
        with pytest.raises(RuntimeError, match="synthetic rollback"):
            service.command(identifier, "change", payload, payments[1])
    assert service.get(identifier) == original
    result, _ = service.command(identifier, "change", payload, payments[1])
    with pytest.raises(RentalError) as stale:
        service.command(
            identifier,
            "change",
            payload.model_copy(update={"request_id": uuid4()}),
            payments[1],
        )
    assert stale.value.code == "version_conflict"
    assert service.get(identifier) == result
    with pytest.raises(QuotationError):
        payments[3][0].preview(payload.draft)


def test_chg02_real_racing_edits_and_cancellation(changes):
    service, payments = changes
    original = confirmed(changes)
    identifier = UUID(original["id"])
    payload = change_command(changes, original, return_date="2026-10-14")
    barrier = Barrier(2)

    def run():
        barrier.wait()
        try:
            return service.command(
                identifier,
                "change",
                payload.model_copy(update={"request_id": uuid4()}),
                payments[1],
            )[0]
        except RentalError as error:
            return error.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert len([row for row in results if isinstance(row, dict)]) == 1
    assert "version_conflict" in results
    assert service.get(identifier)["version"] == 2


def test_chg03_requested_cancel_approved_only_own_allocation_and_finance(changes):
    service, payments = changes
    original = confirmed(changes)
    requested = cancel(changes, original, approved=False)
    assert (
        requested["state"] == "confirmed"
        and requested["allocations"] == original["allocations"]
    )
    cancelled = cancel(changes, requested)
    assert cancelled["state"] == "cancelled" and cancelled["allocations"] == []
    assert cancelled["current_financial"]["net_received"] == "200.00"
    assert cancelled["current_financial"]["refunded"] == "0.00"
    assert service.history(UUID(original["id"]))["total"] == 3


def test_locked_context_refreshes_identity_after_concurrent_cancel(changes):
    service, _ = changes
    original = confirmed(changes)
    identifier = UUID(original["id"])
    payload = preview_input(changes, original)
    with service.factory() as session:
        cached = session.get(Rental, identifier)
        assert cached is not None and cached.version == 1
        cancelled = cancel(changes, original)
        assert cancelled["version"] == 2
        with pytest.raises(RentalError) as stale:
            service._context(session, identifier, payload, locked=True)
        assert stale.value.code == "version_conflict"
        assert cached.version == 2 and cached.state == "cancelled"
    assert service.get(identifier) == cancelled


@pytest.mark.parametrize("total", ["500", "150"])
def test_cancel_preserves_revised_financial_terms_without_silent_reconciliation(
    changes, total
):
    from decimal import Decimal

    service, payments = changes
    original = confirmed(changes)
    changed, _ = service.command(
        UUID(original["id"]),
        "change",
        change_command(changes, original, total=Decimal(total)),
        payments[1],
    )
    cancelled = cancel(changes, changed)
    assert cancelled["allocations"] == []
    assert cancelled["current_financial"] == changed["current_financial"]
    assert cancelled["financial_snapshot"] == changed["financial_snapshot"]


def resume_command(changes, rental, applications):
    service, payments = changes
    preview = preview_input(changes, rental)
    value = service.change_preview(
        UUID(rental["id"]) if rental else payments[2], preview, by_quotation=not rental
    )
    return ResumptionCommand.model_validate(
        {
            **preview.model_dump(mode="json"),
            "catalog_versions": value["after"]["catalog_versions"],
            "applications": applications,
            "payments_reviewed": True,
            "reason": "Synthetic explicit resumption",
            "request_id": str(uuid4()),
        }
    )


def test_chg04_cancelled_resume_same_id_without_allocating_then_fresh_confirm(changes):
    service, payments = changes
    original = confirmed(changes)
    cancelled = cancel(changes, original)
    payload = resume_command(
        changes, cancelled, [allocation(payments[0].get(payments[2]))]
    )
    resumed, _ = service.command(UUID(original["id"]), "resume", payload, payments[1])
    assert resumed["id"] == original["id"] and resumed["state"] == "review"
    assert (
        resumed["allocations"] == []
        and resumed["current_financial"]["net_received"] == "200.00"
    )
    assert len(resumed["current_financial"]["receipts"]) == 1
    conf = confirmation(payments, expected_rental_version=resumed["version"])
    confirmed_again, _ = service.confirm(payments[2], conf, payments[1])
    assert (
        confirmed_again["id"] == original["id"]
        and confirmed_again["state"] == "confirmed"
    )
    assert (
        confirmed_again["version"] == 4
        and confirmed_again["allocations"] == original["allocations"]
    )


def test_chg04_refunded_money_cannot_reappear_two_small_sources_do_not_make_signal(
    changes,
):
    service, payments = changes
    original = confirmed(changes)
    cancelled = cancel(changes, original)
    state = payments[0].get(payments[2])
    payments[0].write(
        payments[2],
        "refund",
        RefundCommand.model_validate(
            versions(
                payments[0],
                payments[2],
                receipt_id=state["receipts"][0]["id"],
                amount="100.00",
                method="pix",
                business_date="2026-10-08",
                reason="Synthetic actual partial refund",
            )
        ),
        payments[1],
    )
    receive(payments, "100.00")
    with pytest.raises(PaymentError):
        service.command(
            UUID(original["id"]),
            "resume",
            resume_command(changes, cancelled, [allocation(state)]),
            payments[1],
        )
    current = payments[0].get(payments[2])
    with pytest.raises(PaymentError):
        service.command(
            UUID(original["id"]),
            "resume",
            resume_command(
                changes,
                cancelled,
                [
                    allocation(current, index=0, deposit="100.00"),
                    allocation(current, index=1, deposit="100.00"),
                ],
            ),
            payments[1],
        )
    resumed, _ = service.command(
        UUID(original["id"]),
        "resume",
        resume_command(changes, cancelled, []),
        payments[1],
    )
    assert resumed["current_financial"]["net_received"] == "200.00"
    assert resumed["current_financial"]["deposit_validated"] is False
    with pytest.raises(RentalError) as error:
        service.confirm(
            payments[2],
            confirmation(payments, expected_rental_version=resumed["version"]),
            payments[1],
        )
    assert error.value.code == "deposit_required"
    assert service.get(UUID(original["id"]))["allocations"] == []


def test_chg04_expired_quotation_review_without_new_receipts(changes):
    service, payments = changes
    service.clock = lambda: datetime(2026, 10, 10, 12, tzinfo=UTC)
    preview = preview_input(changes, None, valid_until="2026-10-10")
    value = service.change_preview(payments[2], preview, by_quotation=True)
    payload = ResumptionCommand.model_validate(
        {
            **preview.model_dump(mode="json"),
            "catalog_versions": value["after"]["catalog_versions"],
            "applications": [],
            "payments_reviewed": True,
            "reason": "Synthetic expiry review",
            "request_id": str(uuid4()),
        }
    )
    resumed, _ = service.command(
        payments[2], "resume", payload, payments[1], by_quotation=True
    )
    assert resumed["state"] == "review" and resumed["allocations"] == []
    assert resumed["quotation_id"] == str(payments[2])
    assert resumed["current_financial"]["receipts"] == []


def test_chg06_correction_preserves_commitment_signature_revision_and_history(changes):
    service, payments = changes
    original = confirmed(changes)
    state = payments[0].get(payments[2])
    receipt = UUID(state["receipts"][0]["id"])
    payments[0].write(
        payments[2],
        "correction",
        CorrectionCommand.model_validate(
            versions(
                payments[0],
                payments[2],
                amount="100.00",
                method="cash",
                business_date="2026-10-08",
                reason="Synthetic correction",
            )
        ),
        payments[1],
        receipt_id=receipt,
    )
    current = service.get(UUID(original["id"]))
    assert current["allocations"] == original["allocations"]
    assert (
        current["financial_pending"]
        and current["current_financial"]["remaining"] == "400.00"
    )
    updated, _ = service.command(
        UUID(original["id"]), "change", change_command(changes, current), payments[1]
    )
    assert (
        updated["signature_commercial_version"]
        != original["signature_commercial_version"]
    )
    with service.factory.begin() as session, pytest.raises(ProgrammingError):
        session.execute(text("UPDATE rental_history SET reason = 'tampered'"))


def test_migration_metadata_downgrade_and_safe_refusal_with_review(changes):
    service, payments = changes
    with service.factory.begin() as session:
        assert (
            compare_metadata(
                MigrationContext.configure(session.connection()), Base.metadata
            )
            == []
        )
    original = confirmed(changes)
    cancel(changes, original)
    with (
        service.factory.begin() as session,
        pytest.raises(ProgrammingError, match="newer rental states"),
    ):
        command.downgrade(migration_config(session.connection()), "0008_rentals")


def test_chg02_custom_kit_dates_swap_excludes_self_preserves_other_and_maintenance(
    changes,
):
    from decimal import Decimal

    from rentalops_api.catalog_contracts import KitItemInput
    from rentalops_api.catalog_models import Product

    service, payments = changes
    original = confirmed(changes)
    later = create(
        payments[3],
        pickup_date="2026-10-20",
        event_date="2026-10-21",
        return_date="2026-10-22",
    )
    other_payments = (*payments[:2], UUID(later["id"]), payments[3], later)
    paid(other_payments)
    other = service.confirm(
        other_payments[2], confirmation(other_payments), payments[1]
    )[0]
    payload = preview_input(changes, original, return_date="2026-10-14")
    kit = payload.draft.lines[0].model_copy(
        update={
            "items": [
                KitItemInput(product_id=pid, quantity=1)
                for name, pid in payments[3][2].items()
                if name in {"arch", "vase"}
            ],
            "unit_price": Decimal("195.00"),
            "negotiation_reason": "Synthetic custom composition",
        }
    )
    payload = payload.model_copy(
        update={
            "draft": payload.draft.model_copy(
                update={"lines": [kit, payload.draft.lines[1]]}
            )
        }
    )
    preview = service.change_preview(UUID(original["id"]), payload)
    assert sorted(row["demand"] for row in preview["after"]["capacity"]) == [2, 3]
    command_payload = ChangeCommand.model_validate(
        {
            **payload.model_dump(mode="json"),
            "catalog_versions": preview["after"]["catalog_versions"],
            "request_id": str(uuid4()),
            "reason": "Synthetic kit and dates swap",
        }
    )
    changed, _ = service.command(
        UUID(original["id"]), "change", command_payload, payments[1]
    )
    assert sorted(row["quantity"] for row in changed["allocations"]) == [2, 3]
    assert {row["return_date"] for row in changed["allocations"]} == {"2026-10-14"}
    overlapping = change_command(
        changes,
        changed,
        pickup_date="2026-10-20",
        event_date="2026-10-21",
        return_date="2026-10-22",
    )
    with pytest.raises(RentalError) as error:
        service.command(UUID(original["id"]), "change", overlapping, payments[1])
    assert error.value.code == "capacity_conflict"
    assert service.get(UUID(original["id"])) == changed
    cancel(changes, changed)
    assert service.get(UUID(other["id"])) == other
    with service.factory() as session:
        assert session.get(Product, payments[3][2]["vase"]).maintenance_quantity == 1


def test_chg06_simultaneous_same_key_and_financial_change_cannot_overwrite(changes):
    service, payments = changes
    original = confirmed(changes)
    payload = change_command(changes, original)
    barrier = Barrier(2)

    def same_key(_):
        barrier.wait()
        return service.command(UUID(original["id"]), "change", payload, payments[1])

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(same_key, range(2)))
    assert results[0][0] == results[1][0]
    assert sorted(row[1] for row in results) == [False, True]
    current = results[0][0]
    next_change = change_command(changes, current)
    receipt = payments[0].get(payments[2])["receipts"][0]
    correction = CorrectionCommand.model_validate(
        versions(
            payments[0],
            payments[2],
            amount="100.00",
            method="cash",
            business_date="2026-10-08",
            reason="Synthetic concurrent coverage change",
        )
    )
    barrier = Barrier(2)

    def mutate(operation):
        barrier.wait()
        try:
            if operation == "change":
                return service.command(
                    UUID(current["id"]), "change", next_change, payments[1]
                )[0]
            return payments[0].write(
                payments[2],
                "correction",
                correction,
                payments[1],
                receipt_id=UUID(receipt["id"]),
            )[0]
        except (RentalError, PaymentError) as error:
            return error.code

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(mutate, ["change", "correction"]))
    assert sum(isinstance(row, dict) for row in outcomes) == 1
    assert "version_conflict" in outcomes
    assert service.get(UUID(original["id"]))["allocations"] == original["allocations"]


def test_chg05_reference_saved_through_quotation_uses_current_prices_new_id_zero_money(
    changes,
):
    from decimal import Decimal

    from rentalops_api.catalog_models import Kit
    from rentalops_api.rental_changes import copy_draft

    from .test_quotations import command_for

    service, payments = changes
    original = confirmed(changes)
    with service.factory.begin() as session:
        kit = session.get(Kit, payments[3][2]["kit"])
        kit.price = Decimal("250.00")
        kit.version += 1
    # Exercise the reference builder and #10 saving without manufacturing a #14
    # completed state. The completed-only endpoint guard is tested separately.
    draft = copy_draft(original["commercial_snapshot"], payments[3][2]["customer"])
    copied, _ = payments[3][0].write(command_for(payments[3][0], draft), payments[1])
    assert copied["id"] != original["quotation_id"] and copied["total"] == "510.00"
    financial = payments[0].get(UUID(copied["id"]))
    assert financial["receipts"] == [] and financial["net_received"] == "0.00"
    assert service.get(UUID(original["id"])) == original


def test_upgrade_backfill_and_review_require_fresh_reconciliation(
    changes,
):
    service, payments = changes
    original = confirmed(changes)
    with service.factory.begin() as session:
        config = migration_config(session.connection())
        command.downgrade(config, "0008_rentals")
        command.upgrade(config, "head")
    assert service.get(UUID(original["id"])) == original
    history = service.history(UUID(original["id"]))["items"][0]
    assert history["after"]["commercial"] == original["commercial_snapshot"]
    assert history["after"]["financial"] == original["financial_snapshot"]
    cancelled = cancel(changes, original)
    payload = resume_command(
        changes, cancelled, [allocation(payments[0].get(payments[2]))]
    )
    with pytest.raises(RentalError) as error:
        service.command(
            UUID(original["id"]),
            "resume",
            payload.model_copy(update={"payments_reviewed": False}),
            payments[1],
        )
    assert error.value.code == "review_required"
    resumed, _ = service.command(UUID(original["id"]), "resume", payload, payments[1])
    revised, _ = service.command(
        UUID(original["id"]), "change", change_command(changes, resumed), payments[1]
    )
    assert revised["state"] == "review" and revised["allocations"] == []
    assert revised["current_financial"]["requires_reconciliation"] is True
    with pytest.raises(RentalError) as required:
        service.confirm(
            payments[2],
            confirmation(payments, expected_rental_version=revised["version"]),
            payments[1],
        )
    assert required.value.code == "deposit_required"
