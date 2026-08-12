from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from tooldrawer_studio.domain.models import CaptureAsset


MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000


@dataclass(slots=True)
class LoadedImage:
    asset: CaptureAsset
    pixels_bgr: np.ndarray
    original_bytes: bytes


def _validate_raw_size(raw: bytes) -> None:
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Image file is too large; maximum size is 50 MB")


def _validate_pixel_size(pixels: np.ndarray) -> None:
    height, width = pixels.shape[:2]
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError("Decoded image is too large; maximum size is 40 megapixels")


def _decode_pixels(raw: bytes, description: str) -> np.ndarray:
    _validate_raw_size(raw)
    encoded = np.frombuffer(raw, dtype=np.uint8)
    pixels = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if pixels is None:
        raise ValueError(f"Unsupported or invalid image: {description}")
    _validate_pixel_size(pixels)
    return pixels


def load_image(path: Path, capture_id: str) -> LoadedImage:
    raw = path.read_bytes()
    pixels = _decode_pixels(raw, str(path))

    height, width = pixels.shape[:2]
    asset = CaptureAsset(
        id=capture_id,
        filename=path.name,
        width_px=width,
        height_px=height,
        archive_path=f"images/{capture_id}{path.suffix.lower()}",
    )
    return LoadedImage(asset=asset, pixels_bgr=pixels, original_bytes=raw)


def load_image_bytes(asset: CaptureAsset, raw: bytes) -> LoadedImage:
    """Decode image bytes already stored in an editable project archive."""
    pixels = _decode_pixels(raw, f"stored capture {asset.id}")
    height, width = pixels.shape[:2]
    if width != asset.width_px or height != asset.height_px:
        raise ValueError(
            f"Stored image dimensions do not match project metadata for capture: {asset.id}"
        )
    return LoadedImage(asset=asset, pixels_bgr=pixels, original_bytes=raw)
