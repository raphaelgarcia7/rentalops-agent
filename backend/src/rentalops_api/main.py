"""Application entry point for the RentalOps HTTP API."""

from fastapi import FastAPI

app = FastAPI(
    title="RentalOps API",
    description="API for managing event-decoration rentals.",
    version="0.1.0",
)


@app.get("/health", tags=["Operations"])
async def health_check() -> dict[str, str]:
    """Report that the API process is responding."""
    return {"status": "ok", "service": "rentalops-api"}
