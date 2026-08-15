import os

import cv2
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem

from tooldrawer_studio.domain.models import CalibrationRecord, Point2D, ToolObject
from tooldrawer_studio.ui.contour_editor import ContourEditor


def _tool() -> ToolObject:
    contour = [
        Point2D(10.0, 10.0),
        Point2D(30.0, 10.0),
        Point2D(30.0, 160.0),
        Point2D(10.0, 160.0),
    ]
    return ToolObject(
        id="tool-1",
        name="Test Tool",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
    )


def _png_bytes(width: int = 400, height: int = 300) -> bytes:
    pixels = np.full((height, width, 3), 230, dtype=np.uint8)
    pixels[40:260, 120:180] = (40, 40, 40)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def _calibration() -> CalibrationRecord:
    # 2 px/mm, expressed as a pixel -> mm transform.
    return CalibrationRecord(
        id="cal-1",
        capture_id="capture-1",
        method="known_distance",
        matrix_3x3=(
            (0.5, 0.0, 0.0),
            (0.0, 0.5, 0.0),
            (0.0, 0.0, 1.0),
        ),
        residual_mm=0.0,
        confidence=0.98,
    )


def test_set_tool_auto_fits_trace_so_it_is_visibly_large():
    app = QApplication.instance() or QApplication([])
    editor = ContourEditor()
    editor.resize(1000, 700)
    editor.show()
    app.processEvents()

    editor.set_tool(_tool())
    app.processEvents()

    bounds = editor.scene.itemsBoundingRect()
    mapped = editor.view.mapFromScene(bounds).boundingRect()
    assert mapped.height() >= editor.view.viewport().height() * 0.60
    assert mapped.width() > 20
    editor.close()


def test_set_tool_can_overlay_source_photo_in_same_calibrated_space():
    app = QApplication.instance() or QApplication([])
    editor = ContourEditor()
    editor.resize(1000, 700)
    editor.show()
    app.processEvents()

    editor.set_tool(
        _tool(),
        image_bytes=_png_bytes(),
        calibration=_calibration(),
    )
    app.processEvents()

    pixmap_items = [
        item for item in editor.scene.items() if isinstance(item, QGraphicsPixmapItem)
    ]
    assert len(pixmap_items) == 1
    image_item = pixmap_items[0]
    mapped = image_item.mapToScene(QPointF(20.0, 30.0))
    assert mapped.x() == pytest.approx(10.0, abs=1e-6)
    assert mapped.y() == pytest.approx(15.0, abs=1e-6)
    assert image_item.zValue() < 0
    editor.close()
