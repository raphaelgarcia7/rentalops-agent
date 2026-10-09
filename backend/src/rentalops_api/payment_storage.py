"""Validate bounded proof bytes and retain their original immutable content."""

import hashlib
import io
import logging
import os
import re
import stat
import warnings
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

from rentalops_api.catalog_storage import CatalogError, PhotoStorage
from rentalops_api.payment_errors import PaymentError, invalid

MAX_PROOF_BYTES = 10_000_000
MAX_PROOF_PIXELS = 25_000_000
TYPES = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}
FORBIDDEN_PDF = {
    "/JavaScript",
    "/JS",
    "/Launch",
    "/EmbeddedFiles",
    "/EmbeddedFile",
    "/RichMedia",
    "/XFA",
    "/GoToR",
    "/SubmitForm",
    "/ImportData",
    "/Filespec",
    "/RichMediaExecute",
    "/Rendition",
}

validating_pdf: ContextVar[bool] = ContextVar("validating_private_pdf", default=False)


class PrivatePdfFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not validating_pdf.get()


# pypdf creates its module loggers at import time. Filter document diagnostics
# only within this validation context; concurrent non-PDF logs remain intact.
for logger_name in tuple(logging.Logger.manager.loggerDict):
    if logger_name == "pypdf" or logger_name.startswith("pypdf."):
        logging.getLogger(logger_name).addFilter(PrivatePdfFilter())


def validate_pdf(data: bytes) -> None:
    # pypdf diagnostics can contain document-controlled text. Silence its logger
    # for this reader without changing process-wide logging configuration.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise invalid("PDF criptografado não é aceito.")
        if not 1 <= len(reader.pages) <= 100:
            raise invalid("Use PDF com 1 a 100 páginas.")
        pending: list[object] = [reader.root_object]
        visited: set[tuple[int, int]] = set()
        count = 0
        while pending:
            value = pending.pop()
            count += 1
            if count > 100_000:
                raise invalid("PDF excede o limite estrutural.")
            if isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in visited:
                    continue
                visited.add(key)
                pending.append(value.get_object())
            elif isinstance(value, DictionaryObject):
                if (
                    any(str(key) in FORBIDDEN_PDF for key in value)
                    or str(value.get("/S")) in FORBIDDEN_PDF
                    or str(value.get("/Type")) in FORBIDDEN_PDF
                ):
                    raise invalid(
                        "PDF com conteúdo executável ou arquivo incorporado "
                        "não é aceito."
                    )
                pending.extend(value.values())
            elif isinstance(value, ArrayObject):
                pending.extend(value)


def validate_proof(data: bytes, content_type: str | None) -> str:
    if len(data) > MAX_PROOF_BYTES:
        raise PaymentError(
            413, "proof_too_large", "Comprovante excede 10.000.000 bytes."
        )
    if not data or content_type not in TYPES:
        raise invalid("Use um comprovante PDF, JPEG ou PNG válido.")
    try:
        if content_type == "application/pdf":
            if not data.startswith(b"%PDF-"):
                raise ValueError
            token = validating_pdf.set(True)
            try:
                validate_pdf(data)
            finally:
                validating_pdf.reset(token)
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if (
                        image.format
                        != {"image/jpeg": "JPEG", "image/png": "PNG"}[content_type]
                    ):
                        raise ValueError
                    if image.width * image.height > MAX_PROOF_PIXELS:
                        raise PaymentError(
                            413, "proof_too_large", "Imagem excede 25 megapixels."
                        )
                    image.verify()
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
    except PaymentError:
        raise
    except Exception:
        raise invalid(
            "Comprovante ilegível ou incompatível com o tipo informado."
        ) from None
    return content_type


@dataclass(frozen=True)
class StoredProof:
    key: str
    content_type: str
    size: int
    sha256: str


class ProofStorage:
    def __init__(self, root: Path | None) -> None:
        self.root = root

    @classmethod
    def from_environment(cls) -> ProofStorage:
        return cls(PhotoStorage.from_environment().root)

    def checked_path(self, key: str) -> Path:
        try:
            root = PhotoStorage(self.root).checked_root()
            if not re.fullmatch(r"proof-[0-9a-f]{32}\.(pdf|jpg|png)", key):
                raise OSError
            path = root / key
            if path.is_symlink() or path.is_junction() or path.resolve().parent != root:
                raise OSError
            return path
        except OSError, CatalogError:
            raise PaymentError(
                503,
                "storage_unavailable",
                "Armazenamento privado de comprovantes indisponível.",
            ) from None

    def write(self, data: bytes, content_type: str) -> StoredProof:
        key = f"proof-{uuid4().hex}.{TYPES[content_type]}"
        path = self.checked_path(key)
        created = False
        try:
            with path.open("xb") as target:
                created = True
                os.chmod(path, 0o600)
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            self.checked_path(key)
            return StoredProof(
                key, content_type, len(data), hashlib.sha256(data).hexdigest()
            )
        except OSError, PaymentError:
            if created:
                self.compensate(key)
            raise PaymentError(
                503,
                "storage_unavailable",
                "Não foi possível guardar o comprovante. O recebimento pode ser "
                "registrado sem anexo.",
            ) from None

    def compensate(self, key: str) -> None:
        try:
            path = self.checked_path(key)
            if stat.S_ISREG(path.lstat().st_mode):
                path.unlink()
        except OSError, PaymentError:
            pass  # Retain an orphan rather than risk historical bytes.

    def read(self, key: str, size: int, digest: str) -> bytes:
        try:
            path = self.checked_path(key)
            if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size != size:
                raise OSError
            with path.open("rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise OSError
                data = source.read(MAX_PROOF_BYTES + 1)
            self.checked_path(key)
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise OSError
            return data
        except OSError, PaymentError:
            raise PaymentError(
                503, "storage_unavailable", "Comprovante indisponível. Tente novamente."
            ) from None
