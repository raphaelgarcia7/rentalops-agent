from unittest.mock import patch
from uuid import UUID

import pytest
from infra.operations.backup import verified_package

from rentalops_api.database import build_engine, build_session_factory
from rentalops_api.operations import OperationsError
from rentalops_api.payment_contracts import (
    PaymentCommand,
    ReceiptCommand,
    ReconciliationCommand,
)
from rentalops_api.payment_errors import PaymentError
from rentalops_api.payment_storage import ProofStorage
from rentalops_api.payments import PaymentService

from ..unit.test_payment_storage import pdf
from .test_operations import point, recover
from .test_operations import recovery as recovery_fixture
from .test_payments import versions

pytestmark = pytest.mark.integration


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    fixture = recovery_fixture.__wrapped__(tmp_path, monkeypatch)
    try:
        yield next(fixture)
    finally:
        fixture.close()


def test_real_encrypted_backup_restores_original_proofs_payments_and_history(recovery):
    service = PaymentService(
        recovery["auth"].factory, ProofStorage(recovery["roots"]["photos"])
    )
    identifier = UUID(recovery["quote"]["id"])
    actor = recovery["actor"]
    state, _ = service.write(
        identifier,
        "receipt",
        ReceiptCommand.model_validate(
            versions(
                service,
                identifier,
                amount="400.00",
                method="pix",
                business_date="2026-10-08",
            )
        ),
        actor,
    )
    receipt = state["receipts"][0]["id"]
    state, _ = service.write(
        identifier,
        "reconciliation",
        ReconciliationCommand.model_validate(
            versions(
                service,
                identifier,
                applications=[
                    {"receipt_id": receipt, "deposit": "200.00", "balance": "200.00"}
                ],
                reason="Synthetic explicit full payment",
            )
        ),
        actor,
    )
    state, _ = service.write(
        identifier,
        "proof",
        PaymentCommand.model_validate(versions(service, identifier)),
        actor,
        UUID(receipt),
        (pdf(), "application/pdf"),
    )
    proof = state["receipts"][0]["proofs"][0]
    published = point(recovery)
    with verified_package(
        published / "manifest.json", recovery["key"], recovery["roots"]["scratch"]
    ) as (_, manifest):
        assert len(manifest["database"]["proofs"]) == 1
        assert manifest["database"]["proofs"][0]["sha256"] == proof["sha256"]
        assert manifest["database"]["tables"]["payment_history"]["count"] == 3
    target = recovery["database"]("restore")
    result = recover(recovery, published / "manifest.json", target)
    assert result["status"] == "restored"
    engine = build_engine(target)
    try:
        restored = PaymentService(
            build_session_factory(engine), ProofStorage(recovery["roots"]["restored"])
        )
        assert restored.get(identifier) == state
        assert restored.history(identifier) == service.history(identifier)
        assert restored.download(identifier, UUID(proof["id"]))[0] == pdf()
    finally:
        engine.dispose()
    with (
        patch.object(
            ProofStorage,
            "read",
            side_effect=PaymentError(
                503, "storage_unavailable", "Synthetic unavailable proof"
            ),
        ),
        pytest.raises(OperationsError),
    ):
        point(recovery)
    assert [path.name for path in recovery["roots"]["backups"].iterdir()] == [
        published.name
    ]
