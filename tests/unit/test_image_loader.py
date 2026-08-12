from pathlib import Path

import cv2
import numpy as np
import pytest

import tooldrawer_studio.capture.image_loader as loader
from tooldrawer_studio.capture.image_loader import load_image
from tooldrawer_studio.domain.models import CaptureAsset


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


def test_normalized_png_bytes_encode_the_decoded_working_pixels():
    working_pixels = np.zeros((20, 40, 3), dtype=np.uint8)
    raw_pixels = np.zeros((40, 20, 3), dtype=np.uint8)
    ok, raw_encoded = cv2.imencode(".png", raw_pixels)
    assert ok
    asset = CaptureAsset(
        id="capture-normalized",
        filename="source.jpg",
        width_px=40,
        height_px=20,
        archive_path="images/capture-normalized.jpg",
    )
    loaded = loader.LoadedImage(
        asset=asset,
        pixels_bgr=working_pixels,
        original_bytes=raw_encoded.tobytes(),
    )

    display_bytes = loader.normalized_png_bytes(loaded)
    display = cv2.imdecode(np.frombuffer(display_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert display is not None
    assert display.shape[:2] == (20, 40)


def test_load_new_image_bytes_builds_asset_from_decoded_pixels():
    pixels = np.zeros((18, 31, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok

    loaded = loader.load_new_image_bytes(encoded.tobytes(), "phone.png", "capture-new")

    assert loaded.asset.id == "capture-new"
    assert loaded.asset.filename == "phone.png"
    assert loaded.asset.archive_path == "images/capture-new.png"
    assert (loaded.asset.width_px, loaded.asset.height_px) == (31, 18)


def test_load_new_image_bytes_reuses_invalid_image_validation():
    with pytest.raises(ValueError, match="Unsupported or invalid image"):
        loader.load_new_image_bytes(b"not-an-image", "bad.jpg", "capture-new")


def test_rotated_png_bytes_rotates_clockwise():
    working_pixels = np.zeros((12, 30, 3), dtype=np.uint8)
    working_pixels[:, :5] = (255, 255, 255)
    ok, encoded = cv2.imencode(".png", working_pixels)
    assert ok
    asset = CaptureAsset(
        id="capture-rotate",
        filename="source.png",
        width_px=30,
        height_px=12,
        archive_path="images/capture-rotate.png",
    )
    loaded = loader.LoadedImage(asset, working_pixels, encoded.tobytes())

    rotated = loader.rotated_png_bytes(loaded, 1)
    decoded = cv2.imdecode(np.frombuffer(rotated, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert decoded is not None
    assert decoded.shape[:2] == (30, 12)
    assert np.all(decoded[:5, :] == 255)
