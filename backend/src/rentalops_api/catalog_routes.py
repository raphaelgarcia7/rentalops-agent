"""Authenticated catalog HTTP boundary; session identity supplies audit actor."""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from rentalops_api.auth_routes import CurrentIdentity, trusted_origin
from rentalops_api.catalog import CatalogService
from rentalops_api.catalog_contracts import (
    KitCreate,
    KitDetail,
    KitEdit,
    KitPage,
    MaintenanceCommand,
    PhotoEdit,
    ProductCreate,
    ProductDetail,
    ProductEdit,
    ProductPage,
    ReasonCommand,
    StockAdjustment,
)
from rentalops_api.catalog_storage import (
    CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
    CatalogError,
    PhotoStorage,
)
from rentalops_api.config import DatabaseSettings
from rentalops_api.database import build_engine, build_session_factory


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


router = APIRouter(tags=["Catalog"], dependencies=[Depends(private_response)])
mutation = [Depends(trusted_origin)]


def catalog_service() -> Iterator[CatalogService]:
    engine = build_engine(DatabaseSettings.from_environment())
    try:
        yield CatalogService(
            build_session_factory(engine), PhotoStorage.from_environment()
        )
    finally:
        engine.dispose()


Service = Annotated[CatalogService, Depends(catalog_service)]
Search = Annotated[str, Query(max_length=200)]
Page = Annotated[int, Query(ge=1, le=2_147_483_647)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/products", response_model=ProductPage)
def products(
    service: Service,
    identity: CurrentIdentity,
    search: Search = "",
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, object]:
    return service.list_records("products", search.strip(), page, page_size)


@router.post(
    "/products", status_code=201, response_model=ProductDetail, dependencies=mutation
)
def create_product(
    payload: ProductCreate, service: Service, identity: CurrentIdentity
) -> dict[str, object]:
    return service.create_product(payload, identity)


@router.get("/products/{identifier}", response_model=ProductDetail)
def product(
    identifier: UUID, service: Service, identity: CurrentIdentity
) -> dict[str, object]:
    return service.get("products", identifier)


@router.patch(
    "/products/{identifier}", response_model=ProductDetail, dependencies=mutation
)
def edit_product(
    identifier: UUID, payload: ProductEdit, service: Service, identity: CurrentIdentity
) -> dict[str, object]:
    return service.edit_product(identifier, payload, identity)


@router.post(
    "/products/{identifier}/inactivate",
    response_model=ProductDetail,
    dependencies=mutation,
)
def inactivate_product(
    identifier: UUID,
    payload: ReasonCommand,
    service: Service,
    identity: CurrentIdentity,
) -> dict[str, object]:
    return service.inactivate("products", identifier, payload, identity)


@router.post(
    "/products/{identifier}/stock-adjustments",
    response_model=ProductDetail,
    dependencies=mutation,
)
def adjust_stock(
    identifier: UUID,
    payload: StockAdjustment,
    service: Service,
    identity: CurrentIdentity,
) -> dict[str, object]:
    return service.adjust_stock(identifier, payload, identity)


@router.post(
    "/products/{identifier}/maintenance",
    response_model=ProductDetail,
    dependencies=mutation,
)
def maintenance(
    identifier: UUID,
    payload: MaintenanceCommand,
    service: Service,
    identity: CurrentIdentity,
) -> dict[str, object]:
    return service.maintenance(identifier, payload, identity)


@router.post(
    "/products/{identifier}/maintenance/{entry_id}/release",
    response_model=ProductDetail,
    dependencies=mutation,
)
def release(
    identifier: UUID,
    entry_id: UUID,
    payload: MaintenanceCommand,
    service: Service,
    identity: CurrentIdentity,
) -> dict[str, object]:
    return service.release(identifier, entry_id, payload, identity)


@router.get("/kits", response_model=KitPage)
def kits(
    service: Service,
    identity: CurrentIdentity,
    search: Search = "",
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, object]:
    return service.list_records("kits", search.strip(), page, page_size)


@router.post("/kits", status_code=201, response_model=KitDetail, dependencies=mutation)
def create_kit(
    payload: KitCreate, service: Service, identity: CurrentIdentity
) -> dict[str, object]:
    return service.save_kit(payload, identity)


@router.get("/kits/{identifier}", response_model=KitDetail)
def kit(
    identifier: UUID, service: Service, identity: CurrentIdentity
) -> dict[str, object]:
    return service.get("kits", identifier)


@router.patch("/kits/{identifier}", response_model=KitDetail, dependencies=mutation)
def edit_kit(
    identifier: UUID, payload: KitEdit, service: Service, identity: CurrentIdentity
) -> dict[str, object]:
    return service.save_kit(payload, identity, identifier)


@router.post(
    "/kits/{identifier}/inactivate", response_model=KitDetail, dependencies=mutation
)
def inactivate_kit(
    identifier: UUID,
    payload: ReasonCommand,
    service: Service,
    identity: CurrentIdentity,
) -> dict[str, object]:
    return service.inactivate("kits", identifier, payload, identity)


@router.post(
    "/products/{identifier}/photos",
    status_code=201,
    response_model=ProductDetail,
    dependencies=mutation,
)
async def upload(
    identifier: UUID,
    file: UploadFile,
    service: Service,
    identity: CurrentIdentity,
    request: Request,
    expected_version: Annotated[int, Form(ge=1, le=2_147_483_647)],
) -> dict[str, object]:
    try:
        form = await request.form()
        if set(form) != {"file", "expected_version"} or len(form.multi_items()) != 2:
            raise CatalogError(422, "Campos de upload inválidos.")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise CatalogError(413, "Foto excede o limite de 10 MiB.")
        return await run_in_threadpool(
            service.upload_photo,
            identifier,
            expected_version,
            data,
            file.content_type,
            identity,
        )
    finally:
        await file.close()


@router.patch(
    "/products/{identifier}/photos/{photo_id}",
    response_model=ProductDetail,
    dependencies=mutation,
)
def edit_photo(
    identifier: UUID,
    photo_id: UUID,
    payload: PhotoEdit,
    service: Service,
    identity: CurrentIdentity,
) -> dict[str, object]:
    return service.edit_photo(identifier, photo_id, payload, identity)


@router.post(
    "/products/{identifier}/photos/{photo_id}/detach",
    response_model=ProductDetail,
    dependencies=mutation,
)
def detach_photo(
    identifier: UUID,
    photo_id: UUID,
    payload: ReasonCommand,
    service: Service,
    identity: CurrentIdentity,
) -> dict[str, object]:
    return service.edit_photo(identifier, photo_id, payload, identity)


@router.get("/photos/{photo_id}")
def read_photo(photo_id: UUID, service: Service, identity: CurrentIdentity) -> Response:
    data, image_format = service.read_photo(photo_id)
    return Response(
        data,
        media_type=CONTENT_TYPES[image_format],
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
