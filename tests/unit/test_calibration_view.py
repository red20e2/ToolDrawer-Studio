import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsLineItem

from tooldrawer_studio.ui.calibration_view import CalibrationImageView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _image_bytes(width: int = 1000, height: int = 500) -> bytes:
    pixels = np.full((height, width, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def _marker(view: CalibrationImageView) -> QGraphicsEllipseItem:
    markers = [
        item for item in view.scene().items() if isinstance(item, QGraphicsEllipseItem)
    ]
    assert markers
    return markers[0]


def _marker_device_size(view: CalibrationImageView) -> tuple[float, float]:
    marker = _marker(view)
    transform = marker.deviceTransform(view.viewportTransform())
    rect = transform.mapRect(marker.boundingRect())
    return rect.width(), rect.height()


def test_center_click_maps_to_native_image_pixels():
    app = _app()
    view = CalibrationImageView()
    view.resize(500, 250)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(2)
    view.show()
    app.processEvents()

    viewport_point = view.mapFromScene(QPointF(500.0, 250.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=viewport_point)
    app.processEvents()

    points = view.points_px()
    assert len(points) == 1
    assert points[0].x_px == pytest.approx(500.0, abs=3.0)
    assert points[0].y_px == pytest.approx(250.0, abs=3.0)
    view.close()


def test_click_after_required_count_preserves_completed_point_sequence():
    app = _app()
    view = CalibrationImageView()
    view.resize(500, 250)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(2)
    view.show()
    app.processEvents()

    first_scene = QPointF(200.0, 200.0)
    second_scene = QPointF(800.0, 200.0)
    third_scene = QPointF(500.0, 400.0)
    for scene_position in (first_scene, second_scene, third_scene):
        position = view.mapFromScene(scene_position)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=position)
        app.processEvents()

    points = view.points_px()
    assert len(points) == 2
    assert points[0].x_px == pytest.approx(200.0, abs=3.0)
    assert points[0].y_px == pytest.approx(200.0, abs=3.0)
    assert points[1].x_px == pytest.approx(800.0, abs=3.0)
    assert points[1].y_px == pytest.approx(200.0, abs=3.0)
    view.close()


def test_zero_required_points_disables_manual_collection():
    app = _app()
    view = CalibrationImageView()
    view.resize(500, 250)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(0)
    view.show()
    app.processEvents()

    point = view.mapFromScene(QPointF(500.0, 250.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()

    assert view.points_px() == ()
    view.close()


def test_new_portrait_image_starts_in_fit_mode_and_reports_zoom():
    app = _app()
    view = CalibrationImageView()
    view.resize(900, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=600, height=1200))
    app.processEvents()

    assert view.is_fit_mode() is True
    assert 0.0 < view.zoom_percent() <= 100.0
    view.close()


def test_new_landscape_image_starts_in_fit_mode_and_reports_zoom():
    app = _app()
    view = CalibrationImageView()
    view.resize(900, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=1600, height=700))
    app.processEvents()

    assert view.is_fit_mode() is True
    assert 0.0 < view.zoom_percent() <= 100.0
    view.close()


def test_actual_size_is_100_percent_and_manual_view_survives_resize():
    app = _app()
    view = CalibrationImageView()
    view.resize(800, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=1000, height=500))
    view.set_actual_size()

    assert view.zoom_percent() == pytest.approx(100.0, abs=0.5)
    assert view.is_fit_mode() is False

    before = view.transform().m11()
    view.resize(1000, 700)
    app.processEvents()
    assert view.transform().m11() == pytest.approx(before, rel=1e-6)
    view.close()


def test_zoom_scale_clamps_between_ten_and_sixteen_hundred_percent():
    app = _app()
    view = CalibrationImageView()
    view.resize(800, 600)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=1000, height=500))

    view._set_zoom_scale(0.001)
    assert view.zoom_percent() == pytest.approx(10.0, abs=0.5)
    assert view.is_fit_mode() is False

    view._set_zoom_scale(100.0)
    assert view.zoom_percent() == pytest.approx(1600.0, abs=0.5)
    view.close()


def test_middle_mouse_drag_pans_actual_size_image():
    app = _app()
    view = CalibrationImageView()
    view.resize(400, 300)
    view.show()
    app.processEvents()
    view.set_image_bytes(_image_bytes(width=2000, height=1600))
    view.set_actual_size()
    app.processEvents()

    before_x = view.horizontalScrollBar().value()
    before_y = view.verticalScrollBar().value()
    start = QPoint(200, 150)
    end = QPoint(140, 100)
    QTest.mousePress(view.viewport(), Qt.MouseButton.MiddleButton, pos=start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.MiddleButton, pos=end)
    app.processEvents()

    assert (view.horizontalScrollBar().value(), view.verticalScrollBar().value()) != (
        before_x,
        before_y,
    )
    assert view.is_fit_mode() is False
    view.close()


