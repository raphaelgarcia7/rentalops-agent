import hashlib
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from rentalops_api import payment_storage
from rentalops_api.payment_errors import PaymentError
from rentalops_api.payment_storage import (
    MAX_PROOF_BYTES,
    ProofStorage,
    validate_proof,
    validating_pdf,
)


def pdf(pages=1, encrypted=False, javascript=False, embedded=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    if encrypted:
        writer.encrypt("synthetic")
    if javascript:
        writer.root_object[NameObject("/OpenAction")] = DictionaryObject(
            {
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): TextStringObject("app.alert('synthetic')"),
            }
        )
    if embedded:
        writer.add_attachment("synthetic.txt", b"synthetic attachment")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image(format="PNG", size=(10, 10)):
    output = io.BytesIO()
    Image.new("RGB", size, "#48765c").save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize(
    "data,mime",
    [(pdf(), "application/pdf"), (image(), "image/png"), (image("JPEG"), "image/jpeg")],
)
def test_valid_original_immutable_proof_bytes(tmp_path, data, mime):
    assert validate_proof(data, mime) == mime
    storage = ProofStorage(tmp_path)
    first, second = storage.write(data, mime), storage.write(data, mime)
    assert first.key != second.key
    assert first.sha256 == second.sha256 == hashlib.sha256(data).hexdigest()
    assert storage.read(first.key, first.size, first.sha256) == data


@pytest.mark.parametrize(
    "data,mime",
    [
        (b"PRIVATE_SYNTHETIC_SENTINEL", "application/pdf"),
        (image(), "image/jpeg"),
        (image(), "application/pdf"),
        (pdf(), "image/png"),
        (pdf(encrypted=True), "application/pdf"),
        (pdf(javascript=True), "application/pdf"),
        (pdf(embedded=True), "application/pdf"),
        (pdf(101), "application/pdf"),
        (pdf(), "text/html"),
        (b"", "image/png"),
    ],
)
def test_invalid_disguised_encrypted_active_embedded_and_page_limits(
    data, mime, caplog
):
    with pytest.raises(PaymentError) as error:
        validate_proof(data, mime)
    assert error.value.status == 422
    assert "PRIVATE_SYNTHETIC_SENTINEL" not in caplog.text


def test_exact_byte_boundary_and_pixel_boundary():
    source = pdf()
    padded = source + b" " * (MAX_PROOF_BYTES - len(source))
    assert validate_proof(padded, "application/pdf") == "application/pdf"
    for data, mime in [
        (padded + b" ", "application/pdf"),
        (image(size=(5000, 5001)), "image/png"),
    ]:
        with pytest.raises(PaymentError) as error:
            validate_proof(data, mime)
        assert error.value.status == 413
    assert validate_proof(image(size=(5000, 5000)), "image/png") == "image/png"
    assert validate_proof(pdf(100), "application/pdf") == "application/pdf"


def test_rejected_pdf_late_reader_logger_never_exposes_document_bytes(
    monkeypatch, caplog
):
    original = pdf()
    old_header = b"3 0 obj\n"
    new_header = b"PRIVATE_SYNTHETIC_SENTINEL  0 obj\n"
    assert old_header in original
    assert b"0000000162 00000 n" in original
    assert b"startxref\n256" in original
    delta = len(new_header) - len(old_header)
    crafted = original.replace(old_header, new_header, 1)
    crafted = crafted.replace(
        b"0000000162 00000 n", f"{162 + delta:010d} 00000 n".encode(), 1
    )
    crafted = crafted.replace(
        b"startxref\n256", f"startxref\n{256 + delta}".encode(), 1
    )
    # Reproduce a logger created after payment_storage was imported. Its direct
    # handler matters: a filter on the pypdf parent/root cannot protect it.
    monkeypatch.delitem(
        logging.Logger.manager.loggerDict, "pypdf._reader", raising=False
    )
    logger = logging.getLogger("pypdf._reader")
    capture = io.StringIO()
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    try:
        with pytest.raises(PaymentError) as error:
            validate_proof(crafted, "application/pdf")
        assert error.value.status == 422
        assert "PRIVATE_SYNTHETIC_SENTINEL" not in capture.getvalue()
        assert "PRIVATE_SYNTHETIC_SENTINEL" not in caplog.text
        logger.warning("outside-validation-visible")
        assert "outside-validation-visible" in capture.getvalue()
    finally:
        logger.removeHandler(handler)


