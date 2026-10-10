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
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from rentalops_api.auth import Identity
from rentalops_api.models import AuthSession, Base, User
from rentalops_api.payment_contracts import (
    CorrectionCommand,
    PaymentCommand,
    ReceiptCommand,
    ReconciliationCommand,
    RefundCommand,
)
from rentalops_api.payment_errors import PaymentError
from rentalops_api.payment_models import (
    PaymentAllocation,
    PaymentHistory,
    PaymentRequest,
    ReceiptRevision,
)
from rentalops_api.payment_storage import ProofStorage
from rentalops_api.payments import PaymentService

from ..conftest import migration_config
from ..unit.test_payment_storage import pdf
from .test_quotations import command_for, create, revision
from .test_quotations import quotations as quotation_fixture

pytestmark = pytest.mark.integration


@pytest.fixture
def payments(migrated_engine, tmp_path):
    quotations = quotation_fixture.__wrapped__(migrated_engine)
    offer = create(quotations)
    service = PaymentService(quotations[0].factory, ProofStorage(tmp_path))
    return service, quotations[1], UUID(offer["id"]), quotations, offer


def versions(service, identifier, **changes):
    state = service.get(identifier)
    return {
        "request_id": str(uuid4()),
        "expected_financial_version": state["financial_version"],
        "expected_quotation_version": state["quotation_version"],
        **changes,
    }


def receive(payments, amount="200.00", method="pix", **changes):
    service, actor, identifier, *_ = payments
    payload = ReceiptCommand.model_validate(
        versions(
            service,
            identifier,
            amount=amount,
            method=method,
            business_date="2026-10-08",
            **changes,
        )
    )
    return service.write(identifier, "receipt", payload, actor)[0]


def reconcile(payments, applications, **changes):
    service, actor, identifier, *_ = payments
    payload = ReconciliationCommand.model_validate(
        versions(
            service,
            identifier,
            applications=applications,
            reason="Synthetic explicit agreement",
            **changes,
        )
    )
    return service.write(identifier, "reconciliation", payload, actor)[0]


def allocation(state, index=0, deposit="200.00", balance="0.00"):
    return {
        "receipt_id": state["receipts"][index]["id"],
        "deposit": deposit,
        "balance": balance,
    }


def test_migration_roundtrip_constraints_metadata_and_immutable_history(
    isolated_engine,
):
    with isolated_engine.begin() as connection:
        config = migration_config(connection)
        command.upgrade(config, "head")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0007_payments"
        )
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )
        assert "payment_allocations" in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        command.downgrade(config, "0006_quotations")
        assert "payment_accounts" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )


@pytest.mark.parametrize(
    "discount,total,deposit,balance",
    [
        (None, "400.00", "200.00", "200.00"),
        (
            {"kind": "percent", "value": "10.00", "reason": "Synthetic discount"},
            "360.00",
            "180.00",
            "180.00",
        ),
    ],
)
def test_commercial_calculation_remains_authoritative(
    payments, discount, total, deposit, balance
):
    service, _, _, quotations, _ = payments
    offer = create(quotations, discount=discount)
    result = service.get(UUID(offer["id"]))
    assert (
        result["total"],
        result["estimated_deposit"],
        result["estimated_balance"],
    ) == (total, deposit, balance)
    odd = create(
        quotations,
        lines=[
            {
                "kind": "product",
                "source_id": str(quotations[2]["vase"]),
                "quantity": 1,
                "unit_price": "100.01",
                "negotiation_reason": "Synthetic exact odd cent",
            }
        ],
    )
    result = service.get(UUID(odd["id"]))
    assert (result["estimated_deposit"], result["estimated_balance"]) == (
        "50.01",
        "50.00",
    )


