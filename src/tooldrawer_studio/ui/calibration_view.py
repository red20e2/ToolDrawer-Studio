from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPen,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from tooldrawer_studio.calibration.service import PixelPoint


class CalibrationImageView(QGraphicsView):
    MIN_ZOOM = 0.10
    MAX_ZOOM = 16.0
    POINT_HIT_RADIUS_PX = 10.0

    pointsChanged = Signal(object)
    selectedPointChanged = Signal(object)
    zoomChanged = Signal(float)
    fitModeChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = self._scene.addPixmap(QPixmap())
        self._pixmap_item.setZValue(0.0)
        self._overlay_items: list[QGraphicsItem] = []
        self._points: list[PixelPoint] = []
        self._required_points = 0
        self._selected_point_index: int | None = None
        self._dragging_point = False
        self._fit_mode = True
        self._manual_navigation = False
        self._space_down = False
        self._panning = False
        self._pan_start = QPoint()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._restore_interaction_cursor()

    def set_image_bytes(self, raw: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(raw):
            raise ValueError("Unsupported or invalid image data")
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(pixmap.rect())
        self.clear_points()
        self.fit_image()

    def set_required_points(self, count: int) -> None:
        if count < 0:
            raise ValueError("Required calibration point count cannot be negative")
        if count != self._required_points:
            self._required_points = int(count)
            self.clear_points()
        self._restore_interaction_cursor()

    def points_px(self) -> tuple[PixelPoint, ...]:
        return tuple(self._points)

    def selected_point_index(self) -> int | None:
        return self._selected_point_index

    def _set_selected_point(self, index: int | None, *, redraw: bool = True) -> None:
        if index is not None and not 0 <= index < len(self._points):
            index = None
        changed = index != self._selected_point_index
        self._selected_point_index = index
        if redraw:
            self._redraw_overlay()
        if changed:
            self.selectedPointChanged.emit(index)

    def delete_selected_point(self) -> None:
        index = self._selected_point_index
        if index is None or not 0 <= index < len(self._points):
            return
        self._points.pop(index)
        self._dragging_point = False
        self._set_selected_point(None, redraw=False)
        self._redraw_overlay()
        self.pointsChanged.emit(self.points_px())

    def clear_points(self) -> None:
        had_selection = self._selected_point_index is not None
        self._points.clear()
        self._selected_point_index = None
        self._dragging_point = False
        self._redraw_overlay()
        if had_selection:
            self.selectedPointChanged.emit(None)
        self.pointsChanged.emit(self.points_px())

    def zoom_percent(self) -> float:
        return abs(float(self.transform().m11())) * 100.0

    def is_fit_mode(self) -> bool:
        return self._fit_mode

    def _emit_view_state(self) -> None:
        self.zoomChanged.emit(self.zoom_percent())
        self.fitModeChanged.emit(self._fit_mode)

    def _mark_manual_navigation(self) -> None:
        changed = self._fit_mode
        self._fit_mode = False
        self._manual_navigation = True
        self.zoomChanged.emit(self.zoom_percent())
        if changed:
            self.fitModeChanged.emit(False)

    def fit_image(self) -> None:
        pixmap = self._pixmap_item.pixmap()
        if pixmap.isNull():
            return
        self.resetTransform()
        self.fitInView(
            self._pixmap_item.boundingRect(),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self._fit_mode = True
        self._manual_navigation = False
        self._emit_view_state()

    def set_actual_size(self) -> None:
        pixmap = self._pixmap_item.pixmap()
        if pixmap.isNull():
            return
        center = self._pixmap_item.boundingRect().center()
        self.resetTransform()
        self.centerOn(center)
        self._mark_manual_navigation()

    def _set_zoom_scale(self, scale: float) -> None:
        pixmap = self._pixmap_item.pixmap()
        if pixmap.isNull():
            return
        target = min(self.MAX_ZOOM, max(self.MIN_ZOOM, float(scale)))
        current = abs(float(self.transform().m11()))
        if current <= 0.0:
            self.resetTransform()
            current = 1.0
        factor = target / current
        if abs(factor - 1.0) > 1e-12:
            self.scale(factor, factor)
        self._mark_manual_navigation()

    def resizeEvent(self, event: QResizeEvent) -> None:
        manual_center: QPointF | None = None
        old_size = event.oldSize()
        if (
            not self._fit_mode
            and not self._pixmap_item.pixmap().isNull()
            and old_size.isValid()
        ):
            chrome_width = max(0, event.size().width() - self.viewport().width())
            chrome_height = max(0, event.size().height() - self.viewport().height())
            old_viewport_width = max(1, old_size.width() - chrome_width)
            old_viewport_height = max(1, old_size.height() - chrome_height)
            old_center = QPoint(
                (old_viewport_width - 1) // 2,
                (old_viewport_height - 1) // 2,
            )
            manual_center = self.mapToScene(old_center)
        super().resizeEvent(event)
        if self._fit_mode:
            self.fit_image()
        elif manual_center is not None:
            self.centerOn(manual_center)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._pixmap_item.pixmap().isNull() or event.angleDelta().y() == 0:
            super().wheelEvent(event)
            return
        viewport_position = event.position().toPoint()
        scene_before = self.mapToScene(viewport_position)
        previous_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        factor = 1.20 if event.angleDelta().y() > 0 else (1.0 / 1.20)
        self._set_zoom_scale(abs(float(self.transform().m11())) * factor)
        scene_after = self.mapToScene(viewport_position)
        delta = scene_after - scene_before
        self.translate(delta.x(), delta.y())
        self.setTransformationAnchor(previous_anchor)
        event.accept()

    def _restore_interaction_cursor(self) -> None:
        if self._space_down:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self._required_points > 0:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected_point()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._dragging_point = False
            self._set_selected_point(None)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = True
            if not self._panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = False
            if not self._panning:
                self._restore_interaction_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.fit_image()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _point_at_viewport(self, position: QPoint) -> int | None:
        threshold_squared = self.POINT_HIT_RADIUS_PX * self.POINT_HIT_RADIUS_PX
        nearest_index: int | None = None
        nearest_distance = threshold_squared + 1.0
        for index, point in enumerate(self._points):
            mapped = self.mapFromScene(QPointF(point.x_px, point.y_px))
            dx = float(mapped.x() - position.x())
            dy = float(mapped.y() - position.y())
            distance = dx * dx + dy * dy
            if distance <= threshold_squared and distance < nearest_distance:
                nearest_index = index
                nearest_distance = distance
        return nearest_index

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_down
        ):
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if (
            event.button() != Qt.MouseButton.LeftButton
            or self._required_points <= 0
            or self._pixmap_item.pixmap().isNull()
        ):
            super().mousePressEvent(event)
            return

        viewport_position = event.position().toPoint()
        hit_index = self._point_at_viewport(viewport_position)
        if hit_index is not None:
            self._set_selected_point(hit_index)
            self._dragging_point = True
            event.accept()
            return

        scene_position = self.mapToScene(viewport_position)
        image_rect = self._pixmap_item.boundingRect()
        if not image_rect.contains(scene_position):
            super().mousePressEvent(event)
            return

        if len(self._points) >= self._required_points:
            event.accept()
            return

        self._points.append(
            PixelPoint(float(scene_position.x()), float(scene_position.y()))
        )
        self._set_selected_point(len(self._points) - 1, redraw=False)
        self._redraw_overlay()
        self.pointsChanged.emit(self.points_px())
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            current = event.position().toPoint()
            delta = current - self._pan_start
            self._pan_start = current
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            self._mark_manual_navigation()
            event.accept()
            return

        if self._dragging_point and self._selected_point_index is not None:
            scene_position = self.mapToScene(event.position().toPoint())
            if self._pixmap_item.boundingRect().contains(scene_position):
                self._points[self._selected_point_index] = PixelPoint(
                    float(scene_position.x()),
                    float(scene_position.y()),
                )
                self._redraw_overlay()
                self.pointsChanged.emit(self.points_px())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.LeftButton,
        ):
            self._panning = False
            self._restore_interaction_cursor()
            event.accept()
            return
        if self._dragging_point and event.button() == Qt.MouseButton.LeftButton:
            self._dragging_point = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _clear_overlay(self) -> None:
        for item in self._overlay_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._overlay_items.clear()

    def _add_overlay_line(self, first: PixelPoint, second: PixelPoint) -> None:
        pen = QPen(QColor(210, 30, 30))
        pen.setWidthF(2.0)
        pen.setCosmetic(True)
        line = self._scene.addLine(
            first.x_px,
            first.y_px,
            second.x_px,
            second.y_px,
            pen,
        )
        line.setZValue(9.0)
        self._overlay_items.append(line)

    def _redraw_overlay(self) -> None:
        self._clear_overlay()

        if self._required_points == 4:
            for index in range(max(0, len(self._points) - 1)):
                self._add_overlay_line(self._points[index], self._points[index + 1])
            if len(self._points) == 4:
                self._add_overlay_line(self._points[-1], self._points[0])
        elif len(self._points) >= 2:
            self._add_overlay_line(self._points[0], self._points[1])

        radius = 6.0
        for index, point in enumerate(self._points):
            selected = index == self._selected_point_index
            pen = QPen(QColor(210, 30, 30))
            pen.setWidthF(3.0 if selected else 2.0)
            pen.setCosmetic(True)
            brush = QBrush(
                QColor(255, 245, 170, 240)
                if selected
                else QColor(255, 255, 255, 220)
            )
            marker = self._scene.addEllipse(
                -radius,
                -radius,
                radius * 2.0,
                radius * 2.0,
                pen,
                brush,
            )
            marker.setPos(QPointF(point.x_px, point.y_px))
            marker.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            marker.setZValue(10.0)
            self._overlay_items.append(marker)

            label = QGraphicsSimpleTextItem(str(index + 1), marker)
            label.setBrush(QBrush(QColor(210, 30, 30)))
            label.setPos(QPointF(radius + 2.0, -radius - 2.0))
            label.setZValue(1.0)
