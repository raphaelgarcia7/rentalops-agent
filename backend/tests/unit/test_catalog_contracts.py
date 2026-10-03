from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from rentalops_api.catalog_contracts import (
    KitCreate,
    KitItemInput,
    MaintenanceCommand,
    ProductCreate,
    ProductEdit,
    StockAdjustment,
    aggregate_items,
)


def test_minimal_exact_zero_and_progressive_optional_fields():
    payload = ProductCreate(name="  Mesa branca ", price="100.01", initial_quantity=0)
    assert payload.name == "Mesa branca" and payload.price == Decimal("100.01")
    assert payload.observation is None and payload.replacement_value is None
    full = ProductCreate(
        name="Mesa preta",
        price="0",
        initial_quantity=3,
        observation="  Conferir tampo ",
        replacement_value="9999999999.99",
    )
    assert full.observation == "Conferir tampo"
    assert full.replacement_value == Decimal("9999999999.99")


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", " "),
        ("name", "a" * 201),
        ("price", -1),
        ("price", "-0.01"),
        ("price", "0.001"),
        ("price", "10000000000"),
        ("price", 1.01),
        ("price", "NaN"),
        ("price", "Infinity"),
        ("initial_quantity", -1),
        ("initial_quantity", 2_147_483_648),
        ("initial_quantity", 1.0),
        ("initial_quantity", True),
        ("initial_quantity", "1"),
        ("description", "a" * 4001),
        ("observation", "a" * 4001),
        ("category", "a" * 101),
        ("color", "a" * 101),
        ("dimensions", "a" * 201),
        ("replacement_value", "-0.01"),
        ("replacement_value", "0.001"),
        ("actor_id", str(uuid4())),
        ("id", str(uuid4())),
        ("total_quantity", 10),
        ("created_at", "2026-01-01"),
        ("maintenance_quantity", 1),
    ],
)
def test_product_boundary_invalid_and_internal_fields(field, value):
    fields = {"name": "Synthetic", "price": "1.01", "initial_quantity": 0}
    fields[field] = value
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(fields)


def test_edit_cannot_silently_change_quantity():
    with pytest.raises(ValidationError):
        ProductEdit.model_validate(
            {
                "name": "Synthetic",
                "price": "1",
                "expected_version": 1,
                "initial_quantity": 4,
            }
        )


@pytest.mark.parametrize(
    "operation,quantity",
    [("entry", 0), ("withdrawal", 0), ("withdrawal", -1), ("unknown", 1)],
)
def test_typed_stock_commands(operation, quantity):
    with pytest.raises(ValidationError):
        StockAdjustment(
            expected_version=1,
            operation=operation,
            quantity=quantity,
            reason="Inventory check",
        )


def test_stock_reason_version_and_maintenance_required():
    assert (
        StockAdjustment(
            expected_version=1, operation="correction", quantity=0, reason="Count"
        ).quantity
        == 0
    )
    for fields in ({"reason": " "}, {"expected_version": 0}, {"quantity": 0}):
        with pytest.raises(ValidationError):
            MaintenanceCommand.model_validate(
                {"expected_version": 1, "quantity": 1, "reason": "Repair", **fields}
            )


def test_kit_aggregation_has_stable_order_and_detects_overflow():
    a, b = uuid4(), uuid4()
    rows = [
        KitItemInput(product_id=b, quantity=1),
        KitItemInput(product_id=a, quantity=2),
        KitItemInput(product_id=b, quantity=3),
    ]
    result = aggregate_items(rows)
    assert result[a] == 2 and result[b] == 4 and list(result) == sorted([a, b])
    with pytest.raises(ValueError):
        aggregate_items(
            [
                KitItemInput(product_id=a, quantity=2_147_483_647),
                KitItemInput(product_id=a, quantity=1),
            ]
        )


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"product_id": str(uuid4()), "quantity": 0}],
        [{"kit_id": str(uuid4()), "quantity": 1}],
        [{"product_id": str(uuid4()), "quantity": True}],
    ],
)
def test_kit_only_accepts_product_references_and_valid_quantities(items):
    with pytest.raises(ValidationError):
        KitCreate.model_validate({"name": "Kit", "price": "30.01", "items": items})
