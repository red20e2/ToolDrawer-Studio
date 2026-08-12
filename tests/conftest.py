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
