"""Private immutable photo bytes; no user paths and no broad cleanup."""

import hashlib
import io
import os
import re
import stat
import warnings
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from rentalops_api.config import environment_values
from rentalops_api.operations import OperationsError, private_path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
CONTENT_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


class CatalogError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


def normalize_image(data: bytes, content_type: str | None) -> tuple[bytes, str]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise CatalogError(413, "Foto excede o limite de 10 MiB.")
    if content_type not in CONTENT_TYPES.values():
        raise CatalogError(422, "Use uma imagem JPEG, PNG ou WebP válida.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                image_format = probe.format
                if (
                    image_format not in CONTENT_TYPES
                    or CONTENT_TYPES[image_format] != content_type
                ):
                    raise CatalogError(
                        422, "O conteúdo não corresponde ao tipo da foto."
                    )
                if probe.width * probe.height > MAX_IMAGE_PIXELS:
                    raise CatalogError(413, "Foto excede o limite de 20 megapixels.")
                probe.verify()
            with Image.open(io.BytesIO(data)) as decoded:
                decoded.load()
                # Fresh pixels remove EXIF, text, ICC and animation metadata.
                mode = "RGB" if image_format == "JPEG" else "RGBA"
                pixels = decoded.convert(mode)
                clean = Image.new(mode, pixels.size)
                clean.paste(pixels)
                output = io.BytesIO()
                clean.save(output, format=image_format)
                normalized = output.getvalue()
                if len(normalized) > MAX_UPLOAD_BYTES:
                    raise CatalogError(413, "Foto normalizada excede 10 MiB.")
                return normalized, image_format
    except Image.DecompressionBombError, Image.DecompressionBombWarning:
        raise CatalogError(413, "Foto excede o limite de 20 megapixels.") from None
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ):
        raise CatalogError(422, "Use uma imagem JPEG, PNG ou WebP válida.") from None


@dataclass(frozen=True)
class StoredPhoto:
    key: str
    image_format: str
    size: int
    sha256: str


class PhotoStorage:
    def __init__(self, root: Path | None) -> None:
        self.root = root

    @classmethod
    def from_environment(cls) -> PhotoStorage:
        value = environment_values().get("STORAGE_ROOT")
        return cls(Path(value) if value else None)

    def checked_root(self) -> Path:
        root = self.root
        try:
            if root is None or not root.is_absolute():
                raise OSError
            # Reject links/junctions at every ancestor, not just the final path.
            for ancestor in (root, *root.parents):
                if ancestor.is_symlink() or ancestor.is_junction():
                    raise OSError
                if (ancestor / ".git").exists():
                    raise OSError
            # Windows paths are case-insensitive. Reject casing variants on all
            # hosts so configuration cannot become public after deployment.
            parts = {part.casefold() for part in root.parts}
            if "public" in parts and "frontend" in parts:
                raise OSError
            if not root.is_dir() or root.resolve() != root:
                raise OSError
            private_path(root)
            # Metadata alone can look private while the runtime UID cannot use
            # the mount (for example mode0000 or a mismatched container owner).
            if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
                raise OSError
            return root
        except OSError, OperationsError:
            raise CatalogError(
                503,
                "Armazenamento de fotos indisponível. "
                "Verifique a configuração privada.",
            ) from None

    def checked_path(self, key: str) -> Path:
        root = self.checked_root()
        if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", key):
            raise CatalogError(503, "Foto indisponível.")
        path = root / key
        if path.is_symlink() or path.is_junction() or path.resolve().parent != root:
            raise CatalogError(503, "Foto indisponível.")
        return path

    def write(self, data: bytes, image_format: str) -> StoredPhoto:
        key = f"{uuid4().hex}.{EXTENSIONS[image_format]}"
        path = self.checked_path(key)
        created = False
        try:
            with path.open("xb") as target:
                os.chmod(path, 0o600)
                created = True
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            # Validate root again before returning an asset that DB may reference.
            self.checked_path(key)
        except OSError, CatalogError:
            if created:
                self.compensate(key)
            raise CatalogError(
                503, "Não foi possível armazenar a foto. Tente novamente."
            ) from None
        return StoredPhoto(
            key, image_format, len(data), hashlib.sha256(data).hexdigest()
        )

    def compensate(self, key: str) -> None:
        # Called only for this operation's exclusive newly-created filename.
        try:
            path = self.checked_path(key)
            if stat.S_ISREG(path.lstat().st_mode):
                path.unlink()
        except OSError, CatalogError:
            # Orphan bytes are safer than deleting any previous/historical asset.
            pass

    def read(self, key: str, size: int, digest: str) -> bytes:
        try:
            path = self.checked_path(key)
            if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size != size:
                raise OSError
            with path.open("rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise OSError
                data = source.read(MAX_UPLOAD_BYTES + 1)
            self.checked_path(key)
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise OSError
            return data
        except OSError, CatalogError:
            raise CatalogError(503, "Foto indisponível. Tente novamente.") from None
