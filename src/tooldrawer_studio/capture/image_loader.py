from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from tooldrawer_studio.domain.models import CaptureAsset


@dataclass(slots=True)
class LoadedImage:
    asset: CaptureAsset
    pixels_bgr: np.ndarray
    original_bytes: bytes


def load_image(path: Path, capture_id: str) -> LoadedImage:
    raw = path.read_bytes()
    encoded = np.frombuffer(raw, dtype=np.uint8)
    pixels = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if pixels is None:
        raise ValueError(f"Unsupported or invalid image: {path}")

    height, width = pixels.shape[:2]
    asset = CaptureAsset(
        id=capture_id,
        filename=path.name,
        width_px=width,
        height_px=height,
        archive_path=f"images/{capture_id}{path.suffix.lower()}",
    )
    return LoadedImage(asset=asset, pixels_bgr=pixels, original_bytes=raw)
