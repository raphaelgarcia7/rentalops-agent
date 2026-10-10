"""Private, versioned confirmation and operational reads."""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from rentalops_api.auth_routes import CurrentIdentity, trusted_origin
from rentalops_api.config import DatabaseSettings
from rentalops_api.customer_routes import private_response
from rentalops_api.database import build_engine, build_session_factory
from rentalops_api.quotation_routes import body_only
from rentalops_api.rental_changes import RentalChangeService
from rentalops_api.rental_contracts import (
    CancellationCommand,
    ChangeCommand,
    ChangePreview,
    ChangePreviewView,
    ConfirmationCommand,
    ConfirmationPreview,
    ConfirmationView,
    RentalHistoryPage,
    RentalVersions,
    RentalView,
    ResumptionCommand,
)

router = APIRouter(tags=["Rentals"], dependencies=[Depends(private_response)])


def rental_service() -> Iterator[RentalChangeService]:
    engine = build_engine(DatabaseSettings.from_environment())
    try:
        yield RentalChangeService(build_session_factory(engine))
    finally:
        engine.dispose()


Service = Annotated[RentalChangeService, Depends(rental_service)]
mutation = [Depends(trusted_origin), Depends(body_only)]


@router.post(
    "/quotations/{identifier}/confirmation-preview",
    response_model=ConfirmationView,
    dependencies=mutation,
)
def preview(
    identifier: UUID,
    payload: ConfirmationPreview,
    identity: CurrentIdentity,
    service: Service,
) -> dict[str, object]:
    return service.preview(identifier, payload)


@router.post(
    "/quotations/{identifier}/confirm",
    response_model=RentalView,
    status_code=201,
    dependencies=mutation,
)
def confirm(
    identifier: UUID,
    payload: ConfirmationCommand,
    identity: CurrentIdentity,
    service: Service,
    response: Response,
) -> dict[str, object]:
    result, replay = service.confirm(identifier, payload, identity)
    response.status_code = 200 if replay else 201
    response.headers["Location"] = f"/rentals/{result['id']}"
    return result


@router.get("/rentals/by-quotation/{identifier}", response_model=RentalView)
def by_quotation(
    identifier: UUID, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.get(identifier, by_quotation=True)


@router.get("/rentals/{identifier}", response_model=RentalView)
def detail(
    identifier: UUID, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.get(identifier)


@router.get("/rentals/{identifier}/history", response_model=RentalHistoryPage)
def history(
    identifier: UUID,
    identity: CurrentIdentity,
    service: Service,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    return service.history(identifier, page, page_size)


@router.post(
    "/rentals/{identifier}/change-preview",
    response_model=ChangePreviewView,
    dependencies=mutation,
)
def change_preview(
    identifier: UUID,
    payload: ChangePreview,
    identity: CurrentIdentity,
    service: Service,
) -> dict[str, object]:
    return service.change_preview(identifier, payload)


@router.post(
    "/quotations/{identifier}/resumption-preview",
    response_model=ChangePreviewView,
    dependencies=mutation,
)
def resumption_preview(
    identifier: UUID,
    payload: ChangePreview,
    identity: CurrentIdentity,
    service: Service,
) -> dict[str, object]:
    return service.change_preview(identifier, payload, by_quotation=True)


@router.post(
    "/rentals/{identifier}/changes",
    response_model=RentalView,
    status_code=201,
    dependencies=mutation,
)
def change(
    identifier: UUID,
    payload: ChangeCommand,
    identity: CurrentIdentity,
    service: Service,
    response: Response,
) -> dict[str, object]:
    result, replay = service.command(identifier, "change", payload, identity)
    response.status_code = 200 if replay else 201
    return result


@router.post(
    "/rentals/{identifier}/cancellations",
    response_model=RentalView,
    status_code=201,
    dependencies=mutation,
)
def cancel(
    identifier: UUID,
    payload: CancellationCommand,
    identity: CurrentIdentity,
    service: Service,
    response: Response,
) -> dict[str, object]:
    result, replay = service.command(identifier, "cancel", payload, identity)
    response.status_code = 200 if replay else 201
    return result


@router.post(
    "/rentals/{identifier}/resumptions",
    response_model=RentalView,
    status_code=201,
    dependencies=mutation,
)
def resume(
    identifier: UUID,
    payload: ResumptionCommand,
    identity: CurrentIdentity,
    service: Service,
    response: Response,
) -> dict[str, object]:
    result, replay = service.command(identifier, "resume", payload, identity)
    response.status_code = 200 if replay else 201
    return result


@router.post(
    "/quotations/{identifier}/resumptions",
    response_model=RentalView,
    status_code=201,
    dependencies=mutation,
)
def resume_quotation(
    identifier: UUID,
    payload: ResumptionCommand,
    identity: CurrentIdentity,
    service: Service,
    response: Response,
) -> dict[str, object]:
    result, replay = service.command(
        identifier, "resume", payload, identity, by_quotation=True
    )
    response.status_code = 200 if replay else 201
    return result


@router.post("/rentals/{identifier}/copy-preview", dependencies=mutation)
def copy_preview(
    identifier: UUID,
    payload: RentalVersions,
    identity: CurrentIdentity,
    service: Service,
) -> dict[str, object]:
    return service.copy_preview(identifier, payload)
