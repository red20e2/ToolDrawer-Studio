from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsSimpleTextItem,
)

from tooldrawer_studio.ui.calibration_view import CalibrationImageView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _image_bytes(width: int = 1000, height: int = 700) -> bytes:
    pixels = np.full((height, width, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def _device_origin(item, view: CalibrationImageView) -> QPointF:
    return item.deviceTransform(view.viewportTransform()).map(QPointF(0.0, 0.0))


def _marker_and_label(view: CalibrationImageView):
    marker = next(
        item for item in view.scene().items() if isinstance(item, QGraphicsEllipseItem)
    )
    label = next(
        item for item in view.scene().items() if isinstance(item, QGraphicsSimpleTextItem)
    )
    return marker, label


def test_point_number_label_stays_anchored_to_marker_at_high_zoom():
    app = _app()
    view = CalibrationImageView()
    view.resize(800, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes())
    view.set_required_points(2)
    view.set_actual_size()

    target = view.mapFromScene(QPointF(500.0, 350.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    app.processEvents()

    marker, label = _marker_and_label(view)
    marker_origin = _device_origin(marker, view)
    label_origin = _device_origin(label, view)
    baseline_dx = label_origin.x() - marker_origin.x()
    baseline_dy = label_origin.y() - marker_origin.y()

    view._set_zoom_scale(8.0)
    app.processEvents()

    marker, label = _marker_and_label(view)
    marker_origin = _device_origin(marker, view)
    label_origin = _device_origin(label, view)
    zoomed_dx = label_origin.x() - marker_origin.x()
    zoomed_dy = label_origin.y() - marker_origin.y()

    assert zoomed_dx == pytest.approx(baseline_dx, abs=2.0)
    assert zoomed_dy == pytest.approx(baseline_dy, abs=2.0)
    view.close()
