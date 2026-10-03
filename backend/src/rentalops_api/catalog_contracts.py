"""Catalog input contracts shared by application services and HTTP adapters."""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

MAX_QUANTITY = 2_147_483_647


def exact_money(value: object) -> Decimal:
    # JSON clients must send decimal strings, never already-rounded float money.
    if not isinstance(value, str | Decimal):
        raise ValueError("Use a decimal string.")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid money.") from None
    if (
        not amount.is_finite()
        or amount < 0
        or amount > Decimal("9999999999.99")
        or not isinstance(amount.as_tuple().exponent, int)
        or int(amount.as_tuple().exponent) < -2
    ):
        raise ValueError("Money outside Numeric(12,2).")
    return amount.quantize(Decimal("0.01"))


Money = Annotated[Decimal, BeforeValidator(exact_money)]
Quantity = Annotated[int, Field(strict=True, ge=0, le=MAX_QUANTITY)]
PositiveQuantity = Annotated[int, Field(strict=True, ge=1, le=MAX_QUANTITY)]


class CatalogPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProductFields(CatalogPayload):
    name: str = Field(min_length=1, max_length=200)
    price: Money
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=100)
    dimensions: str | None = Field(default=None, max_length=200)
    replacement_value: Money | None = None
    observation: str | None = Field(default=None, max_length=4000)


class ProductCreate(ProductFields):
    initial_quantity: Quantity


class ProductEdit(ProductFields):
    expected_version: PositiveQuantity


class VersionCommand(CatalogPayload):
    expected_version: PositiveQuantity


class ReasonCommand(VersionCommand):
    reason: str = Field(min_length=1, max_length=4000)


class StockAdjustment(ReasonCommand):
    operation: Literal["entry", "withdrawal", "correction"]
    quantity: Quantity

    @field_validator("quantity")
    @classmethod
    def quantity_for_operation(cls, value: int, info: ValidationInfo) -> int:
        if info.data.get("operation") != "correction" and value == 0:
            raise ValueError("Movement quantity must be positive.")
        return value


class MaintenanceCommand(ReasonCommand):
    quantity: PositiveQuantity


class KitItemInput(CatalogPayload):
    product_id: UUID
    quantity: PositiveQuantity


class KitFields(CatalogPayload):
    name: str = Field(min_length=1, max_length=200)
    price: Money
    items: list[KitItemInput] = Field(min_length=1, max_length=1000)


class KitCreate(KitFields):
    pass


class KitEdit(KitFields):
    expected_version: PositiveQuantity


class PhotoEdit(VersionCommand):
    is_principal: bool = Field(strict=True)
    order: Quantity


def aggregate_items(items: list[KitItemInput]) -> dict[UUID, int]:
    totals: dict[UUID, int] = {}
    for item in items:
        totals[item.product_id] = totals.get(item.product_id, 0) + item.quantity
        if totals[item.product_id] > MAX_QUANTITY:
            raise ValueError("Component quantity outside PostgreSQL integer.")
    return dict(sorted(totals.items()))


class HistoryView(BaseModel):
    id: UUID
    actor_id: UUID
    session_id: UUID
    operation: str
    reason: str
    snapshot: dict[str, object]
    created_at: str


class MovementView(BaseModel):
    id: UUID
    actor_id: UUID
    session_id: UUID
    operation: str
    reason: str
    quantity: int
    total_after: int
    maintenance_after: int
    created_at: str


class MaintenanceView(BaseModel):
    id: UUID
    quantity: int
    released_quantity: int
    reason: str


class PhotoView(BaseModel):
    id: UUID
    format: str
    size: int
    sha256: str
    order: int
    is_principal: bool


class RecordView(BaseModel):
    id: UUID
    name: str
    price: str
    is_active: bool
    version: int
    created_by: UUID
    updated_by: UUID
    created_at: str
    updated_at: str


class ProductView(RecordView):
    description: str | None
    category: str | None
    color: str | None
    dimensions: str | None
    replacement_value: str | None
    observation: str | None
    total_quantity: int
    maintenance_quantity: int
    apt_quantity: int


class ProductDetail(ProductView):
    history: list[HistoryView]
    movements: list[MovementView]
    maintenance: list[MaintenanceView]
    photos: list[PhotoView]


class KitItemView(BaseModel):
    product_id: UUID
    name: str
    quantity: int
    is_active: bool


class KitView(RecordView):
    items: list[KitItemView]
    needs_review: bool


class KitDetail(KitView):
    history: list[HistoryView]


class ProductPage(BaseModel):
    items: list[ProductView]
    total: int
    page: int
    page_size: int


class KitPage(BaseModel):
    items: list[KitView]
    total: int
    page: int
    page_size: int