def test_single_250_is_pending_then_explicit_distribution_200_50(payments):
    service, actor, identifier, *_ = payments
    state = receive(payments, "250.00")
    assert state["received"] == state["pending"] == "250.00"
    assert not state["deposit_validated"] and "reservation_confirmed" not in state
    assert state["receipts"][0]["actor_id"] == str(actor.user_id)
    state = reconcile(payments, [allocation(state, balance="50.00")])
    assert (
        state["applied_deposit"],
        state["applied_balance"],
        state["balance_remaining"],
    ) == ("200.00", "50.00", "150.00")
    assert (
        state["deposit_validated"]
        and not state["fully_paid"]
        and "reservation_confirmed" not in state
    )
    assert service.history(identifier)["total"] == 2


def test_partial_receipts_never_accumulate_deposit_but_balance_can_have_parts(payments):
    receive(payments, "100.00", "pix")
    state = receive(payments, "100.00", "cash")
    for apps in (
        [allocation(state, deposit="100.00"), allocation(state, 1, deposit="100.00")],
        [allocation(state)],
    ):
        with pytest.raises(PaymentError) as error:
            reconcile(payments, apps)
        assert error.value.status == 422
    state = reconcile(
        payments,
        [
            allocation(state, deposit="0.00", balance="100.00"),
            allocation(state, 1, deposit="0.00", balance="100.00"),
        ],
    )
    assert not state["deposit_validated"] and state["balance_remaining"] == "0.00"
    state = receive(payments, "200.00", "card")
    apps = [
        {
            "receipt_id": row["id"],
            "deposit": "200.00" if row["method"] == "card" else "0.00",
            "balance": "0.00" if row["method"] == "card" else "100.00",
        }
        for row in state["receipts"]
    ]
    state = reconcile(payments, apps)
    assert state["fully_paid"] and state["remaining"] == "0.00"


def test_integral_excess_substitutive_distribution_and_separate_refund(payments):
    service, actor, identifier, *_ = payments
    state = receive(payments, "450.00")
    assert state["excess"] == "50.00" and not state["fully_paid"]
    state = reconcile(payments, [allocation(state, balance="200.00")])
    assert (
        state["fully_paid"]
        and state["pending"] == "50.00"
        and state["remaining"] == "0.00"
    )
    state = reconcile(payments, [allocation(state, balance="100.00")])
    assert (
        state["applied_balance"] == "100.00" and state["balance_remaining"] == "100.00"
    )
    payload = RefundCommand.model_validate(
        versions(
            service,
            identifier,
            receipt_id=state["receipts"][0]["id"],
            amount="50.00",
            method="pix",
            business_date="2026-10-08",
            reason="Synthetic money already returned",
        )
    )
    state, replay = service.write(identifier, "refund", payload, actor)
    assert (
        not replay
        and state["received"] == "450.00"
        and state["refunded"] == "50.00"
        and state["net_received"] == "400.00"
        and len(state["refunds"]) == 1
    )
    repeated, replay = service.write(identifier, "refund", payload, actor)
    assert replay and repeated == state
    invalid_refund = payload.model_copy(
        update={
            "request_id": uuid4(),
            "expected_financial_version": state["financial_version"],
            "amount": Decimal("400.01"),
        }
    )
    with pytest.raises(PaymentError):
        service.write(identifier, "refund", invalid_refund, actor)


def test_correction_preserves_original_reason_author_and_invalidates_overcoverage(
    payments,
):
    service, actor, identifier, *_ = payments
    state = receive(payments, "400.00")
    state = reconcile(payments, [allocation(state, balance="200.00")])
    receipt = state["receipts"][0]["id"]
    payload = CorrectionCommand.model_validate(
        versions(
            service,
            identifier,
            amount="100.00",
            method="cash",
            business_date="2026-10-07",
            observation="Synthetic corrected note",
            reason="Synthetic clerical correction",
        )
    )
    state, _ = service.write(identifier, "correction", payload, actor, UUID(receipt))
    assert state["refunded"] == "0.00" and state["received"] == "100.00"
    assert state["applied_deposit"] == state["applied_balance"] == "0.00"
    assert state["requires_reconciliation"] and not state["deposit_validated"]
    with service.factory() as session:
        revisions = list(
            session.scalars(
                select(ReceiptRevision)
                .where(ReceiptRevision.receipt_id == UUID(receipt))
                .order_by(ReceiptRevision.number)
            )
        )
        assert [row.amount for row in revisions] == [
            Decimal("400.00"),
            Decimal("100.00"),
        ]
        assert (
            revisions[1].reason == payload.reason
            and revisions[1].actor_id == actor.user_id
        )
    event = service.history(identifier)["items"][-1]
    assert (
        event["before"]["received"] == "400.00"
        and event["after"]["received"] == "100.00"
    )


