from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from tooldrawer_studio.domain.models import CaptureAsset


MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
SUPPORTED_ARCHIVE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


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


def normalized_png_bytes(image: LoadedImage) -> bytes:
    """Encode the normalized working pixels for a calibration/display view."""
    ok, encoded = cv2.imencode(".png", image.pixels_bgr)
    if not ok:
        raise ValueError("Could not encode normalized image for display")
    return encoded.tobytes()


def rotated_png_bytes(image: LoadedImage, quarter_turns: int) -> bytes:
    """Encode working pixels after clockwise 90-degree pending rotations."""
    turns = quarter_turns % 4
    pixels = image.pixels_bgr
    if turns:
        pixels = np.rot90(pixels, k=-turns).copy()
    ok, encoded = cv2.imencode(".png", pixels)
    if not ok:
        raise ValueError("Could not encode rotated image")
    return encoded.tobytes()


def load_new_image_bytes(raw: bytes, filename: str, capture_id: str) -> LoadedImage:
    """Validate a newly captured/uploaded image and build project metadata."""
    safe_name = Path(filename).name or "capture.png"
    pixels = _decode_pixels(raw, safe_name)
    height, width = pixels.shape[:2]

    suffix = Path(safe_name).suffix.lower()
    stored_raw = raw
    if suffix not in SUPPORTED_ARCHIVE_SUFFIXES:
        suffix = ".png"
        safe_name = f"{Path(safe_name).stem or 'capture'}.png"
        ok, encoded = cv2.imencode(".png", pixels)
        if not ok:
            raise ValueError("Could not encode normalized image")
        stored_raw = encoded.tobytes()

    asset = CaptureAsset(
        id=capture_id,
        filename=safe_name,
        width_px=width,
        height_px=height,
        archive_path=f"images/{capture_id}{suffix}",
    )
    return LoadedImage(asset=asset, pixels_bgr=pixels, original_bytes=stored_raw)


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
