from pathlib import Path

import pytest

from tooldrawer_studio.capture.image_loader import load_image


def test_load_image_preserves_bytes_and_normalizes_bgr():
    loaded = load_image(Path("tests/fixtures/simple_tools.png"), capture_id="capture-1")

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
