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
from rentalops_api.database import build_engine

app = FastAPI(
    title="RentalOps API",
    description="API for managing event-decoration rentals.",
    version="0.1.0",
)

app.include_router(router)
app.include_router(catalog_router)
app.add_middleware(PhotoBodyLimit)


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
    return JSONResponse(
        status_code=422,
        content={"detail": "Entrada inválida."},
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


@app.get("/health/ready", tags=["Operations"])
def readiness_check() -> JSONResponse:
    """Check connectivity only; never disclose underlying database failures."""
    engine = None
    try:
        engine = build_engine(DatabaseSettings.from_environment())
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except DatabaseConfigurationError, SQLAlchemyError, ValueError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    finally:
        if engine is not None:
            engine.dispose()
    return JSONResponse(content={"status": "ready"})
