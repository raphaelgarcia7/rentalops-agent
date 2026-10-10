"""Strict confirmation commands and private operational DTOs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from rentalops_api.catalog_contracts import CatalogPayload, PositiveQuantity
from rentalops_api.payment_contracts import Application
from rentalops_api.quotation_contracts import QuotationCapacityView, QuotationDraft


class ConfirmationPreview(CatalogPayload):
    expected_quotation_version: int = Field(strict=True, ge=1, le=2_147_483_647)
    expected_financial_version: int = Field(strict=True, ge=0, le=2_147_483_647)
    expected_rental_version: int | None = Field(
        default=None, strict=True, ge=1, le=2_147_483_647
    )


class ConfirmationCommand(ConfirmationPreview):
    request_id: UUID


class ConfirmationView(BaseModel):
    quotation_id: UUID
    quotation_version: int
    financial_version: int
    deposit_valid: bool
    pending: bool
    capacity: list[QuotationCapacityView]
    checked_at: datetime
    readonly: Literal[True] = True


class PendingView(BaseModel):
    id: UUID
    kind: Literal["inventory", "financial"]
    source: str
    source_version: int
    details: dict[str, object]
    actor_id: UUID
    created_at: datetime
    resolved: bool


class RentalSummary(BaseModel):
    id: UUID
    version: int
    state: Literal["confirmed", "cancelled", "review", "out", "completed"]
    inventory_pending: bool
    financial_pending: bool


class RentalView(RentalSummary):
    quotation_id: UUID
    customer_id: UUID
    quotation_version: int
    financial_version: int
    commercial_snapshot: dict[str, object]
    financial_snapshot: dict[str, object]
    allocations: list[dict[str, object]]
    pending: list[PendingView]
    actor_id: UUID
    session_id: UUID
    checked_at: datetime
    confirmation_deposit: str
    current_financial: dict[str, object]
    signature_commercial_version: int


class RentalHistoryItem(BaseModel):
    id: UUID
    version: int
    operation: str
    reason: str | None
    before: dict[str, object]
    after: dict[str, object]
    actor_id: UUID
    session_id: UUID
    created_at: datetime


class RentalHistoryPage(BaseModel):
    items: list[RentalHistoryItem]
    page: int
    page_size: int
    total: int


class RentalVersions(CatalogPayload):
    expected_quotation_version: int = Field(strict=True, ge=1, le=2_147_483_647)
    expected_financial_version: int = Field(strict=True, ge=0, le=2_147_483_647)
    expected_rental_version: int = Field(strict=True, ge=0, le=2_147_483_647)


class ChangePreview(RentalVersions):
    draft: QuotationDraft


class ChangeCommand(ChangePreview):
    request_id: UUID
    reason: str = Field(min_length=1, max_length=1000)
    catalog_versions: dict[str, PositiveQuantity] = Field(min_length=1)


class CancellationCommand(RentalVersions):
    request_id: UUID
    reason: str = Field(min_length=1, max_length=1000)
    approved: bool = Field(strict=True)


class ResumptionCommand(ChangeCommand):
    payments_reviewed: bool = Field(strict=True)
    applications: list[Application] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique_origins(self) -> ResumptionCommand:
        if len({row.receipt_id for row in self.applications}) != len(self.applications):
            raise ValueError("Duplicate receipt origin.")
        return self


class ChangePreviewView(BaseModel):
    before: dict[str, object]
    after: dict[str, object]
    financial: dict[str, object]
    expected_rental_version: int
    expected_quotation_version: int
    expected_financial_version: int
    requires_new_signature: bool
    readonly: Literal[True] = True
