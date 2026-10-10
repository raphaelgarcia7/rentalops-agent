"""Loopback-only disposable PostgreSQL harness; never import in production.

Requires TEST_DATABASE_URL and uses the same fail-closed UUID schema fixture as
integration. Test control endpoints exist only in this wrapper, never main.app.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import uvicorn
from alembic import command
from fastapi import FastAPI, Request
from pydantic import BaseModel, ConfigDict

from rentalops_api.auth import AuthError, AuthService, AuthSettings
from rentalops_api.auth_routes import auth_service
from rentalops_api.catalog import CatalogService
from rentalops_api.catalog_routes import catalog_service
from rentalops_api.catalog_storage import PhotoStorage
from rentalops_api.customer_routes import customer_service
from rentalops_api.customers import CustomerService
from rentalops_api.database import build_session_factory
from rentalops_api.main import app as production_app
from rentalops_api.payment_routes import payment_service
from rentalops_api.payment_storage import ProofStorage
from rentalops_api.payments import PaymentService
from rentalops_api.quotation_routes import quotation_service
from rentalops_api.quotations import QuotationService
from rentalops_api.rental_routes import rental_service
from rentalops_api.rentals import RentalService

from .conftest import isolated_engine, migration_config


@asynccontextmanager
async def lifespan(app):
    namespace = isolated_engine.__wrapped__()
    engine = next(namespace)
    storage = TemporaryDirectory(prefix="rentalops-catalog-browser-")
    try:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
        service = AuthService(
            build_session_factory(engine),
            AuthSettings(
                "http://127.0.0.1:4173", False, "synthetic-browser-test-key" * 3
            ),
        )
        app.state.service = service
        app.state.targets = set()
        app.state.namespace = namespace
        app.state.storage = storage
        production_app.dependency_overrides[auth_service] = lambda: service
        catalog = CatalogService(
            build_session_factory(engine), PhotoStorage(Path(storage.name))
        )
        production_app.dependency_overrides[catalog_service] = lambda: catalog
        customers = CustomerService(build_session_factory(engine))
        production_app.dependency_overrides[customer_service] = lambda: customers
        quotations = QuotationService(build_session_factory(engine))
        production_app.dependency_overrides[quotation_service] = lambda: quotations
        payments = PaymentService(
            build_session_factory(engine), ProofStorage(Path(storage.name))
        )
        production_app.dependency_overrides[payment_service] = lambda: payments
        rentals = RentalService(build_session_factory(engine))
        production_app.dependency_overrides[rental_service] = lambda: rentals
        yield
    finally:
        production_app.dependency_overrides.clear()
        namespace.close()
        storage.cleanup()


app = FastAPI(lifespan=lifespan)


@app.get("/__test/health")
def health():
    return {"status": "ready"}


@app.post("/__test/cleanup")
def cleanup(request: Request):
    production_app.dependency_overrides.clear()
    request.app.state.namespace.close()
    request.app.state.storage.cleanup()
    return {"status": "cleaned"}


@app.post("/__test/setup")
def setup(request: Request):
    email = f"browser-{uuid4().hex}@example.invalid"
    service = request.app.state.service
    service.create_user(email)
    request.app.state.targets.add(email)
    token = service.issue_link(email, "access")
    return {"email": email, "token": token}


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    operation: str


@app.post("/__test/control")
def control(payload: Control, request: Request):
    if payload.email not in request.app.state.targets:
        raise AuthError(400, "Synthetic test target required.")
    service = request.app.state.service
    if payload.operation == "reset":
        return {"token": service.issue_link(payload.email, "reset")}
    if payload.operation == "deactivate":
        service.deactivate(payload.email)
        return {"status": "deactivated"}
    raise AuthError(400, "Synthetic test operation required.")


app.mount("/", production_app)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        access_log=False,
        proxy_headers=False,
        log_level="warning",
    )
