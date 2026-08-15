import os

import cv2
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.ui.main_window import MainWindow


def _png_bytes(width: int = 400, height: int = 300) -> bytes:
    pixels = np.full((height, width, 3), 235, dtype=np.uint8)
    pixels[30:270, 140:185] = (35, 35, 35)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def test_selected_detected_tool_shows_source_photo_behind_trace():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    capture_id = window.controller.import_image_bytes(_png_bytes(), "top.png")
    window.controller.calibrate_known_distance(
        PixelPoint(20.0, 20.0), PixelPoint(220.0, 20.0), 100.0
    )
    contour = [
        Point2D(60.0, 20.0),
        Point2D(85.0, 20.0),
        Point2D(85.0, 135.0),
        Point2D(60.0, 135.0),
    ]
    tool = ToolObject(
        id="tool-1",
        name="Test Tool",
        source_capture_id=capture_id,
        base_contour_mm=list(contour),
        contour_mm=list(contour),
    )
    window.controller.project.tools.append(tool)

    window._populate_tools([tool])
    app.processEvents()

    pixmap_items = [
        item
        for item in window.contour_editor.scene.items()
        if isinstance(item, QGraphicsPixmapItem)
    ]
    assert len(pixmap_items) == 1
    assert window.tool_list.currentRow() == 0
    window.close()