def test_commercial_revision_requires_explicit_current_conference_and_no_old_write(
    payments,
):
    service, actor, identifier, quotations, offer = payments
    state = receive(payments)
    state = reconcile(payments, [allocation(state)])
    old = ReceiptCommand.model_validate(
        versions(
            service,
            identifier,
            amount="20.00",
            method="cash",
            business_date="2026-10-08",
        )
    )
    quotations[0].write(
        command_for(
            quotations[0],
            revision(
                quotations,
                offer,
                discount={
                    "kind": "amount",
                    "value": "20.00",
                    "reason": "Synthetic new agreement",
                },
            ),
            reason="Synthetic commercial revision",
        ),
        actor,
        identifier,
    )
    state = service.get(identifier)
    assert state["commercial_version_pending"] and not state["deposit_validated"]
    assert state["applied_deposit"] == "0.00" and state["received"] == "200.00"
    with pytest.raises(PaymentError) as error:
        service.write(identifier, "receipt", old, actor)
    assert (
        error.value.status == 409
        and service.get(identifier)["financial_version"] == state["financial_version"]
    )
    state = reconcile(payments, [allocation(state, deposit="190.00", balance="10.00")])
    assert state["deposit_validated"] and state["reconciled_quotation_version"] == 2


def second_actor(service):
    now = datetime.now(UTC)
    with service.factory.begin() as session:
        user = User(email=f"synthetic-financial-{uuid4().hex}@example.invalid")
        session.add(user)
        session.flush()
        auth = AuthSession(
            user_id=user.id,
            token_hash=uuid4().hex,
            created_at=now,
            last_activity=now,
            expires_at=now + timedelta(hours=12),
        )
        session.add(auth)
        session.flush()
        return Identity(user.id, auth.id, auth.expires_at, now + timedelta(hours=1))


def test_concurrent_replay_is_one_money_event_payload_conflict_and_rollback(payments):
    service, actor, identifier, *_ = payments
    payload = ReceiptCommand.model_validate(
        versions(
            service,
            identifier,
            amount="200.00",
            method="pix",
            business_date="2026-10-08",
        )
    )
    barrier = Barrier(2)

    def execute():
        barrier.wait()
        return service.write(identifier, "receipt", payload, actor)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute(), range(2)))
    assert sorted(row[1] for row in results) == [False, True]
    assert results[0][0] == results[1][0]
    with pytest.raises(PaymentError) as error:
        service.write(
            identifier,
            "receipt",
            payload.model_copy(update={"amount": Decimal("201.00")}),
            actor,
        )
    assert error.value.code == "idempotency_conflict"
    before = service.get(identifier)
    another = ReceiptCommand.model_validate(
        versions(
            service,
            identifier,
            amount="10.00",
            method="cash",
            business_date="2026-10-08",
        )
    )
    with (
        patch.object(Session, "commit", side_effect=RuntimeError("Synthetic rollback")),
        pytest.raises(RuntimeError),
    ):
        service.write(identifier, "receipt", another, actor)
    assert service.get(identifier) == before
    with service.factory() as session:
        assert (
            len(list(session.scalars(select(PaymentRequest))))
            == len(list(session.scalars(select(PaymentHistory))))
            == 1
        )


