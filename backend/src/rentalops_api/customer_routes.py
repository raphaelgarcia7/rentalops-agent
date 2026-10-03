"""Authenticated customer boundary; search filters belong exclusively in bodies."""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from rentalops_api.auth_routes import CurrentIdentity, trusted_origin
from rentalops_api.config import DatabaseSettings
from rentalops_api.customer_contracts import (
    CustomerCreate,
    CustomerDetail,
    CustomerEdit,
    CustomerPage,
    CustomerSearch,
)
from rentalops_api.customers import CustomerError, CustomerService
from rentalops_api.database import build_engine, build_session_factory


def body_filters_only(request: Request) -> None:
    if request.query_params:
        raise CustomerError(422, "invalid_query", "Envie os filtros no corpo da busca.")


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


router = APIRouter(
    prefix="/customers",
    tags=["Customers"],
    dependencies=[Depends(private_response), Depends(body_filters_only)],
)
mutation = [Depends(trusted_origin)]


def customer_service() -> Iterator[CustomerService]:
    engine = build_engine(DatabaseSettings.from_environment())
    try:
        yield CustomerService(build_session_factory(engine))
    finally:
        engine.dispose()


Service = Annotated[CustomerService, Depends(customer_service)]


@router.post("", response_model=CustomerDetail, status_code=201, dependencies=mutation)
def create(
    payload: CustomerCreate,
    identity: CurrentIdentity,
    service: Service,
    response: Response,
) -> dict[str, object]:
    result = service.create(payload, identity)
    response.headers["Location"] = f"/customers/{result['id']}"
    return result


@router.post("/search", response_model=CustomerPage, dependencies=mutation)
def search(
    payload: CustomerSearch, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.search(payload)


@router.get("/{identifier}", response_model=CustomerDetail)
def detail(
    identifier: UUID, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.get(identifier)


@router.patch("/{identifier}", response_model=CustomerDetail, dependencies=mutation)
def edit(
    identifier: UUID, payload: CustomerEdit, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.edit(identifier, payload, identity)
