import hashlib
import io
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from rentalops_api.catalog_storage import (
    MAX_UPLOAD_BYTES,
    CatalogError,
    PhotoStorage,
    normalize_image,
)


def synthetic_image(image_format="PNG", size=(12, 10), exif=False):
    buffer = io.BytesIO()
    picture = Image.new("RGB", size, "#456f58")
    metadata = Image.Exif()
    if exif:
        metadata[270] = "Synthetic private metadata"
    picture.save(buffer, format=image_format, exif=metadata)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "image_format,content_type",
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_decoded_format_clean_exif_immutable_bytes(
    tmp_path, image_format, content_type
):
    data, verified = normalize_image(
        synthetic_image(image_format, exif=True), content_type
    )
    assert verified == image_format
    with Image.open(io.BytesIO(data)) as picture:
        assert not picture.getexif() and picture.size == (12, 10)
    storage = PhotoStorage(tmp_path)
    a = storage.write(data, verified)
    b = storage.write(data, verified)
    assert a.key != b.key and a.sha256 == b.sha256 == hashlib.sha256(data).hexdigest()
    assert storage.read(a.key, a.size, a.sha256) == data


@pytest.mark.parametrize(
    "data,mime",
    [
        (b"<svg></svg>", "image/png"),
        (b"<html></html>", "image/jpeg"),
        (b"not a photo", "image/webp"),
        (b"<svg/>", "image/svg+xml"),
        (synthetic_image(), "image/jpeg"),
        (synthetic_image(), None),
    ],
)
def test_disguised_bytes_and_mime_rejected(data, mime):
    with pytest.raises(CatalogError) as caught:
        normalize_image(data, mime)
    assert caught.value.status == 422


def test_byte_and_decoded_pixel_limits_before_storage(tmp_path):
    for data in (b"x" * (MAX_UPLOAD_BYTES + 1), synthetic_image(size=(5000, 4001))):
        with pytest.raises(CatalogError) as caught:
            normalize_image(data, "image/png")
        assert caught.value.status == 413
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "key",
    [
        "../outside.png",
        "..\\outside.png",
        "/root/photo.png",
        "a" * 32 + ".svg",
        "photo.png",
        "https://example.invalid/photo.png",
    ],
)
def test_storage_keys_traversal_and_client_urls_never_opened(tmp_path, key):
    with pytest.raises(CatalogError) as caught:
        PhotoStorage(tmp_path).read(key, 1, "x")
    assert caught.value.status == 503 and str(tmp_path) not in str(caught.value)


def test_root_missing_relative_git_and_public_fail_closed(tmp_path):
    paths = [None, Path("relative"), tmp_path / "missing"]
    (tmp_path / ".git").mkdir()
    paths.append(tmp_path)
    for root in paths:
        with pytest.raises(CatalogError) as caught:
            PhotoStorage(root).checked_root()
        assert caught.value.status == 503


def test_private_metadata_without_effective_access_fails_closed(tmp_path):
    tmp_path.chmod(0o700)
    storage = PhotoStorage(tmp_path)
    assert storage.checked_root() == tmp_path
    with patch("rentalops_api.catalog_storage.os.access", return_value=False) as access:
        with pytest.raises(CatalogError) as caught:
            storage.checked_root()
        access.assert_called_once_with(tmp_path, os.R_OK | os.W_OK | os.X_OK)
    assert caught.value.status == 503
    assert str(tmp_path) not in str(caught.value)
    assert storage.checked_root() == tmp_path


@pytest.mark.parametrize(
    "frontend,public",
    [
        ("frontend", "public"),
        ("Frontend", "Public"),
        ("FRONTEND", "PUBLIC"),
        ("frontend", "PUBLIC"),
        ("FRONTEND", "public"),
        ("FrOnTeNd", "PuBlIc"),
    ],
)
@pytest.mark.parametrize("nested", [False, True])
def test_public_frontend_root_and_ancestors_reject_case_variants(
    tmp_path, frontend, public, nested
):
    root = tmp_path / frontend / public
    if nested:
        root = root / "nested" / "photos"
    root.mkdir(parents=True)
    with pytest.raises(CatalogError) as caught:
        PhotoStorage(root).checked_root()
    assert caught.value.status == 503
    assert str(root) not in str(caught.value)
    assert list(root.iterdir()) == []


def test_actual_symlink_and_parent_symlink_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    original = outside / "original.png"
    original.write_bytes(b"synthetic historical asset")
    key = "a" * 32 + ".png"

    def link_directory(target, path):
        if os.name == "nt":
            # Junctions test real Windows reparse points without granting
            # administrator privileges or enabling developer mode.
            import _winapi

            _winapi.CreateJunction(str(target), str(path))
        else:
            os.symlink(target, path, target_is_directory=True)

    if os.name == "nt":
        link_directory(outside, private / key)
    else:
        os.symlink(original, private / key)
    storage = PhotoStorage(private)
    with pytest.raises(CatalogError):
        storage.read(
            key,
            len(original.read_bytes()),
            hashlib.sha256(original.read_bytes()).hexdigest(),
        )
    storage.compensate(key)
    assert original.read_bytes() == b"synthetic historical asset"
    assert (private / key).is_symlink() or (private / key).is_junction()
    link_directory(outside, tmp_path / "linked")
    with pytest.raises(CatalogError):
        PhotoStorage(tmp_path / "linked").checked_root()


def test_filesystem_failure_only_removes_new_partial_file(tmp_path):
    storage = PhotoStorage(tmp_path)
    previous = storage.write(b"historical", "PNG")
    with patch(
        "rentalops_api.catalog_storage.os.fsync",
        side_effect=OSError("synthetic failure"),
    ):
        with pytest.raises(CatalogError) as caught:
            storage.write(b"new", "PNG")
    assert caught.value.status == 503
    assert [item.name for item in tmp_path.iterdir()] == [previous.key]
    assert storage.read(previous.key, previous.size, previous.sha256) == b"historical"


def test_missing_corrupt_and_directory_asset_returns_generic_error(tmp_path):
    storage = PhotoStorage(tmp_path)
    key = "a" * 32 + ".png"
    for action in (lambda: None, lambda: (tmp_path / key).write_bytes(b"bad")):
        action()
        with pytest.raises(CatalogError) as caught:
            storage.read(key, 3, "x")
        assert caught.value.status == 503
    (tmp_path / key).unlink()
    (tmp_path / key).mkdir()
    with pytest.raises(CatalogError):
        storage.read(key, 3, "x")
