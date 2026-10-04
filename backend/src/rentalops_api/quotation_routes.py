"""Private authenticated quotation routes with existing Origin/CSRF protection."""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from rentalops_api.auth_routes import CurrentIdentity, trusted_origin
from rentalops_api.config import DatabaseSettings
from rentalops_api.customer_routes import private_response
from rentalops_api.database import build_engine, build_session_factory
from rentalops_api.quotation_contracts import (
    QuotationDraft,
    QuotationPageView,
    QuotationPreviewView,
    QuotationSearch,
    QuotationView,
    QuotationWrite,
)
from rentalops_api.quotations import QuotationError, QuotationService


def body_only(request: Request) -> None:
    if request.query_params:
        raise QuotationError(
            422, "invalid_query", "Envie os filtros no corpo da busca."
        )


router = APIRouter(
    prefix="/quotations",
    tags=["Quotations"],
    dependencies=[Depends(private_response), Depends(body_only)],
)
mutation = [Depends(trusted_origin)]


def quotation_service() -> Iterator[QuotationService]:
    engine = build_engine(DatabaseSettings.from_environment())
    try:
        yield QuotationService(build_session_factory(engine))
    finally:
        engine.dispose()


Service = Annotated[QuotationService, Depends(quotation_service)]


@router.post("/preview", response_model=QuotationPreviewView, dependencies=mutation)
def preview(
    payload: QuotationDraft, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.preview(payload)


@router.post("/search", response_model=QuotationPageView, dependencies=mutation)
def search(
    payload: QuotationSearch, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.search(payload)


@router.post("", response_model=QuotationView, status_code=201, dependencies=mutation)
def create(
    payload: QuotationWrite,
    identity: CurrentIdentity,
    service: Service,
    response: Response,
) -> dict[str, object]:
    result, replay = service.write(payload, identity)
    response.status_code = 200 if replay else 201
    response.headers["Location"] = f"/quotations/{result['id']}"
    return result


@router.get("/{identifier}", response_model=QuotationView)
def detail(
    identifier: UUID, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.get(identifier)


@router.get("/{identifier}/versions", response_model=list[QuotationView])
def versions(
    identifier: UUID, identity: CurrentIdentity, service: Service
) -> list[dict[str, object]]:
    return service.versions(identifier)


@router.get("/{identifier}/versions/{number}", response_model=QuotationView)
def version(
    identifier: UUID, number: int, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.get(identifier, number)


@router.post(
    "/{identifier}/versions",
    response_model=QuotationView,
    status_code=201,
    dependencies=mutation,
)
def revise(
    identifier: UUID,
    payload: QuotationWrite,
    identity: CurrentIdentity,
    service: Service,
    response: Response,
) -> dict[str, object]:
    result, replay = service.write(payload, identity, identifier)
    response.status_code = 200 if replay else 201
    return result