def test_new_pdf_descendant_logger_is_private_only_in_validation_context(caplog):
    logger = logging.getLogger("pypdf.synthetic_late_validation_logger")
    token = validating_pdf.set(True)
    try:
        logger.warning("PRIVATE_SYNTHETIC_SENTINEL")
        logging.getLogger("rentalops.synthetic_other_logger").warning(
            "unrelated-diagnostic-visible"
        )
    finally:
        validating_pdf.reset(token)
    logger.warning("outside-validation-visible")
    assert "PRIVATE_SYNTHETIC_SENTINEL" not in caplog.text
    assert "unrelated-diagnostic-visible" in caplog.text
    assert "outside-validation-visible" in caplog.text


def test_private_pdf_logging_chains_existing_factory_and_isolates_threads(
    monkeypatch, caplog
):
    captured = []
    previous = payment_storage._previous_log_record_factory

    def configured_factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.custom_factory_marker = True
        captured.append(record)
        return record

    monkeypatch.setattr(
        payment_storage, "_previous_log_record_factory", configured_factory
    )
    logger = logging.getLogger("pypdf.synthetic_concurrent_logger")
    token = validating_pdf.set(True)
    try:
        try:
            raise ValueError("PRIVATE_SYNTHETIC_EXCEPTION")
        except ValueError:
            logger.warning(
                "PRIVATE_SYNTHETIC_SENTINEL %s",
                "private-argument",
                exc_info=True,
                stack_info=True,
            )
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(logger.warning, "concurrent-context-visible").result()
    finally:
        validating_pdf.reset(token)
    assert len(captured) == 2
    assert all(record.custom_factory_marker for record in captured)
    assert captured[0].msg == "Private PDF parser diagnostic omitted."
    assert captured[0].args == ()
    assert captured[0].exc_info is None
    assert captured[0].stack_info is None
    assert "PRIVATE_SYNTHETIC_SENTINEL" not in caplog.text
    assert "private-argument" not in caplog.text
    assert "concurrent-context-visible" in caplog.text


@pytest.mark.parametrize(
    "key",
    [
        "../escape.pdf",
        "..\\escape.pdf",
        "/root/file.pdf",
        "https://example.invalid/file.pdf",
        "proof-" + "a" * 32 + ".html",
    ],
)
def test_private_storage_refuses_paths(tmp_path, key):
    with pytest.raises(PaymentError) as error:
        ProofStorage(tmp_path).read(key, 1, "x")
    assert error.value.status == 503 and str(tmp_path) not in str(error.value)


def test_unavailable_private_root_and_digest_corruption(tmp_path):
    for root in (None, Path("relative"), tmp_path / "absent"):
        with pytest.raises(PaymentError):
            ProofStorage(root).write(pdf(), "application/pdf")
    storage = ProofStorage(tmp_path)
    proof = storage.write(pdf(), "application/pdf")
    with pytest.raises(PaymentError):
        storage.read(proof.key, proof.size, "0" * 64)
    with (
        patch.object(Path, "is_symlink", return_value=True),
        pytest.raises(PaymentError),
    ):
        storage.read(proof.key, proof.size, proof.sha256)


def test_failed_new_write_compensates_only_owned_bytes(tmp_path):
    storage = ProofStorage(tmp_path)
    old = storage.write(pdf(), "application/pdf")
    with (
        patch("rentalops_api.payment_storage.os.fsync", side_effect=OSError),
        pytest.raises(PaymentError),
    ):
        storage.write(pdf(), "application/pdf")
    assert [item.name for item in tmp_path.iterdir()] == [old.key]
