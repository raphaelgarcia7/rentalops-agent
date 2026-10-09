"""Bound multipart input before the parser can spool an unbounded upload."""

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rentalops_api.catalog_storage import MAX_UPLOAD_BYTES
from rentalops_api.payment_storage import MAX_PROOF_BYTES


class PhotoBodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].endswith(("/photos", "/proofs"))
        ):
            await self.app(scope, receive, send)
            return
        # Small bounded allowance for the multipart envelope and version field.
        is_proof = scope["path"].endswith("/proofs")
        limit = (MAX_PROOF_BYTES if is_proof else MAX_UPLOAD_BYTES) + 64 * 1024
        headers = dict(scope["headers"])
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = limit + 1
        if declared > limit:
            response = JSONResponse(
                status_code=413,
                content={"detail": "Arquivo excede o limite de upload."},
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        consumed = 0

        messages: list[Message] = []
        while True:
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": "Arquivo excede o limite de upload."},
                        headers={"Cache-Control": "no-store"},
                    )
                    await response(scope, receive, send)
                    return
            messages.append(message)
            if not message.get("more_body", False):
                break
        pending = iter(messages)

        async def bounded_receive() -> Message:
            message = next(pending, None)
            return message if message is not None else await receive()

        await self.app(scope, bounded_receive, send)