def test_point_coordinates_are_invariant_in_actual_size_view():
    app = _app()
    view = CalibrationImageView()
    view.resize(700, 500)
    view.set_image_bytes(_image_bytes(1200, 800))
    view.set_required_points(2)
    view.show()
    app.processEvents()

    view.set_actual_size()
    scene_target = QPointF(725.0, 315.0)
    viewport_target = view.mapFromScene(scene_target)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=viewport_target)
    app.processEvents()

    assert view.points_px()[0].x_px == pytest.approx(725.0, abs=2.0)
    assert view.points_px()[0].y_px == pytest.approx(315.0, abs=2.0)
    view.close()


def test_new_point_is_selected_and_delete_removes_it():
    app = _app()
    view = CalibrationImageView()
    view.resize(700, 500)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(2)
    view.show()
    app.processEvents()

    target = view.mapFromScene(QPointF(250.0, 200.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    assert view.selected_point_index() == 0

    QTest.keyClick(view, Qt.Key.Key_Delete)
    app.processEvents()

    assert view.points_px() == ()
    assert view.selected_point_index() is None
    view.close()


def test_selected_point_can_be_dragged_to_a_new_image_coordinate():
    app = _app()
    view = CalibrationImageView()
    view.resize(700, 500)
    view.set_image_bytes(_image_bytes(1000, 700))
    view.set_required_points(2)
    view.show()
    app.processEvents()
    view.set_actual_size()

    start_scene = QPointF(500.0, 350.0)
    end_scene = QPointF(560.0, 390.0)
    start = view.mapFromScene(start_scene)
    end = view.mapFromScene(end_scene)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(view.viewport(), end)
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
    app.processEvents()

    point = view.points_px()[0]
    assert point.x_px == pytest.approx(560.0, abs=3.0)
    assert point.y_px == pytest.approx(390.0, abs=3.0)
    view.close()


def test_escape_clears_selection_without_deleting_point():
    app = _app()
    view = CalibrationImageView()
    view.resize(700, 500)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(2)
    view.show()
    app.processEvents()

    target = view.mapFromScene(QPointF(250.0, 200.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    assert view.selected_point_index() == 0

    QTest.keyClick(view, Qt.Key.Key_Escape)
    app.processEvents()

    assert len(view.points_px()) == 1
    assert view.selected_point_index() is None
    view.close()


def test_marker_stays_constant_screen_size_when_zoom_changes():
    app = _app()
    view = CalibrationImageView()
    view.resize(700, 500)
    view.set_image_bytes(_image_bytes(1200, 800))
    view.set_required_points(2)
    view.show()
    app.processEvents()

    target = view.mapFromScene(QPointF(600.0, 400.0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=target)
    before = _marker_device_size(view)

    view.set_actual_size()
    app.processEvents()
    after = _marker_device_size(view)

    assert after[0] == pytest.approx(before[0], abs=1.5)
    assert after[1] == pytest.approx(before[1], abs=1.5)
    view.close()


def test_two_points_draw_a_cosmetic_pair_line():
    app = _app()
    view = CalibrationImageView()
    view.resize(700, 500)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(2)
    view.show()
    app.processEvents()

    for scene_point in (QPointF(200.0, 200.0), QPointF(800.0, 200.0)):
        QTest.mouseClick(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=view.mapFromScene(scene_point),
        )
    app.processEvents()

    lines = [item for item in view.scene().items() if isinstance(item, QGraphicsLineItem)]
    assert len(lines) == 1
    assert lines[0].pen().isCosmetic() is True
    view.close()


def test_four_points_draw_polygon_edges():
    app = _app()
    view = CalibrationImageView()
    view.resize(700, 500)
    view.set_image_bytes(_image_bytes())
    view.set_required_points(4)
    view.show()
    app.processEvents()

    for scene_point in (
        QPointF(200.0, 100.0),
        QPointF(800.0, 100.0),
        QPointF(800.0, 400.0),
        QPointF(200.0, 400.0),
    ):
        QTest.mouseClick(
            view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=view.mapFromScene(scene_point),
        )
    app.processEvents()

    lines = [item for item in view.scene().items() if isinstance(item, QGraphicsLineItem)]
    assert len(lines) == 4
    assert all(line.pen().isCosmetic() for line in lines)
    view.close()
