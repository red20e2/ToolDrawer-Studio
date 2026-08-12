from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from tooldrawer_studio.calibration.service import PixelPoint


class CalibrationImageView(QGraphicsView):
    pointsChanged = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = self._scene.addPixmap(QPixmap())
        self._pixmap_item.setZValue(0.0)
        self._overlay_group: QGraphicsItemGroup | None = None
        self._points: list[PixelPoint] = []
        self._required_points = 0
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def set_image_bytes(self, raw: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(raw):
            raise ValueError("Unsupported or invalid image data")
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(QPixmap(pixmap).rect())
        self.clear_points()
        self._fit_image()

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

    def _fit_image(self) -> None:
        pixmap = self._pixmap_item.pixmap()
        if pixmap.isNull():
            return
        self.fitInView(self._pixmap_item.boundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_image()

    def mousePressEvent(self, event: QMouseEvent) -> None:
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
