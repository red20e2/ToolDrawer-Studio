from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainterPath, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
)

from tooldrawer_studio.measurement.models import ImagePoint


class _EndpointHandle(QGraphicsEllipseItem):
    def __init__(
        self,
        position: ImagePoint,
        bounds: QRectF,
        changed: Callable[[], None],
    ) -> None:
        radius = 6.0
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0)
        self._bounds = bounds
        self._changed = changed
        self.setBrush(QColor(255, 255, 255, 235))
        pen = QPen(QColor(210, 30, 30))
        pen.setWidthF(2.0)
        self.setPen(pen)
        self.setZValue(30.0)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPos(QPointF(position.x_px, position.y_px))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            point = value
            max_x = max(self._bounds.left(), self._bounds.right() - 1.0)
            max_y = max(self._bounds.top(), self._bounds.bottom() - 1.0)
            return QPointF(
                min(max(float(point.x()), self._bounds.left()), max_x),
                min(max(float(point.y()), self._bounds.top()), max_y),
            )
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._changed()
        return result


class MeasurementImageView(QGraphicsView):
    endpointsChanged = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = self._scene.addPixmap(QPixmap())
        self._pixmap_item.setZValue(0.0)
        self._silhouette_item: QGraphicsPathItem | None = None
        self._measurement_line: QGraphicsLineItem | None = None
        self._endpoint_handles: list[_EndpointHandle] = []
        self._manual_point_mode = False
        self._updating = False
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
        self.clear_measurement()
        self._fit_image()

    def _fit_image(self) -> None:
        pixmap = self._pixmap_item.pixmap()
        if pixmap.isNull():
            return
        self.fitInView(
            self._pixmap_item.boundingRect(), Qt.AspectRatioMode.KeepAspectRatio
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_image()

    def set_manual_point_mode(self, enabled: bool) -> None:
        self._manual_point_mode = bool(enabled)

    def endpoints_px(self) -> tuple[ImagePoint, ...]:
        return tuple(
            ImagePoint(float(handle.pos().x()), float(handle.pos().y()))
            for handle in self._endpoint_handles
        )

    def _remove_item(self, item) -> None:
        if item is not None and item.scene() is self._scene:
            self._scene.removeItem(item)

    def _clear_endpoints(self) -> None:
        for handle in self._endpoint_handles:
            self._remove_item(handle)
        self._endpoint_handles.clear()
        self._remove_item(self._measurement_line)
        self._measurement_line = None

    def clear_measurement(self) -> None:
        self._updating = True
        try:
            self._clear_endpoints()
            self._remove_item(self._silhouette_item)
            self._silhouette_item = None
        finally:
            self._updating = False

    def _set_silhouette(self, silhouette: Iterable[ImagePoint]) -> None:
        points = list(silhouette)
        if not points:
            return
        path = QPainterPath(QPointF(points[0].x_px, points[0].y_px))
        for point in points[1:]:
            path.lineTo(QPointF(point.x_px, point.y_px))
        path.closeSubpath()
        item = QGraphicsPathItem(path)
        pen = QPen(QColor(30, 150, 50))
        pen.setWidthF(1.5)
        item.setPen(pen)
        item.setZValue(10.0)
        self._scene.addItem(item)
        self._silhouette_item = item

    def _image_bounds(self) -> QRectF:
        pixmap = self._pixmap_item.pixmap()
        if pixmap.isNull():
            raise ValueError("Load a side-view image before setting measurement points")
        return self._pixmap_item.boundingRect()

    def _add_endpoint(self, point: ImagePoint) -> None:
        handle = _EndpointHandle(point, self._image_bounds(), self._handle_changed)
        self._scene.addItem(handle)
        self._endpoint_handles.append(handle)

    def set_overlay(
        self,
        silhouette: Iterable[ImagePoint],
        endpoint_a: ImagePoint | None = None,
        endpoint_b: ImagePoint | None = None,
    ) -> None:
        if (endpoint_a is None) != (endpoint_b is None):
            raise ValueError("Measurement overlay requires either zero or two endpoints")
        self._updating = True
        try:
            self.clear_measurement()
            self._updating = True
            self._set_silhouette(silhouette)
            if endpoint_a is not None and endpoint_b is not None:
                self._add_endpoint(endpoint_a)
                self._add_endpoint(endpoint_b)
                self._redraw_line_and_emit()
        finally:
            self._updating = False

    def _redraw_line_and_emit(self) -> None:
        points = self.endpoints_px()
        if len(points) == 2:
            if self._measurement_line is None:
                self._measurement_line = QGraphicsLineItem()
                pen = QPen(QColor(210, 30, 30))
                pen.setWidthF(2.0)
                self._measurement_line.setPen(pen)
                self._measurement_line.setZValue(20.0)
                self._scene.addItem(self._measurement_line)
            self._measurement_line.setLine(
                points[0].x_px,
                points[0].y_px,
                points[1].x_px,
                points[1].y_px,
            )
            if not self._updating:
                self.endpointsChanged.emit((points[0], points[1]))
        else:
            self._remove_item(self._measurement_line)
            self._measurement_line = None

    def _handle_changed(self) -> None:
        self._redraw_line_and_emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            not self._manual_point_mode
            or event.button() != Qt.MouseButton.LeftButton
            or self._pixmap_item.pixmap().isNull()
        ):
            super().mousePressEvent(event)
            return

        scene_position = self.mapToScene(event.position().toPoint())
        bounds = self._pixmap_item.boundingRect()
        if not bounds.contains(scene_position):
            super().mousePressEvent(event)
            return

        if len(self._endpoint_handles) >= 2:
            self._clear_endpoints()
        self._add_endpoint(
            ImagePoint(float(scene_position.x()), float(scene_position.y()))
        )
        self._redraw_line_and_emit()
        event.accept()
