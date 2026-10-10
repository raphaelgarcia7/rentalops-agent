"""Manual financial commands. All effects, history and replay commit together."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from rentalops_api.auth import Identity
from rentalops_api.database import session_scope
from rentalops_api.payment_contracts import (
    CorrectionCommand,
    PaymentCommand,
    PaymentHistoryItem,
    PaymentView,
    ProofView,
    ReceiptCommand,
    ReconciliationCommand,
    RefundCommand,
)
from rentalops_api.payment_errors import PaymentError, conflict, invalid
from rentalops_api.payment_models import (
    PaymentAccount,
    PaymentAllocation,
    PaymentHistory,
    PaymentProof,
    PaymentRefund,
    PaymentRequest,
    Receipt,
    ReceiptRevision,
)
from rentalops_api.payment_storage import ProofStorage, StoredProof, validate_proof
from rentalops_api.quotation_contracts import SAO_PAULO
from rentalops_api.quotation_models import Quotation, QuotationVersion

ZERO = Decimal("0.00")


def money(value: Decimal) -> str:
    return format(value, ".2f")


class PaymentService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        storage: ProofStorage | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.factory = factory
        self.storage = storage or ProofStorage.from_environment()
        self.clock = clock or (lambda: datetime.now(UTC))

    def _quotation(
        self, session: Session, identifier: UUID, *, write: bool = False
    ) -> tuple[Quotation, QuotationVersion]:
        header = session.scalar(
            select(Quotation)
            .where(Quotation.id == identifier)
            .with_for_update(read=not write)
        )
        if header is None:
            raise PaymentError(404, "not_found", "Orçamento não encontrado.")
        offer = session.get(QuotationVersion, (identifier, header.current_version))
        if offer is None:
            raise PaymentError(503, "unavailable", "Versão comercial indisponível.")
        return header, offer

    def _receipts(
        self, session: Session, identifier: UUID, *, locked: bool = False
    ) -> list[Receipt]:
        query = (
            select(Receipt)
            .where(Receipt.quotation_id == identifier)
            .order_by(Receipt.id)
        )
        if locked:
            query = query.with_for_update()
        return list(session.scalars(query))

    def _summary(
        self,
        session: Session,
        header: Quotation,
        offer: QuotationVersion,
        account: PaymentAccount | None,
        distribution: list[dict[str, str]] | None = None,
    ) -> dict[str, object]:
        receipts = self._receipts(session, header.id)
        refunds = list(
            session.scalars(
                select(PaymentRefund)
                .where(PaymentRefund.quotation_id == header.id)
                .order_by(PaymentRefund.created_at, PaymentRefund.id)
            )
        )
        proofs = list(
            session.scalars(
                select(PaymentProof)
                .where(PaymentProof.quotation_id == header.id)
                .order_by(PaymentProof.created_at, PaymentProof.id)
            )
        )
        stale = bool(
            account
            and account.reconciled_quotation_version is not None
            and account.reconciled_quotation_version != header.current_version
        )
        applications = (
            {
                item["receipt_id"]: item
                for item in (
                    distribution
                    if distribution is not None
                    else self._applications(session, account)
                )
            }
            if account and not stale
            else {}
        )
        received, returned, applied_deposit, applied_balance = ZERO, ZERO, ZERO, ZERO
        rows: list[dict[str, object]] = []
        for receipt in receipts:
            revision = session.get(ReceiptRevision, (receipt.id, receipt.revision))
            assert revision is not None
            refunded = sum(
                (item.amount for item in refunds if item.receipt_id == receipt.id), ZERO
            )
            net = revision.amount - refunded
            application = applications.get(str(receipt.id), {})
            deposit = Decimal(application.get("deposit", "0.00"))
            balance = Decimal(application.get("balance", "0.00"))
            received += revision.amount
            returned += refunded
            applied_deposit += deposit
            applied_balance += balance
            rows.append(
                {
                    "id": str(receipt.id),
                    "revision": receipt.revision,
                    "amount": money(revision.amount),
                    "method": revision.method,
                    "business_date": revision.business_date.isoformat(),
                    "observation": revision.observation,
                    "actor_id": str(revision.actor_id),
                    "session_id": str(revision.session_id),
                    "created_at": revision.created_at.isoformat(),
                    "refunded": money(refunded),
                    "net": money(net),
                    "applied_deposit": money(deposit),
                    "applied_balance": money(balance),
                    "pending": money(net - deposit - balance),
                    "proofs": [
                        ProofView.model_validate(
                            {key: getattr(proof, key) for key in ProofView.model_fields}
                        ).model_dump(mode="json")
                        for proof in proofs
                        if proof.receipt_id == receipt.id
                    ],
                }
            )
        pending = received - returned - applied_deposit - applied_balance
        needs = bool(
            stale or (account and account.requires_reconciliation) or pending > 0
        )
        deposit_validated = bool(
            account
            and account.reconciled_quotation_version == header.current_version
            and not account.requires_reconciliation
            and applied_deposit == offer.estimated_deposit
        )
        return PaymentView.model_validate(
            {
                "quotation_id": str(header.id),
                "quotation_version": header.current_version,
                "financial_version": account.version if account else 0,
                "reconciled_quotation_version": account.reconciled_quotation_version
                if account
                else None,
                "total": money(offer.total),
                "estimated_deposit": money(offer.estimated_deposit),
                "estimated_balance": money(offer.estimated_balance),
                "received": money(received),
                "refunded": money(returned),
                "net_received": money(received - returned),
                "applied_deposit": money(applied_deposit),
                "applied_balance": money(applied_balance),
                "deposit_remaining": money(offer.estimated_deposit - applied_deposit),
                "balance_remaining": money(offer.estimated_balance - applied_balance),
                "remaining": money(offer.total - applied_deposit - applied_balance),
                "pending": money(pending),
                "excess": money(max(ZERO, received - returned - offer.total)),
                "deposit_validated": deposit_validated,
                "fully_paid": deposit_validated
                and applied_balance == offer.estimated_balance,
                "requires_reconciliation": needs,
                "commercial_version_pending": stale,
                "receipts": rows,
                "refunds": [
                    {
                        key: getattr(item, key)
                        for key in (
                            "id",
                            "receipt_id",
                            "amount",
                            "method",
                            "business_date",
                            "reason",
                            "actor_id",
                            "session_id",
                            "created_at",
                        )
                    }
                    | {"amount": money(item.amount)}
                    for item in refunds
                ],
            }
        ).model_dump(mode="json")

    def _applications(
        self, session: Session, account: PaymentAccount
    ) -> list[dict[str, str]]:
        return [
            {
                "receipt_id": str(row.receipt_id),
                "deposit": money(row.deposit),
                "balance": money(row.balance),
            }
            for row in session.scalars(
                select(PaymentAllocation)
                .where(
                    PaymentAllocation.quotation_id == account.quotation_id,
                    PaymentAllocation.financial_version == account.version,
                )
                .order_by(PaymentAllocation.receipt_id)
            )
        ]

    def get(self, identifier: UUID) -> dict[str, object]:
        with session_scope(self.factory) as session:
            header, offer = self._quotation(session, identifier)
            return self._summary(
                session, header, offer, session.get(PaymentAccount, identifier)
            )

    def history(
        self, identifier: UUID, page: int = 1, page_size: int = 50
    ) -> dict[str, object]:
        if page < 1 or not 1 <= page_size <= 100:
            raise invalid("Paginação inválida.")
        with session_scope(self.factory) as session:
            self._quotation(session, identifier)
            condition = PaymentHistory.quotation_id == identifier
            total = (
                session.scalar(
                    select(func.count()).select_from(PaymentHistory).where(condition)
                )
                or 0
            )
            rows = session.scalars(
                select(PaymentHistory)
                .where(condition)
                .order_by(PaymentHistory.created_at, PaymentHistory.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            items = [
                PaymentHistoryItem.model_validate(
                    {key: getattr(row, key) for key in PaymentHistoryItem.model_fields}
                ).model_dump(mode="json")
                for row in rows
            ]
            return {
                "items": items,
                "page": page,
                "page_size": page_size,
                "total": total,
            }

    def _net(self, session: Session, receipt: Receipt) -> Decimal:
        revision = session.get(ReceiptRevision, (receipt.id, receipt.revision))
        assert revision is not None
        returned = session.scalar(
            select(func.coalesce(func.sum(PaymentRefund.amount), 0)).where(
                PaymentRefund.receipt_id == receipt.id
            )
        )
        return revision.amount - cast(Decimal, returned)

    def _reconcile(
        self,
        session: Session,
        account: PaymentAccount,
        offer: QuotationVersion,
        receipts: list[Receipt],
        payload: ReconciliationCommand,
    ) -> list[dict[str, str]]:
        by_id = {receipt.id: receipt for receipt in receipts}
        deposit, balance, deposit_sources = ZERO, ZERO, 0
        for item in payload.applications:
            receipt = by_id.get(item.receipt_id)
            if receipt is None:
                raise PaymentError(
                    404, "not_found", "Recebimento não pertence a este orçamento."
                )
            net = self._net(session, receipt)
            if item.deposit + item.balance > net:
                raise invalid(
                    "A aplicação supera o valor líquido disponível da origem."
                )
            if item.deposit > 0:
                deposit_sources += 1
                if (
                    item.deposit != offer.estimated_deposit
                    or net < offer.estimated_deposit
                ):
                    raise invalid(
                        "O sinal exige o valor completo em um único "
                        "recebimento líquido."
                    )
            deposit += item.deposit
            balance += item.balance
        if (
            deposit_sources > 1
            or deposit > offer.estimated_deposit
            or balance > offer.estimated_balance
        ):
            raise invalid("A distribuição supera o sinal ou saldo da versão comercial.")
        account.reconciled_quotation_version = offer.number
        account.requires_reconciliation = False
        return [item.model_dump(mode="json") for item in payload.applications]

    def _invalidate_coverage(
        self,
        session: Session,
        account: PaymentAccount,
        receipts: list[Receipt],
        applications: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        net = {str(receipt.id): self._net(session, receipt) for receipt in receipts}
        valid = [
            item
            for item in applications
            if Decimal(item["deposit"]) + Decimal(item["balance"])
            <= net[item["receipt_id"]]
        ]
        if len(valid) != len(applications):
            account.requires_reconciliation = True
        return valid

    def write(
        self,
        identifier: UUID,
        operation: str,
        payload: PaymentCommand,
        identity: Identity,
        receipt_id: UUID | None = None,
        proof: tuple[bytes, str | None] | None = None,
    ) -> tuple[dict[str, object], bool]:
        upload_type = validate_proof(*proof) if proof else None
        canonical = {
            "quotation_id": str(identifier),
            "receipt_id": str(receipt_id) if receipt_id else None,
            "payload": payload.model_dump(mode="json"),
        }
        if proof:
            canonical["proof"] = {
                "sha256": hashlib.sha256(proof[0]).hexdigest(),
                "content_type": upload_type,
            }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        lock_id = int.from_bytes(
            hashlib.sha256(
                f"payment:{identity.user_id}:{operation}:{payload.request_id}".encode()
            ).digest()[:8],
            "big",
            signed=True,
        )
        stored: StoredProof | None = None
        try:
            with session_scope(self.factory) as session:
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id}
                )
                replay = session.get(
                    PaymentRequest, (identity.user_id, operation, payload.request_id)
                )
                if replay:
                    if replay.payload_hash != digest:
                        raise conflict("idempotency_conflict")
                    return replay.result, True
                header, offer = self._quotation(session, identifier, write=True)
                if header.current_version != payload.expected_quotation_version:
                    raise conflict()
                account = session.scalar(
                    select(PaymentAccount)
                    .where(PaymentAccount.quotation_id == identifier)
                    .with_for_update()
                )
                if account is None:
                    account = PaymentAccount(
                        quotation_id=identifier,
                        version=0,
                        requires_reconciliation=False,
                    )
                    session.add(account)
                    session.flush()
                if account.version != payload.expected_financial_version:
                    raise conflict()
                receipts = self._receipts(session, identifier, locked=True)
                before = self._summary(session, header, offer, account)
                distribution = self._applications(session, account)
                by_id = {receipt.id: receipt for receipt in receipts}
                reason = getattr(payload, "reason", None)
                receipt: Receipt | None
                if (
                    isinstance(payload, ReceiptCommand)
                    and payload.business_date
                    > self.clock().astimezone(SAO_PAULO).date()
                ):
                    raise invalid(
                        "Registre somente recebimento ou devolução já realizados."
                    )
                if operation in {"receipt", "correction"}:
                    if not isinstance(payload, ReceiptCommand):
                        raise invalid("Comando de recebimento inválido.")
                    if operation == "receipt":
                        receipt = Receipt(
                            id=uuid4(), quotation_id=identifier, revision=1
                        )
                        session.add(receipt)
                        session.flush()
                        receipts.append(receipt)
                    else:
                        if not isinstance(payload, CorrectionCommand):
                            raise invalid("Correção exige motivo.")
                        receipt = by_id.get(receipt_id) if receipt_id else None
                        if receipt is None:
                            raise PaymentError(
                                404,
                                "not_found",
                                "Recebimento não encontrado neste orçamento.",
                            )
                        current = session.get(
                            ReceiptRevision, (receipt.id, receipt.revision)
                        )
                        assert current is not None
                        if payload.amount < current.amount - self._net(
                            session, receipt
                        ):
                            raise invalid(
                                "O valor corrigido não pode ser inferior "
                                "ao já devolvido."
                            )
                        receipt.revision += 1
                    session.add(
                        ReceiptRevision(
                            receipt_id=receipt.id,
                            number=receipt.revision,
                            amount=payload.amount,
                            method=payload.method,
                            business_date=payload.business_date,
                            observation=payload.observation,
                            reason=reason,
                            actor_id=identity.user_id,
                            session_id=identity.session_id,
                            created_at=self.clock(),
                        )
                    )
                    session.flush()
                    distribution = self._invalidate_coverage(
                        session, account, receipts, distribution
                    )
                elif operation == "reconciliation" and isinstance(
                    payload, ReconciliationCommand
                ):
                    distribution = self._reconcile(
                        session, account, offer, receipts, payload
                    )
                elif operation == "refund" and isinstance(payload, RefundCommand):
                    receipt = by_id.get(payload.receipt_id)
                    if receipt is None:
                        raise PaymentError(
                            404,
                            "not_found",
                            "Recebimento não encontrado neste orçamento.",
                        )
                    if payload.amount > self._net(session, receipt):
                        raise invalid(
                            "A devolução registrada supera o líquido "
                            "disponível da origem."
                        )
                    session.add(
                        PaymentRefund(
                            quotation_id=identifier,
                            receipt_id=receipt.id,
                            amount=payload.amount,
                            method=payload.method,
                            business_date=payload.business_date,
                            reason=payload.reason,
                            actor_id=identity.user_id,
                            session_id=identity.session_id,
                            created_at=self.clock(),
                        )
                    )
                    session.flush()
                    distribution = self._invalidate_coverage(
                        session, account, receipts, distribution
                    )
                elif operation == "proof" and proof and upload_type:
                    if receipt_id not in by_id:
                        raise PaymentError(
                            404,
                            "not_found",
                            "Recebimento não encontrado neste orçamento.",
                        )
                    stored = self.storage.write(proof[0], upload_type)
                    session.add(
                        PaymentProof(
                            quotation_id=identifier,
                            receipt_id=receipt_id,
                            storage_key=stored.key,
                            content_type=stored.content_type,
                            size=stored.size,
                            sha256=stored.sha256,
                            actor_id=identity.user_id,
                            session_id=identity.session_id,
                            created_at=self.clock(),
                        )
                    )
                else:
                    raise invalid("Operação financeira inválida.")
                account.version += 1
                session.flush()
                result = self._summary(session, header, offer, account, distribution)
                session.add(
                    PaymentHistory(
                        quotation_id=identifier,
                        financial_version=account.version,
                        quotation_version=header.current_version,
                        operation=operation,
                        actor_id=identity.user_id,
                        session_id=identity.session_id,
                        reason=reason,
                        before=before,
                        after=result,
                        created_at=self.clock(),
                    )
                )
                session.flush()
                session.add_all(
                    [
                        PaymentAllocation(
                            quotation_id=identifier,
                            financial_version=account.version,
                            receipt_id=UUID(item["receipt_id"]),
                            deposit=Decimal(item["deposit"]),
                            balance=Decimal(item["balance"]),
                        )
                        for item in distribution
                    ]
                )
                session.add(
                    PaymentRequest(
                        actor_id=identity.user_id,
                        operation=operation,
                        request_id=payload.request_id,
                        payload_hash=digest,
                        quotation_id=identifier,
                        financial_version=account.version,
                        result=result,
                    )
                )
                session.commit()
                return result, False
        except BaseException:
            if stored:
                self._compensate_uncommitted(identifier, stored.key)
            raise

    def _compensate_uncommitted(self, identifier: UUID, key: str) -> None:
        # A commit may have reached PostgreSQL before its acknowledgement was
        # lost. Wait for that quotation transaction to finish, then check fresh
        # committed metadata. Never delete a durable proof on an unknown result.
        try:
            with session_scope(self.factory) as session:
                found = session.scalar(
                    select(Quotation.id)
                    .where(Quotation.id == identifier)
                    .with_for_update()
                )
                if found is None:
                    return
                persisted = session.scalar(
                    select(PaymentProof.id).where(PaymentProof.storage_key == key)
                )
                if persisted is None:
                    self.storage.compensate(key)
        except Exception:
            # Retain only this attempt's possible orphan if the outcome cannot
            # be verified; broad cleanup would risk committed historical bytes.
            return

    def download(self, identifier: UUID, proof_id: UUID) -> tuple[bytes, str, str]:
        with session_scope(self.factory) as session:
            self._quotation(session, identifier)
            proof = session.get(PaymentProof, proof_id)
            if proof is None or proof.quotation_id != identifier:
                raise PaymentError(
                    404, "not_found", "Comprovante não encontrado neste orçamento."
                )
            data = self.storage.read(proof.storage_key, proof.size, proof.sha256)
            extension = {
                "application/pdf": "pdf",
                "image/jpeg": "jpg",
                "image/png": "png",
            }[proof.content_type]
            return data, proof.content_type, f"comprovante-{proof.id}.{extension}"
