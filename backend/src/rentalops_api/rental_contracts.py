"""Strict confirmation commands and private operational DTOs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from rentalops_api.catalog_contracts import CatalogPayload
from rentalops_api.quotation_contracts import QuotationCapacityView


class ConfirmationPreview(CatalogPayload):
    expected_quotation_version: int = Field(strict=True, ge=1, le=2_147_483_647)
    expected_financial_version: int = Field(strict=True, ge=0, le=2_147_483_647)


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
    state: Literal["confirmed"]
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


class RentalHistoryItem(BaseModel):
    id: UUID
    version: int
    operation: str
    actor_id: UUID
    session_id: UUID
    created_at: datetime


class RentalHistoryPage(BaseModel):
    items: list[RentalHistoryItem]
    page: int
    page_size: int
    total: int
