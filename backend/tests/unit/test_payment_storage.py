import hashlib
import io
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from rentalops_api.payment_errors import PaymentError
from rentalops_api.payment_storage import MAX_PROOF_BYTES, ProofStorage, validate_proof


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
