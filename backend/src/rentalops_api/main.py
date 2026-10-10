"""Application entry point for the RentalOps HTTP API."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from rentalops_api.auth import AuthError
from rentalops_api.auth_routes import CurrentIdentity, router
from rentalops_api.catalog_middleware import PhotoBodyLimit
from rentalops_api.catalog_routes import router as catalog_router
from rentalops_api.catalog_storage import CatalogError
from rentalops_api.config import DatabaseConfigurationError, DatabaseSettings
from rentalops_api.customer_contracts import Address, CustomerCreate, CustomerSearch
from rentalops_api.customer_routes import router as customer_router
from rentalops_api.customers import CustomerError
from rentalops_api.database import build_engine
from rentalops_api.operations_middleware import OperationalBoundary
from rentalops_api.payment_errors import PaymentError
from rentalops_api.payment_routes import router as payment_router
from rentalops_api.quotation_routes import router as quotation_router
from rentalops_api.quotations import QuotationError
from rentalops_api.rental_routes import router as rental_router
from rentalops_api.rentals import RentalError

app = FastAPI(
    title="RentalOps API",
    description="API for managing event-decoration rentals.",
    version="0.1.0",
)

app.include_router(router)
app.include_router(catalog_router)
app.include_router(customer_router)
app.include_router(quotation_router)
app.include_router(payment_router)
app.include_router(rental_router)
app.add_middleware(PhotoBodyLimit)
app.add_middleware(OperationalBoundary)


@app.exception_handler(RentalError)
async def rental_error(request: Request, error: RentalError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"detail": error.message, "code": error.code, **error.data},
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.exception_handler(QuotationError)
@app.exception_handler(PaymentError)
async def quotation_error(request: Request, error: QuotationError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"detail": error.message, "code": error.code},
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.exception_handler(CustomerError)
async def customer_error(request: Request, error: CustomerError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={
            "detail": error.message,
            "code": error.code,
            "existing_ids": [str(identifier) for identifier in error.existing_ids],
        },
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.exception_handler(CatalogError)
async def catalog_error(request: Request, error: CatalogError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"detail": error.message},
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.exception_handler(AuthError)
async def authentication_error(request: Request, error: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"detail": error.message},
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(RequestValidationError)
async def invalid_input(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    # Pydantic's default details include the rejected input, possibly a password.
    content: dict[str, object] = {"detail": "Entrada inválida."}
    if request.url.path.startswith("/customers"):
        allowed = (
            set(CustomerCreate.model_fields)
            | set(CustomerSearch.model_fields)
            | set(Address.model_fields)
            | {"expected_version", "identifier"}
        )
        content["fields"] = sorted(
            {
                str(part)
                for item in error.errors()
                for part in item["loc"]
                if part in allowed
            }
        ) or ["input"]
    if request.url.path.startswith("/quotations"):
        from rentalops_api.quotation_contracts import (
            QuotationDiscount,
            QuotationLineInput,
            QuotationSearch,
            QuotationWrite,
        )

        allowed = (
            set(QuotationWrite.model_fields)
            | set(QuotationSearch.model_fields)
            | set(QuotationLineInput.model_fields)
            | set(QuotationDiscount.model_fields)
            | {"identifier", "number"}
        )
        content["fields"] = sorted(
            {
                str(part)
                for item in error.errors()
                for part in item["loc"]
                if part in allowed
            }
        ) or ["input"]
    return JSONResponse(
        status_code=422,
        content=content,
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(SQLAlchemyError)
@app.exception_handler(ValueError)
async def unavailable(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Serviço indisponível."},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/internal/identity", tags=["Internal"])
def internal_identity(identity: CurrentIdentity) -> dict[str, str]:
    """Backend identity boundary for future commercial routes; no business writes."""
    return {"user_id": str(identity.user_id)}


@app.get("/health", tags=["Operations"])
async def health_check() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "ok", "service": "rentalops-api"}


@app.get("/ready", tags=["Operations"])
@app.get("/health/ready", tags=["Operations"], include_in_schema=False)
def readiness_check() -> JSONResponse:
    """Check database, schema and storage without revealing infrastructure."""
    engine = None
    try:
        engine = build_engine(DatabaseSettings.from_environment())
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            from rentalops_api.readiness import check_schema

            check_schema(connection)
        from rentalops_api.catalog_storage import PhotoStorage

        PhotoStorage.from_environment().checked_root()
    except DatabaseConfigurationError, SQLAlchemyError, ValueError, CatalogError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    finally:
        if engine is not None:
            engine.dispose()
    return JSONResponse(content={"status": "ready"})
