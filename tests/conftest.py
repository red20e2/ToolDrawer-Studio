from pathlib import Path

import cv2
import numpy as np
import pytest


@pytest.fixture
def simple_tools_image_path(tmp_path: Path) -> Path:
    """Create the deterministic two-tool image used by capture/tracing tests."""
    image = np.full((200, 300, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (30, 40), (120, 130), (0, 0, 0), thickness=-1)
    cv2.rectangle(image, (190, 60), (260, 140), (0, 0, 0), thickness=-1)

    ok, encoded = cv2.imencode(".png", image)
    assert ok

    path = tmp_path / "simple_tools.png"
    path.write_bytes(encoded.tobytes())
    return path


def _write_png(tmp_path: Path, name: str, image: np.ndarray) -> Path:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    path = tmp_path / name
    path.write_bytes(encoded.tobytes())
    return path


@pytest.fixture
def gradient_tools_image_path(tmp_path: Path) -> Path:
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    for x in range(300):
        value = int(70 + 150 * (x / 299.0))
        image[:, x] = (value, value, value)
    cv2.rectangle(image, (30, 40), (120, 130), (15, 15, 15), thickness=-1)
    cv2.rectangle(image, (190, 60), (260, 140), (15, 15, 15), thickness=-1)
    return _write_png(tmp_path, "gradient_tools.png", image)


@pytest.fixture
def cluttered_tools_image_path(tmp_path: Path) -> Path:
    image = np.full((200, 300, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (30, 40), (120, 130), (0, 0, 0), thickness=-1)
    cv2.rectangle(image, (190, 60), (260, 140), (0, 0, 0), thickness=-1)
    cv2.rectangle(image, (4, 4), (10, 10), (0, 0, 0), thickness=-1)
    cv2.rectangle(image, (286, 186), (292, 192), (0, 0, 0), thickness=-1)
    return _write_png(tmp_path, "cluttered_tools.png", image)


@pytest.fixture
def low_contrast_tools_image_path(tmp_path: Path) -> Path:
    image = np.full((200, 300, 3), 150, dtype=np.uint8)
    cv2.rectangle(image, (30, 40), (120, 130), (105, 105, 105), thickness=-1)
    cv2.rectangle(image, (190, 60), (260, 140), (105, 105, 105), thickness=-1)
    return _write_png(tmp_path, "low_contrast_tools.png", image)
