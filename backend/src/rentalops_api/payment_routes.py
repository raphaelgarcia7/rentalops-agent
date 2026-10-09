"""Authenticated, Origin/CSRF-protected financial HTTP contracts."""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import ValidationError

from rentalops_api.auth_routes import CurrentIdentity, trusted_origin
from rentalops_api.config import DatabaseSettings
from rentalops_api.customer_routes import private_response
from rentalops_api.database import build_engine, build_session_factory
from rentalops_api.payment_contracts import (
    CorrectionCommand,
    PaymentCommand,
    PaymentHistoryPage,
    PaymentView,
    ReceiptCommand,
    ReconciliationCommand,
    RefundCommand,
)
from rentalops_api.payment_errors import PaymentError, invalid
from rentalops_api.payment_storage import MAX_PROOF_BYTES
from rentalops_api.payments import PaymentService

router = APIRouter(
    prefix="/quotations/{quotation_id}/payments",
    tags=["Payments"],
    dependencies=[Depends(private_response)],
)
mutation = [Depends(trusted_origin)]


def payment_service() -> Iterator[PaymentService]:
    engine = build_engine(DatabaseSettings.from_environment())
    try:
        yield PaymentService(build_session_factory(engine))
    finally:
        engine.dispose()


Service = Annotated[PaymentService, Depends(payment_service)]


@router.get("", response_model=PaymentView)
def detail(
    quotation_id: UUID, identity: CurrentIdentity, service: Service
) -> dict[str, object]:
    return service.get(quotation_id)


@router.get("/history", response_model=PaymentHistoryPage)
def history(
    quotation_id: UUID,
    identity: CurrentIdentity,
    service: Service,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    return service.history(quotation_id, page, page_size)


@router.post("/receipts", response_model=PaymentView, dependencies=mutation)
def receipt(
    quotation_id: UUID,
    payload: ReceiptCommand,
    identity: CurrentIdentity,
    service: Service,
) -> dict[str, object]:
    return service.write(quotation_id, "receipt", payload, identity)[0]


@router.post(
    "/receipts/{receipt_id}/corrections",
    response_model=PaymentView,
    dependencies=mutation,
)
def correct(
    quotation_id: UUID,
    receipt_id: UUID,
    payload: CorrectionCommand,
    identity: CurrentIdentity,
    service: Service,
) -> dict[str, object]:
    return service.write(quotation_id, "correction", payload, identity, receipt_id)[0]


@router.post("/reconciliations", response_model=PaymentView, dependencies=mutation)
def reconcile(
    quotation_id: UUID,
    payload: ReconciliationCommand,
    identity: CurrentIdentity,
    service: Service,
) -> dict[str, object]:
    return service.write(quotation_id, "reconciliation", payload, identity)[0]


@router.post("/refunds", response_model=PaymentView, dependencies=mutation)
def refund(
    quotation_id: UUID,
    payload: RefundCommand,
    identity: CurrentIdentity,
    service: Service,
) -> dict[str, object]:
    return service.write(quotation_id, "refund", payload, identity)[0]


@router.post(
    "/receipts/{receipt_id}/proofs", response_model=PaymentView, dependencies=mutation
)
async def upload(
    request: Request,
    quotation_id: UUID,
    receipt_id: UUID,
    identity: CurrentIdentity,
    service: Service,
    file: Annotated[UploadFile, File()],
    request_id: Annotated[UUID, Form()],
    expected_financial_version: Annotated[int, Form(ge=0)],
    expected_quotation_version: Annotated[int, Form(ge=1)],
) -> dict[str, object]:
    form = await request.form()
    allowed = {
        "file",
        "request_id",
        "expected_financial_version",
        "expected_quotation_version",
    }
    if set(form) != allowed or any(len(form.getlist(key)) != 1 for key in allowed):
        raise invalid("Campos inválidos no envio do comprovante.")
    try:
        if request.query_params:
            raise invalid("Envie os dados do comprovante no formulário.")
        command = PaymentCommand(
            request_id=request_id,
            expected_financial_version=expected_financial_version,
            expected_quotation_version=expected_quotation_version,
        )
    except ValidationError:
        raise invalid("Versões inválidas para anexar comprovante.") from None
    try:
        data = await file.read(MAX_PROOF_BYTES + 1)
        if len(data) > MAX_PROOF_BYTES:
            raise PaymentError(
                413, "proof_too_large", "Comprovante excede 10.000.000 bytes."
            )
        return service.write(
            quotation_id,
            "proof",
            command,
            identity,
            receipt_id,
            (data, file.content_type),
        )[0]
    finally:
        await file.close()


@router.get("/proofs/{proof_id}/download")
def download(
    quotation_id: UUID, proof_id: UUID, identity: CurrentIdentity, service: Service
) -> Response:
    data, content_type, filename = service.download(quotation_id, proof_id)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
