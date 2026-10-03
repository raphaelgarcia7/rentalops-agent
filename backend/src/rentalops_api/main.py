"""Application entry point for the RentalOps HTTP API."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from rentalops_api.config import DatabaseConfigurationError, DatabaseSettings
from rentalops_api.database import build_engine

app = FastAPI(
    title="RentalOps API",
    description="API for managing event-decoration rentals.",
    version="0.1.0",
)


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
