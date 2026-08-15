from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
)

from tooldrawer_studio.image_analysis import refine_corner_subpixel, snap_to_polyline
from tooldrawer_studio.measurement.models import ImagePoint
from tooldrawer_studio.ui.image_view import ZoomableImageView


class _EndpointHandle(QGraphicsEllipseItem):
    def __init__(
        self,
        position: ImagePoint,
        bounds: QRectF,
        changed: Callable[[], None],
        released: Callable[[], None],
    ) -> None:
        radius = 6.0
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0)
        self._bounds = bounds
        self._changed = changed
        self._released = released
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

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self._released()


class MeasurementImageView(ZoomableImageView):
    endpointsChanged = Signal(object)
    silhouetteClicked = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._silhouette_item: QGraphicsPathItem | None = None
        self._alternate_items: list[QGraphicsPathItem] = []
        self._measurement_line: QGraphicsLineItem | None = None
        self._endpoint_handles: list[_EndpointHandle] = []
        self._manual_point_mode = False
        self._updating = False
        self._silhouette: list[ImagePoint] = []

    def set_image_bytes(self, raw: bytes) -> None:
        super().set_image_bytes(raw)
        self.clear_measurement()

    def set_manual_point_mode(self, enabled: bool) -> None:
        self._manual_point_mode = bool(enabled)

    def endpoints_px(self) -> tuple[ImagePoint, ...]:
        return tuple(
            ImagePoint(float(handle.pos().x()), float(handle.pos().y()))
            for handle in self._endpoint_handles
        )

    def _remove_item(self, item) -> None:
        if item is not None and item.scene() is self.scene():
            self.scene().removeItem(item)

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
            for item in self._alternate_items:
                self._remove_item(item)
            self._alternate_items.clear()
            self._silhouette = []
        finally:
            self._updating = False

    def _path_item(self, points: list[ImagePoint], color: QColor, z: float) -> QGraphicsPathItem:
        path = QPainterPath(QPointF(points[0].x_px, points[0].y_px))
        for point in points[1:]:
            path.lineTo(QPointF(point.x_px, point.y_px))
        path.closeSubpath()
        item = QGraphicsPathItem(path)
        pen = QPen(color)
        pen.setWidthF(1.5)
        item.setPen(pen)
        item.setZValue(z)
        self.scene().addItem(item)
        return item

    def _set_silhouette(self, silhouette: Iterable[ImagePoint]) -> None:
        points = list(silhouette)
        self._silhouette = points
        if not points:
            return
        self._silhouette_item = self._path_item(points, QColor(30, 150, 50), 10.0)

    def _image_bounds(self) -> QRectF:
        pixmap = self.pixmap_item.pixmap()
        if pixmap.isNull():
            raise ValueError("Load a side-view image before setting measurement points")
        return self.pixmap_item.boundingRect()

    def _add_endpoint(self, point: ImagePoint) -> None:
        handle = _EndpointHandle(
            point,
            self._image_bounds(),
            self._handle_changed,
            self._snap_endpoints,
        )
        self.scene().addItem(handle)
        self._endpoint_handles.append(handle)

    def set_overlay(
        self,
        silhouette: Iterable[ImagePoint],
        endpoint_a: ImagePoint | None = None,
        endpoint_b: ImagePoint | None = None,
        alternatives: Iterable[Iterable[ImagePoint]] = (),
    ) -> None:
        if (endpoint_a is None) != (endpoint_b is None):
            raise ValueError("Measurement overlay requires either zero or two endpoints")
        self._updating = True
        try:
            self.clear_measurement()
            self._updating = True
            for alternate in alternatives:
                points = list(alternate)
                if len(points) >= 3:
                    self._alternate_items.append(
                        self._path_item(points, QColor(140, 140, 140, 160), 8.0)
                    )
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
                self.scene().addItem(self._measurement_line)
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

    def _snap_endpoints(self) -> None:
        if self._updating or not self._silhouette:
            return
        self._updating = True
        try:
            for handle in self._endpoint_handles:
                current = ImagePoint(float(handle.pos().x()), float(handle.pos().y()))
                snapped = snap_to_polyline(current, self._silhouette)
                handle.setPos(QPointF(snapped.x_px, snapped.y_px))
        finally:
            self._updating = False
        self._redraw_line_and_emit()

    def _refine(self, x_px: float, y_px: float) -> ImagePoint:
        gray = self._gray
        if gray is None:
            point = ImagePoint(x_px, y_px)
        else:
            rx, ry = refine_corner_subpixel(gray, x_px, y_px)
            point = ImagePoint(rx, ry)
        if self._silhouette:
            return snap_to_polyline(point, self._silhouette)
        return point

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._begin_pan(event):
            return
        if (
            event.button() != Qt.MouseButton.LeftButton
            or self.pixmap_item.pixmap().isNull()
        ):
            super().mousePressEvent(event)
            return

        item = self.itemAt(event.position().toPoint())
        if isinstance(item, _EndpointHandle):
            super().mousePressEvent(event)
            return

        scene_position = self.mapToScene(event.position().toPoint())
        bounds = self.pixmap_item.boundingRect()
        if not bounds.contains(scene_position):
            super().mousePressEvent(event)
            return

        if not self._manual_point_mode:
            self.silhouetteClicked.emit(
                ImagePoint(float(scene_position.x()), float(scene_position.y()))
            )
            event.accept()
            return

        if len(self._endpoint_handles) >= 2:
            self._clear_endpoints()
        self._add_endpoint(
            self._refine(float(scene_position.x()), float(scene_position.y()))
        )
        self._redraw_line_and_emit()
        event.accept()
