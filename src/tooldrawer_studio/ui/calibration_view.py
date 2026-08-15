from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsSimpleTextItem,
)

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.image_analysis import refine_corner_subpixel
from tooldrawer_studio.ui.image_view import ZoomableImageView


class _PointHandle(QGraphicsEllipseItem):
    def __init__(self, view: "CalibrationImageView", index: int, point: PixelPoint) -> None:
        radius = 6.0
        super().__init__(-radius, -radius, radius * 2.0, radius * 2.0)
        self._view = view
        self.index = index
        self.setPos(QPointF(point.x_px, point.y_px))
        self.setZValue(20.0)
        self.setBrush(QBrush(QColor(255, 255, 255, 220)))
        pen = QPen(QColor(210, 30, 30))
        pen.setWidthF(2.0)
        self.setPen(pen)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self._label = QGraphicsSimpleTextItem(str(index + 1), self)
        self._label.setBrush(QBrush(QColor(210, 30, 30)))
        self._label.setPos(radius + 2.0, -radius - 2.0)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            point = value
            bounds = self._view.pixmap_item.boundingRect()
            return QPointF(
                min(max(float(point.x()), bounds.left()), max(bounds.left(), bounds.right() - 1.0)),
                min(max(float(point.y()), bounds.top()), max(bounds.top(), bounds.bottom() - 1.0)),
            )
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._view._handle_moved(self)
        return result


class CalibrationImageView(ZoomableImageView):
    pointsChanged = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._handles: list[_PointHandle] = []
        self._required_points = 0
        self._updating = False

    def set_image_bytes(self, raw: bytes) -> None:
        super().set_image_bytes(raw)
        self.clear_points()

    def set_required_points(self, count: int) -> None:
        if count < 0:
            raise ValueError("Required calibration point count cannot be negative")
        if count != self._required_points:
            self._required_points = int(count)
            self.clear_points()

    def points_px(self) -> tuple[PixelPoint, ...]:
        return tuple(
            PixelPoint(float(handle.pos().x()), float(handle.pos().y()))
            for handle in self._handles
        )

    def set_points(self, points: Sequence[PixelPoint]) -> None:
        self._rebuild_handles(list(points))
        self.pointsChanged.emit(self.points_px())

    def clear_points(self) -> None:
        self._rebuild_handles([])
        self.pointsChanged.emit(self.points_px())

    def _rebuild_handles(self, points: list[PixelPoint]) -> None:
        self._updating = True
        try:
            for handle in self._handles:
                if handle.scene() is self.scene():
                    self.scene().removeItem(handle)
            self._handles.clear()
            for index, point in enumerate(points):
                handle = _PointHandle(self, index, point)
                self.scene().addItem(handle)
                self._handles.append(handle)
        finally:
            self._updating = False

    def _handle_moved(self, handle: _PointHandle) -> None:
        if self._updating:
            return
        self.pointsChanged.emit(self.points_px())

    def _refine(self, x_px: float, y_px: float) -> PixelPoint:
        gray = self._gray
        if gray is None:
            return PixelPoint(x_px, y_px)
        rx, ry = refine_corner_subpixel(gray, x_px, y_px)
        return PixelPoint(rx, ry)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._begin_pan(event):
            return
        if (
            event.button() != Qt.MouseButton.LeftButton
            or self._required_points <= 0
            or self.pixmap_item.pixmap().isNull()
        ):
            super().mousePressEvent(event)
            return

        item = self.itemAt(event.position().toPoint())
        if isinstance(item, (_PointHandle, QGraphicsSimpleTextItem)):
            super().mousePressEvent(event)
            return

        scene_position = self.mapToScene(event.position().toPoint())
        image_rect = self.pixmap_item.boundingRect()
        if not image_rect.contains(scene_position):
            super().mousePressEvent(event)
            return

        points = list(self.points_px())
        if len(points) >= self._required_points:
            points = []
        points.append(self._refine(float(scene_position.x()), float(scene_position.y())))
        self.set_points(points)
        event.accept()
