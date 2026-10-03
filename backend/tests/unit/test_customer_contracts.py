"""Every example is synthetic; documents are generated, never customer fixtures."""

import pytest
from pydantic import ValidationError

from rentalops_api.customer_contracts import (
    Address,
    CustomerCreate,
    CustomerEdit,
    CustomerSearch,
    normalize_cpf,
)


def synthetic_cpf(seed: int = 123456789) -> str:
    digits = str(seed).zfill(9)
    for length in (9, 10):
        total = sum(int(digits[i]) * (length + 1 - i) for i in range(length))
        digits += str((total * 10 % 11) % 10)
    return digits


def test_minimal_progressive_normalization_and_blank_optionals():
    record = CustomerCreate(
        name="  Synthetic person  ",
        phone="(11) 91234-5678",
        cpf=" ",
        rg=" ",
        notes=" ",
        email=" ",
        address={"city": " "},
    )
    assert record.name == "Synthetic person"
    assert record.phone.startswith("+55")
    assert (
        record.cpf
        is record.rg
        is record.notes
        is record.email
        is record.address
        is None
    )
    cpf = synthetic_cpf()
    formatted = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    assert normalize_cpf(formatted) == cpf
    assert CustomerCreate(name="S", phone="+44 20 8366 1177").phone == "+442083661177"
    assert Address(postal_code="01000-000", state="sp").model_dump()["state"] == "SP"
    assert (
        CustomerCreate(
            name="S", phone="(11) 91234-5678", address={"city": "Synthetic city"}
        ).address.city
        == "Synthetic city"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", " "),
        ("name", "x" * 201),
        ("phone", 123),
        ("phone", "123"),
        ("phone", "phone +55 (11) 91234-5678"),
        ("phone", "(11) 91234-5678 ext 2"),
        ("cpf", "0" * 11),
        ("cpf", synthetic_cpf()[:-1] + "0"),
        ("cpf", "letters"),
        ("rg", "x" * 31),
        ("email", "bad-email"),
        ("notes", "x" * 4001),
        ("id", "arbitrary"),
        ("created_by", "arbitrary"),
        ("updated_by", "arbitrary"),
        ("version", 1),
        ("created_at", "arbitrary"),
        ("cnpj", "arbitrary"),
        ("acknowledged_shared_contact", True),
        ("address", {"postal_code": "123"}),
        ("address", {"state": "ZZ"}),
        ("address", {"street": "x" * 201}),
        ("address", {"number": "x" * 31}),
        ("address", {"complement": "x" * 201}),
        ("address", {"city": "x" * 101}),
        ("address", {"neighborhood": "x" * 101}),
        ("address", {"unknown": "x"}),
    ],
)
def test_invalid_customer_fields_are_rejected(field, value):
    with pytest.raises(ValidationError):
        CustomerCreate.model_validate(
            {"name": "Synthetic", "phone": "(11) 91234-5678", field: value}
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "S"},
        {"phone": "(11) 91234-5678"},
    ],
)
def test_required_initial_fields(payload):
    with pytest.raises(ValidationError):
        CustomerCreate.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_version": True},
        {"expected_version": "1"},
        {"expected_version": 0},
        {"expected_version": 1, "name": None},
        {"expected_version": 1, "phone": None},
        {"expected_version": 1, "actor_id": "arbitrary"},
    ],
)
def test_edits_reject_invalid_version_and_internal_fields(payload):
    with pytest.raises(ValidationError):
        CustomerEdit.model_validate(payload)


def test_partial_edit_and_search_limits_exact_normalized_filters():
    assert CustomerEdit(expected_version=1, notes=" ").model_dump(
        exclude_unset=True
    ) == {"expected_version": 1, "notes": None}
    assert (
        CustomerSearch(phone="(11) 91234-5678").phone
        == CustomerSearch(phone="+55 11 91234-5678").phone
    )
    assert CustomerSearch().page_size == 25
    for payload in (
        {"page": 0},
        {"page_size": 101},
        {"page": True},
        {"name": "x" * 201},
        {"cpf": "invalid"},
        {"phone": "123"},
    ):
        with pytest.raises(ValidationError):
            CustomerSearch.model_validate(payload)
