"""Strict manual-payment commands and private response contracts."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from rentalops_api.catalog_contracts import CatalogPayload, exact_money
from rentalops_api.quotation_contracts import SAO_PAULO, BusinessDate


def payment_money(value: object) -> Decimal:
    if isinstance(value, str) and not re.fullmatch(r"[0-9]+\.[0-9]{2}", value):
        raise ValueError("Use a decimal string with two fractional digits.")
    return exact_money(value)


PaymentMoney = Annotated[Decimal, BeforeValidator(payment_money)]
PositiveMoney = Annotated[PaymentMoney, Field(gt=0)]
Method = Literal["pix", "cash", "card"]
Reason = Annotated[str, Field(min_length=1, max_length=1000)]


class PaymentCommand(CatalogPayload):
    request_id: UUID
    expected_financial_version: int = Field(strict=True, ge=0, le=2_147_483_647)
    expected_quotation_version: int = Field(strict=True, ge=1, le=2_147_483_647)


class ReceiptCommand(PaymentCommand):
    amount: PositiveMoney
    method: Method
    business_date: BusinessDate
    observation: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def not_future(self) -> ReceiptCommand:
        if self.business_date > datetime.now(UTC).astimezone(SAO_PAULO).date():
            raise ValueError("A receipt must already have happened.")
        return self


class CorrectionCommand(ReceiptCommand):
    reason: Reason


class RefundCommand(ReceiptCommand):
    receipt_id: UUID
    reason: Reason


class Application(CatalogPayload):
    receipt_id: UUID
    deposit: PaymentMoney
    balance: PaymentMoney


class ReconciliationCommand(PaymentCommand):
    applications: list[Application] = Field(max_length=1000)
    reason: Reason

    @model_validator(mode="after")
    def unique_origins(self) -> ReconciliationCommand:
        if len({item.receipt_id for item in self.applications}) != len(
            self.applications
        ):
            raise ValueError("Duplicate receipt origin.")
        return self


class ProofView(BaseModel):
    id: UUID
    receipt_id: UUID
    content_type: str
    size: int
    sha256: str
    actor_id: UUID
    created_at: datetime


class ReceiptView(BaseModel):
    id: UUID
    revision: int
    amount: str
    method: Method
    business_date: date
    observation: str | None
    actor_id: UUID
    session_id: UUID
    created_at: datetime
    refunded: str
    net: str
    applied_deposit: str
    applied_balance: str
    pending: str
    proofs: list[ProofView]


class RefundView(BaseModel):
    id: UUID
    receipt_id: UUID
    amount: str
    method: Method
    business_date: date
    reason: str
    actor_id: UUID
    session_id: UUID
    created_at: datetime


class PaymentView(BaseModel):
    quotation_id: UUID
    quotation_version: int
    financial_version: int
    reconciled_quotation_version: int | None
    total: str
    estimated_deposit: str
    estimated_balance: str
    received: str
    refunded: str
    net_received: str
    applied_deposit: str
    applied_balance: str
    deposit_remaining: str
    balance_remaining: str
    remaining: str
    pending: str
    excess: str
    deposit_validated: bool
    fully_paid: bool
    requires_reconciliation: bool
    commercial_version_pending: bool
    receipts: list[ReceiptView]
    refunds: list[RefundView]


class PaymentHistoryItem(BaseModel):
    id: UUID
    financial_version: int
    quotation_version: int
    operation: str
    actor_id: UUID
    session_id: UUID
    reason: str | None
    before: dict[str, object]
    after: dict[str, object]
    created_at: datetime


class PaymentHistoryPage(BaseModel):
    items: list[PaymentHistoryItem]
    page: int
    page_size: int
    total: int
