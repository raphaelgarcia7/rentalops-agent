"""HTTP contracts; services remain independent from browser-provided identity."""

from collections.abc import Iterator
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from rentalops_api.auth import (
    COOKIE_NAME,
    AuthError,
    AuthService,
    AuthSettings,
    Identity,
    normalize_email,
)
from rentalops_api.config import DatabaseSettings
from rentalops_api.database import build_engine, build_session_factory

router = APIRouter(prefix="/auth", tags=["Authentication"])


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LoginPayload(StrictPayload):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str) -> str:
        return normalize_email(value)


class PasswordPayload(StrictPayload):
    token: str = Field(min_length=1, max_length=256, repr=False)
    password: str = Field(min_length=12, max_length=128, repr=False)


class EmptyPayload(StrictPayload):
    pass


def auth_service() -> Iterator[AuthService]:
    settings = AuthSettings.from_environment()
    engine = build_engine(DatabaseSettings.from_environment())
    try:
        yield AuthService(build_session_factory(engine), settings)
    finally:
        engine.dispose()


Service = Annotated[AuthService, Depends(auth_service)]


def trusted_origin(request: Request, service: Service) -> None:
    if request.headers.get("origin") != service.settings.origin:
        raise AuthError(
            403, "Origem não autorizada. Reabra o sistema pelo endereço oficial."
        )


def current_identity(request: Request, service: Service) -> Identity:
    return service.identity(request.cookies.get(COOKIE_NAME))


CurrentIdentity = Annotated[Identity, Depends(current_identity)]


@router.post("/password/login", dependencies=[Depends(trusted_origin)])
def login(
    payload: LoginPayload, request: Request, response: Response, service: Service
) -> dict[str, object]:
    # Direct peer address only. Forwarded headers are never trusted by this module.
    origin = request.client.host if request.client else "unknown"
    token, identity = service.login(payload.email, payload.password, origin)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=service.settings.secure_cookie,
        samesite="lax",
        max_age=12 * 60 * 60,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return asdict(identity)


@router.get("/session")
def session(identity: CurrentIdentity, response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    return asdict(identity)


@router.post("/logout", status_code=204, dependencies=[Depends(trusted_origin)])
def logout(payload: EmptyPayload, request: Request, service: Service) -> Response:
    service.logout(request.cookies.get(COOKIE_NAME))
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        secure=service.settings.secure_cookie,
        samesite="lax",
    )
    return response


@router.post("/password/set", status_code=204, dependencies=[Depends(trusted_origin)])
def set_password(payload: PasswordPayload, service: Service) -> Response:
    service.set_password(payload.token, payload.password)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        secure=service.settings.secure_cookie,
        samesite="lax",
    )
    return response


@router.post("/activity", dependencies=[Depends(trusted_origin)])
def activity(
    payload: EmptyPayload, request: Request, response: Response, service: Service
) -> dict[str, object]:
    identity = service.identity(request.cookies.get(COOKIE_NAME), activity=True)
    response.headers["Cache-Control"] = "no-store"
    return asdict(identity)