def test_two_users_reconciling_same_version_and_refund_correction_race(payments):
    service, actor, identifier, *_ = payments
    other = second_actor(service)
    state = receive(payments, "400.00")
    barrier = Barrier(2)

    def execute(identity):
        payload = ReconciliationCommand.model_validate(
            versions(
                service,
                identifier,
                applications=[allocation(state, balance="200.00")],
                reason="Synthetic concurrent confirmation",
            )
        )
        barrier.wait()
        try:
            return service.write(identifier, "reconciliation", payload, identity)[0]
        except PaymentError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, [actor, other]))
    assert sum(isinstance(row, dict) for row in results) == 1 and 409 in results
    state = service.get(identifier)
    receipt = UUID(state["receipts"][0]["id"])
    correction = CorrectionCommand.model_validate(
        versions(
            service,
            identifier,
            amount="50.00",
            method="cash",
            business_date="2026-10-08",
            reason="Synthetic corrected amount",
        )
    )
    refund = RefundCommand.model_validate(
        versions(
            service,
            identifier,
            receipt_id=str(receipt),
            amount="100.00",
            method="pix",
            business_date="2026-10-08",
            reason="Synthetic money already returned",
        )
    )
    barrier = Barrier(2)

    def compete(pair):
        operation, payload, identity = pair
        barrier.wait()
        try:
            return service.write(
                identifier,
                operation,
                payload,
                identity,
                receipt if operation == "correction" else None,
            )[0]
        except PaymentError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                compete, [("correction", correction, actor), ("refund", refund, other)]
            )
        )
    assert sum(isinstance(row, dict) for row in results) == 1 and 409 in results
    state = service.get(identifier)
    assert Decimal(state["net_received"]) >= 0 and not state["deposit_validated"]


