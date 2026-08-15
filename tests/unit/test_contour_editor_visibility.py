import os
import gc
import weakref
from dataclasses import replace

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


def test_set_tool_reuses_decoded_photo_only_for_the_same_capture():
    app = QApplication.instance() or QApplication([])
    editor = ContourEditor()
    source_requests: list[str] = []

    class Controller:
        def capture_display_bytes(self, capture_id: str) -> bytes:
            source_requests.append(capture_id)
            if capture_id == "capture-1":
                return _png_bytes(400, 300)
            return _png_bytes(160, 120)

        def calibration_for_capture(self, capture_id: str) -> CalibrationRecord:
            return replace(
                _calibration(),
                id=f"cal-{capture_id}",
                capture_id=capture_id,
            )

    editor.controller = Controller()
    first = _tool()
    second = replace(first, id="tool-2", name="Second Tool")
    other_capture = replace(
        first,
        id="tool-3",
        name="Other Capture Tool",
        source_capture_id="capture-2",
    )

    editor.set_tool(first)
    first_pixmap_key = editor._source_pixmap.cacheKey()
    editor.set_tool(second)
    second_pixmap_key = editor._source_pixmap.cacheKey()

    class ReplacementController(Controller):
        def capture_display_bytes(self, capture_id: str) -> bytes:
            source_requests.append(f"replacement:{capture_id}")
            if capture_id == "capture-1":
                return _png_bytes(220, 140)
            return _png_bytes(160, 120)

    editor.controller = ReplacementController()
    editor.set_tool(first)
    replacement_width = editor._source_pixmap.width()
    editor.set_tool(other_capture)
    app.processEvents()

    assert source_requests == [
        "capture-1",
        "replacement:capture-1",
        "replacement:capture-2",
    ]
    assert second_pixmap_key == first_pixmap_key
    assert replacement_width == 220
    assert editor._source_pixmap.width() == 160
    assert editor._source_pixmap.height() == 120
    editor.close()


def test_source_pixmap_cache_does_not_retain_replaced_controller():
    app = QApplication.instance() or QApplication([])
    editor = ContourEditor()

    class Controller:
        def capture_display_bytes(self, _capture_id: str) -> bytes:
            return _png_bytes()

        def calibration_for_capture(self, _capture_id: str) -> CalibrationRecord:
            return _calibration()

    controller = Controller()
    controller_ref = weakref.ref(controller)
    editor.controller = controller
    editor.set_tool(_tool())

    editor.controller = None
    del controller
    gc.collect()

    assert controller_ref() is None
    editor.close()


def test_source_pixmap_cache_does_not_reuse_after_controller_dies():
    app = QApplication.instance() or QApplication([])
    editor = ContourEditor()

    class Controller:
        def capture_display_bytes(self, _capture_id: str) -> bytes:
            return _png_bytes()

        def calibration_for_capture(self, _capture_id: str) -> CalibrationRecord:
            return _calibration()

    controller = Controller()
    editor.controller = controller
    editor.set_tool(_tool())
    assert editor._source_pixmap is not None

    editor.controller = None
    del controller
    gc.collect()
    editor.set_tool(_tool())
    app.processEvents()

    assert editor._source_pixmap is None
    editor.close()
