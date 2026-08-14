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
    QGraphicsItemGroup,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from tooldrawer_studio.calibration.service import PixelPoint


class CalibrationImageView(QGraphicsView):
    MIN_ZOOM = 0.10
    MAX_ZOOM = 16.0

    pointsChanged = Signal(object)
    zoomChanged = Signal(float)
    fitModeChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = self._scene.addPixmap(QPixmap())
        self._pixmap_item.setZValue(0.0)
        self._overlay_group: QGraphicsItemGroup | None = None
        self._points: list[PixelPoint] = []
        self._required_points = 0
        self._fit_mode = True
        self._manual_navigation = False
        self._space_down = False
        self._panning = False
        self._pan_start = QPoint()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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

    def points_px(self) -> tuple[PixelPoint, ...]:
        return tuple(self._points)

    def clear_points(self) -> None:
        self._points.clear()
        self._redraw_overlay()
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
        super().resizeEvent(event)
        if self._fit_mode:
            self.fit_image()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._pixmap_item.pixmap().isNull() or event.angleDelta().y() == 0:
            super().wheelEvent(event)
            return
        previous_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        factor = 1.20 if event.angleDelta().y() > 0 else (1.0 / 1.20)
        self._set_zoom_scale(abs(float(self.transform().m11())) * factor)
        self.setTransformationAnchor(previous_anchor)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
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
                self.unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.fit_image()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

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

        scene_position = self.mapToScene(event.position().toPoint())
        image_rect = self._pixmap_item.boundingRect()
        if not image_rect.contains(scene_position):
            super().mousePressEvent(event)
            return

        if len(self._points) >= self._required_points:
            self.clear_points()

        self._points.append(
            PixelPoint(float(scene_position.x()), float(scene_position.y()))
        )
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
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and event.button() in (
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.LeftButton,
        ):
            self._panning = False
            if self._space_down:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _redraw_overlay(self) -> None:
        if self._overlay_group is not None:
            self._scene.removeItem(self._overlay_group)
            self._overlay_group = None

        group = QGraphicsItemGroup()
        group.setZValue(10.0)
        self._scene.addItem(group)

        pen = QPen(QColor(210, 30, 30))
        pen.setWidthF(2.0)
        brush = QBrush(QColor(255, 255, 255, 220))
        radius = 6.0
        for index, point in enumerate(self._points, start=1):
            marker = self._scene.addEllipse(
                point.x_px - radius,
                point.y_px - radius,
                radius * 2.0,
                radius * 2.0,
                pen,
                brush,
            )
            group.addToGroup(marker)
            label = QGraphicsSimpleTextItem(str(index))
            label.setBrush(QBrush(QColor(210, 30, 30)))
            label.setPos(QPointF(point.x_px + radius + 2.0, point.y_px - radius - 2.0))
            self._scene.addItem(label)
            group.addToGroup(label)

        self._overlay_group = group
