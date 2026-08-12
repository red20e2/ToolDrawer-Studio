from pathlib import Path

import cv2
import numpy as np
import pytest

import tooldrawer_studio.capture.image_loader as loader
from tooldrawer_studio.capture.image_loader import load_image


def test_load_image_preserves_bytes_and_normalizes_bgr(simple_tools_image_path: Path):
    loaded = load_image(simple_tools_image_path, capture_id="capture-1")

    assert loaded.asset.id == "capture-1"
    assert loaded.asset.width_px == 300
    assert loaded.asset.height_px == 200
    assert loaded.asset.width_px == loaded.pixels_bgr.shape[1]
    assert loaded.asset.height_px == loaded.pixels_bgr.shape[0]
    assert loaded.pixels_bgr.shape[2] == 3
    assert len(loaded.original_bytes) > 0


def test_load_image_rejects_invalid_bytes(tmp_path: Path):
    invalid = tmp_path / "not-an-image.png"
    invalid.write_bytes(b"not an image")

    with pytest.raises(ValueError, match="Unsupported or invalid image"):
        load_image(invalid, capture_id="capture-2")


def test_load_image_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: b"x" * (loader.MAX_IMAGE_BYTES + 1),
    )

    with pytest.raises(ValueError, match="too large"):
        loader.load_image(Path("huge.jpg"), "capture-3")


def test_decode_rejects_excessive_pixel_count(monkeypatch, tmp_path: Path):
    pixels = np.zeros((20, 30, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    path = tmp_path / "image.png"
    path.write_bytes(encoded.tobytes())
    monkeypatch.setattr(loader, "MAX_IMAGE_PIXELS", 500)

    with pytest.raises(ValueError, match="too large"):
        loader.load_image(path, "capture-4")
