"""Allowlisted JSON telemetry; never log request content or exception text."""

import json
import logging
from time import monotonic
from uuid import uuid4

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rentalops_api.operations import OperationsError, active_operation

logger = logging.getLogger("rentalops.operations")


class OperationalBoundary:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = monotonic()
        request_id = str(uuid4())
        status = 500
        response_started = False

        async def response_send(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            if scope["method"] in {"GET", "HEAD", "OPTIONS"}:
                await self.app(scope, receive, response_send)
            else:
                with active_operation():
                    await self.app(scope, receive, response_send)
        except OperationsError:
            await JSONResponse(
                {"detail": "Serviço em manutenção. Tente novamente."},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, response_send)
        except Exception:
            if not response_started:
                await JSONResponse(
                    {"detail": "Serviço indisponível."},
                    status_code=503,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, response_send)
            else:
                status = 503
                # A partial response cannot be rewritten or claimed successful.
                raise OperationsError("Response interrupted.") from None
        finally:
            route = scope.get("route")
            operation = getattr(route, "name", "unknown")
            logger.info(
                json.dumps(
                    {
                        "request_id": request_id,
                        "operation": operation,
                        "duration_ms": round((monotonic() - started) * 1000, 2),
                        "code": status,
                        "error_category": "dependency"
                        if status == 503
                        else "request"
                        if status >= 400
                        else None,
                    }
                )
            )
