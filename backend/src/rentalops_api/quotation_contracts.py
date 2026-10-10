"""Exact commercial quotation inputs and pure, reusable calculations."""

import re
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    field_serializer,
    model_validator,
)

from rentalops_api.catalog_contracts import (
    MAX_QUANTITY,
    CatalogPayload,
    KitItemInput,
    Money,
    PositiveQuantity,
    aggregate_items,
)

MAX_MONEY = Decimal("9999999999.99")
CENT = Decimal("0.01")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def iso_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Use an ISO business date.")
    return date.fromisoformat(value)


def local_time(value: object) -> time | None:
    if value is None:
        return value
    if isinstance(value, time):
        if value.tzinfo is not None or value.second or value.microsecond:
            raise ValueError("Use local HH:mm.")
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError("Use local HH:mm.")
    return time.fromisoformat(value)


BusinessDate = Annotated[date, BeforeValidator(iso_date)]
LocalTime = Annotated[time | None, BeforeValidator(local_time)]
Reason = Annotated[str, Field(min_length=1, max_length=4000)]


class QuotationLineInput(CatalogPayload):
    kind: Literal["product", "kit"]
    source_id: UUID
    quantity: PositiveQuantity
    # Retaining a saved line is explicit and scoped to the revision being edited.
    retained_line_id: UUID | None = None
    unit_price: Money | None = None
    items: list[KitItemInput] | None = Field(
        default=None, min_length=1, max_length=1000
    )
    negotiation_reason: Reason | None = None

    @model_validator(mode="after")
    def valid_composition(self) -> QuotationLineInput:
        if self.kind == "product" and self.items is not None:
            raise ValueError("Products cannot contain components.")
        if self.items is not None:
            aggregate_items(self.items)
        return self


class QuotationDiscount(CatalogPayload):
    kind: Literal["amount", "percent"]
    value: Money
    reason: Reason | None = None

    @model_validator(mode="after")
    def valid_discount(self) -> QuotationDiscount:
        if self.kind == "percent" and self.value > 100:
            raise ValueError("Percentage outside 0..100.")
        if self.value > 0 and not self.reason:
            raise ValueError("Positive discount requires a reason.")
        return self


class QuotationDraft(CatalogPayload):
    customer_id: UUID
    pickup_date: BusinessDate
    event_date: BusinessDate
    return_date: BusinessDate
    valid_until: BusinessDate
    pickup_time: LocalTime = None
    event_time: LocalTime = None
    return_time: LocalTime = None
    lines: list[QuotationLineInput] = Field(min_length=1, max_length=1000)
    discount: QuotationDiscount | None = None
    quotation_id: UUID | None = None
    expected_version: PositiveQuantity | None = None

    @field_serializer("pickup_time", "event_time", "return_time")
    def serialize_local_time(self, value: time | None) -> str | None:
        return value.strftime("%H:%M") if value is not None else None

    @model_validator(mode="after")
    def valid_dates(self) -> QuotationDraft:
        if self.return_date == date.max:
            raise ValueError("Planning next day exceeds the supported date range.")
        if not self.pickup_date <= self.event_date <= self.return_date:
            raise ValueError("Pickup/event/return dates are not ordered.")
        if self.valid_until > self.pickup_date:
            raise ValueError("Validity must end by pickup.")
        if (
            self.pickup_date == self.return_date
            and self.pickup_time is not None
            and self.return_time is not None
            and self.pickup_time > self.return_time
        ):
            raise ValueError("Same-day pickup must precede return.")
        if (self.quotation_id is None) != (self.expected_version is None):
            raise ValueError("Revision identity/version must be paired.")
        return self


class QuotationWrite(QuotationDraft):
    request_id: UUID
    # The preview supplies current versions for every source and actual component.
    catalog_versions: dict[str, PositiveQuantity]
    reason: Reason | None = None


class QuotationSearch(CatalogPayload):
    customer_id: UUID | None = None
    quotation_id: UUID | None = None
    state: Literal["current", "expired"] | None = None
    valid_until: BusinessDate | None = None
    pickup_date: BusinessDate | None = None
    event_date: BusinessDate | None = None
    return_date: BusinessDate | None = None
    page: Annotated[int, Field(strict=True, ge=1, le=MAX_QUANTITY)] = 1
    page_size: Annotated[int, Field(strict=True, ge=1, le=100)] = 25


class QuotationComponentView(BaseModel):
    product_id: UUID
    quantity: int
    name: str
    source_version: int


class QuotationLineView(BaseModel):
    kind: Literal["product", "kit"]
    source_id: UUID
    quantity: int
    unit_price: str
    name: str
    source_version: int
    items: list[QuotationComponentView]
    negotiation_reason: str | None


class QuotationSavedLineView(QuotationLineView):
    id: UUID


class QuotationCapacityView(BaseModel):
    product_id: UUID
    name: str
    demand: int
    apt: int
    shortage: int
    committed: int
    available: int
    conflicts: list[dict[str, object]]


class QuotationOfferView(BaseModel):
    customer_id: UUID
    pickup_date: date
    event_date: date
    return_date: date
    valid_until: date
    pickup_time: str | None
    event_time: str | None
    return_time: str | None
    discount: QuotationDiscount | None
    catalog_versions: dict[str, int]
    subtotal: str
    discount_amount: str
    total: str
    estimated_deposit: str
    estimated_balance: str
    planning_available_from: date
    state: Literal["current", "expired"]
    expired: bool
    requires_revision: bool
    capacity: list[QuotationCapacityView]
    capacity_mode: Literal["simultaneous_allocations"]
    capacity_checked_at: str
    stock_pending: bool


class QuotationPreviewView(QuotationOfferView):
    lines: list[QuotationLineView]


class QuotationView(QuotationOfferView):
    lines: list[QuotationSavedLineView]
    id: UUID
    version: int
    current_version: int
    reason: str | None
    actor_id: UUID
    session_id: UUID
    created_at: str
    revised_at: str
    rental: dict[str, object] | None = None


class QuotationPageView(BaseModel):
    items: list[QuotationView]
    total: int
    page: int
    page_size: int


def commercial_totals(
    lines: list[tuple[int, Decimal]], discount: QuotationDiscount | None
) -> dict[str, str]:
    subtotal = sum((quantity * price for quantity, price in lines), Decimal(0))
    if subtotal > MAX_MONEY:
        raise ValueError("Quotation subtotal overflow.")
    deduction = Decimal(0)
    if discount:
        deduction = discount.value
        if discount.kind == "percent":
            deduction = (subtotal * discount.value / 100).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
    total = subtotal - deduction
    if total < CENT or deduction > subtotal:
        raise ValueError("Quotation total must be positive.")
    deposit = (total / 2).quantize(CENT, rounding=ROUND_CEILING)
    return {
        key: format(value, ".2f")
        for key, value in {
            "subtotal": subtotal,
            "discount_amount": deduction,
            "total": total,
            "estimated_deposit": deposit,
            "estimated_balance": total - deposit,
        }.items()
    }


def validity_state(valid_until: date, now: datetime | None = None) -> dict[str, object]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("Clock must be timezone-aware.")
    expired = current.astimezone(SAO_PAULO).date() > valid_until
    return {
        "state": "expired" if expired else "current",
        "expired": expired,
        "requires_revision": expired,
    }


def next_planning_day(return_date: date) -> date:
    """Daily planning includes return day; it creates no stock commitment."""
    return return_date + timedelta(days=1)
