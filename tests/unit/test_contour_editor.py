import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from tooldrawer_studio.calibration.service import PixelPoint, calibrate_known_distance
from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.ui.contour_editor import ContourEditor


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _tool() -> ToolObject:
    contour = [Point2D(0, 0), Point2D(20, 0), Point2D(20, 10), Point2D(0, 10)]
    return ToolObject(
        id="tool-1",
        name="Wrench",
        source_capture_id="capture-1",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=0.6,
    )


def test_insert_and_delete_vertex_keep_a_valid_contour():
    app = _app()
    editor = ContourEditor()
    editor.set_tool(_tool())
    editor.insert_vertex(0, Point2D(10, 0))
    assert len(editor.contour()) == 5
    editor.delete_vertex(1)
    assert len(editor.contour()) == 4
    editor.close()
    assert app is not None


def test_click_near_edge_inserts_a_vertex():
    app = _app()
    editor = ContourEditor()
    editor.set_tool(_tool())
    editor.show()
    app.processEvents()
    editor._edge_clicked(QPointF(10.0, 0.0))
    app.processEvents()
    assert len(editor.contour()) == 5
    editor.close()


def test_photo_overlay_warps_calibrated_image_into_millimetres():
    app = _app()
    pixels = np.full((80, 120, 3), 200, dtype=np.uint8)
    pixels[10:50, 20:80] = (20, 20, 20)
    calibration = calibrate_known_distance(
        "capture-1", PixelPoint(0.0, 0.0), PixelPoint(100.0, 0.0), 100.0
    )
    editor = ContourEditor()
    editor.set_tool(_tool(), pixels_bgr=pixels, calibration=calibration)
    assert not editor.view.pixmap_item.pixmap().isNull()
    assert editor.show_photo.isChecked()
    editor.close()
    assert app is not None


def test_smooth_and_simplify_actions_keep_a_closed_contour():
    app = _app()
    editor = ContourEditor()
    editor.set_tool(_tool())
    editor.smooth_contour()
    editor.simplify_contour()
    assert len(editor.contour()) >= 4
    editor.close()
    assert app is not None