def test_concurrent_commercial_revision_has_no_deadlock_or_old_validation(payments):
    service, actor, identifier, quotations, offer = payments
    state = receive(payments)
    payload = ReconciliationCommand.model_validate(
        versions(
            service,
            identifier,
            applications=[allocation(state)],
            reason="Synthetic race",
        )
    )
    commercial = command_for(
        quotations[0],
        revision(
            quotations,
            offer,
            discount={
                "kind": "amount",
                "value": "20.00",
                "reason": "Synthetic concurrent revision",
            },
        ),
        reason="Synthetic concurrent commercial revision",
    )
    barrier = Barrier(2)

    def financial():
        barrier.wait()
        try:
            return service.write(identifier, "reconciliation", payload, actor)[0]
        except PaymentError as error:
            return error.status

    def revise():
        barrier.wait()
        return quotations[0].write(commercial, actor, identifier)[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        f = pool.submit(financial)
        c = pool.submit(revise)
        result = f.result()
        assert c.result()["version"] == 2
    assert isinstance(result, dict) or result == 409
    state = service.get(identifier)
    assert state["quotation_version"] == 2 and not state["deposit_validated"]


def test_proof_no_financial_validation_replay_isolation_and_commit_compensation(
    payments,
):
    service, actor, identifier, quotations, _ = payments
    state = receive(payments)
    receipt = UUID(state["receipts"][0]["id"])
    payload = PaymentCommand.model_validate(versions(service, identifier))
    state, _ = service.write(
        identifier, "proof", payload, actor, receipt, (pdf(), "application/pdf")
    )
    assert not state["deposit_validated"] and state["pending"] == "200.00"
    assert len(state["receipts"][0]["proofs"]) == 1
    files = list(service.storage.root.iterdir())
    assert service.write(
        identifier, "proof", payload, actor, receipt, (pdf(), "application/pdf")
    ) == (state, True)
    proof_id = UUID(state["receipts"][0]["proofs"][0]["id"])
    assert service.download(identifier, proof_id)[0] == pdf()
    alien = UUID(create(quotations)["id"])
    with pytest.raises(PaymentError) as error:
        service.download(alien, proof_id)
    assert error.value.status == 404
    next_payload = PaymentCommand.model_validate(versions(service, identifier))
    with (
        patch.object(
            Session, "commit", side_effect=RuntimeError("Synthetic commit failure")
        ),
        pytest.raises(RuntimeError),
    ):
        service.write(
            identifier,
            "proof",
            next_payload,
            actor,
            receipt,
            (pdf(2), "application/pdf"),
        )
    assert (
        list(service.storage.root.iterdir()) == files
        and service.get(identifier) == state
    )


def test_lost_commit_ack_retains_committed_proof_and_replays_original(payments):
    service, actor, identifier, *_ = payments
    state = receive(payments)
    receipt = UUID(state["receipts"][0]["id"])
    payload = PaymentCommand.model_validate(versions(service, identifier))
    original_commit = Session.commit

    def commit_then_lose_ack(session):
        original_commit(session)
        raise RuntimeError("Synthetic acknowledgement lost after actual commit")

    with (
        patch.object(Session, "commit", commit_then_lose_ack),
        pytest.raises(RuntimeError),
    ):
        service.write(
            identifier, "proof", payload, actor, receipt, (pdf(), "application/pdf")
        )
    committed = service.get(identifier)
    assert committed["financial_version"] == state["financial_version"] + 1
    proof = committed["receipts"][0]["proofs"][0]
    assert service.download(identifier, UUID(proof["id"]))[0] == pdf()
    assert service.write(
        identifier, "proof", payload, actor, receipt, (pdf(), "application/pdf")
    ) == (committed, True)
    assert len(list(service.storage.root.iterdir())) == 1
    assert service.history(identifier)["total"] == 2


def test_unverifiable_commit_compensation_retains_only_new_possible_orphan(payments):
    service, actor, identifier, *_ = payments
    state = receive(payments)
    receipt = UUID(state["receipts"][0]["id"])
    payload = PaymentCommand.model_validate(versions(service, identifier))
    transaction = service.factory()
    with (
        patch.object(
            service,
            "factory",
            side_effect=[transaction, RuntimeError("Synthetic recovery unavailable")],
        ),
        patch.object(Session, "commit", side_effect=RuntimeError("Synthetic failure")),
        pytest.raises(RuntimeError),
    ):
        service.write(
            identifier, "proof", payload, actor, receipt, (pdf(), "application/pdf")
        )
    assert service.get(identifier) == state
    assert service.history(identifier)["total"] == 1
    files = list(service.storage.root.iterdir())
    assert len(files) == 1 and files[0].read_bytes() == pdf()


def test_history_paging_database_guards_and_correction_below_refunded(payments):
    service, actor, identifier, *_ = payments
    state = receive(payments, "400.00")
    receipt = UUID(state["receipts"][0]["id"])
    refund = RefundCommand.model_validate(
        versions(
            service,
            identifier,
            receipt_id=str(receipt),
            amount="100.00",
            method="cash",
            business_date="2026-10-08",
            reason="Synthetic return",
        )
    )
    service.write(identifier, "refund", refund, actor)
    correction = CorrectionCommand.model_validate(
        versions(
            service,
            identifier,
            amount="99.99",
            method="cash",
            business_date="2026-10-08",
            reason="Synthetic invalid correction",
        )
    )
    with pytest.raises(PaymentError):
        service.write(identifier, "correction", correction, actor, receipt)
    first = service.history(identifier, page_size=1)
    second = service.history(identifier, page=2, page_size=1)
    assert first["total"] == 2 and first["items"][0]["id"] != second["items"][0]["id"]
    for table in [
        "payment_receipt_revisions",
        "payment_refunds",
        "payment_history",
        "payment_requests",
    ]:
        with service.factory.begin() as session, pytest.raises(ProgrammingError):
            session.execute(text(f"DELETE FROM {table}"))
    with service.factory.begin() as session, pytest.raises(IntegrityError):
        session.add(
            PaymentAllocation(
                quotation_id=identifier,
                financial_version=1,
                receipt_id=receipt,
                deposit=Decimal("-1"),
                balance=Decimal(0),
            )
        )
        session.flush()
