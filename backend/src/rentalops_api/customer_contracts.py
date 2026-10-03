"""Validated customer contracts shared by services and HTTP, without PII errors."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

import phonenumbers
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


def optional_text(value: object) -> object:
    return value.strip() or None if isinstance(value, str) else value


def normalize_phone(value: str) -> str:
    if len(value) > 50 or not re.fullmatch(r"[+\d\s().-]+", value):
        raise ValueError("Invalid phone.")
    try:
        parsed = phonenumbers.parse(value, "BR")
    except phonenumbers.NumberParseException:
        raise ValueError("Invalid phone.") from None
    if not phonenumbers.is_valid_number(parsed) or parsed.extension:
        raise ValueError("Invalid phone.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_cpf(value: str) -> str:
    if not re.fullmatch(r"[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}", value):
        raise ValueError("Invalid CPF.")
    digits = re.sub(r"\D", "", value)
    if len(set(digits)) == 1:
        raise ValueError("Invalid CPF.")
    for length in (9, 10):
        total = sum(int(digits[i]) * (length + 1 - i) for i in range(length))
        check = (total * 10 % 11) % 10
        if check != int(digits[length]):
            raise ValueError("Invalid CPF.")
    return digits


OptionalText = Annotated[str | None, BeforeValidator(optional_text)]
Version = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]


class CustomerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Address(CustomerPayload):
    postal_code: OptionalText = Field(default=None, max_length=9)
    street: OptionalText = Field(default=None, max_length=200)
    number: OptionalText = Field(default=None, max_length=30)
    complement: OptionalText = Field(default=None, max_length=200)
    neighborhood: OptionalText = Field(default=None, max_length=100)
    city: OptionalText = Field(default=None, max_length=100)
    state: OptionalText = Field(default=None, max_length=2)

    @field_validator("postal_code")
    @classmethod
    def postal_format(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[0-9]{5}-?[0-9]{3}", value):
            raise ValueError("Invalid postal code.")
        return value.replace("-", "") if value else None

    @field_validator("state")
    @classmethod
    def state_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if normalized not in {
            "AC",
            "AL",
            "AP",
            "AM",
            "BA",
            "CE",
            "DF",
            "ES",
            "GO",
            "MA",
            "MT",
            "MS",
            "MG",
            "PA",
            "PB",
            "PR",
            "PE",
            "PI",
            "RJ",
            "RN",
            "RS",
            "RO",
            "RR",
            "SC",
            "SP",
            "SE",
            "TO",
        }:
            raise ValueError("Invalid state.")
        return normalized


class CustomerFields(CustomerPayload):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=50)
    email: Annotated[EmailStr | None, BeforeValidator(optional_text)] = Field(
        default=None, max_length=320
    )
    notes: OptionalText = Field(default=None, max_length=4000)
    cpf: OptionalText = None
    rg: OptionalText = Field(default=None, max_length=30)
    address: Address | None = None

    _phone = field_validator("phone")(normalize_phone)

    @field_validator("cpf")
    @classmethod
    def valid_cpf(cls, value: str | None) -> str | None:
        return normalize_cpf(value) if value is not None else None

    @field_validator("address")
    @classmethod
    def empty_address(cls, value: Address | None) -> Address | None:
        return value if value and any(value.model_dump().values()) else None


class CustomerCreate(CustomerFields):
    acknowledged_shared_contact: list[UUID] = Field(default_factory=list)


class CustomerEdit(CustomerPayload):
    expected_version: Version
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, min_length=1, max_length=50)
    email: Annotated[EmailStr | None, BeforeValidator(optional_text)] = Field(
        default=None, max_length=320
    )
    notes: OptionalText = Field(default=None, max_length=4000)
    cpf: OptionalText = None
    rg: OptionalText = Field(default=None, max_length=30)
    address: Address | None = None
    acknowledged_shared_contact: list[UUID] = Field(default_factory=list)

    @field_validator("name", "phone")
    @classmethod
    def required_if_supplied(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Required field.")
        return value

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else value

    @field_validator("cpf")
    @classmethod
    def valid_cpf(cls, value: str | None) -> str | None:
        return normalize_cpf(value) if value is not None else None


class CustomerSearch(CustomerPayload):
    name: str = Field(default="", max_length=200)
    phone: OptionalText = None
    cpf: OptionalText = None
    page: Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)] = 1
    page_size: Annotated[int, Field(strict=True, ge=1, le=100)] = 25

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value is not None else None

    @field_validator("cpf")
    @classmethod
    def valid_cpf(cls, value: str | None) -> str | None:
        return normalize_cpf(value) if value is not None else None


class CustomerSummary(BaseModel):
    id: UUID
    name: str
    phone: str
    version: int


class CustomerView(CustomerSummary):
    email: str | None
    notes: str | None
    cpf: str | None
    rg: str | None
    address: Address | None
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime


class CustomerAuditView(BaseModel):
    id: UUID
    actor_id: UUID
    session_id: UUID
    created_at: datetime
    version: int
    changed_fields: list[str]


class CustomerDetail(CustomerView):
    history: list[CustomerAuditView]


class CustomerPage(BaseModel):
    items: list[CustomerSummary]
    page: int
    page_size: int
    total: int
