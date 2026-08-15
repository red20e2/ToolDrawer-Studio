from __future__ import annotations

import weakref

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainterPath, QPen, QPixmap, QTransform, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.domain.models import CalibrationRecord, Point2D, ToolObject
from tooldrawer_studio.geometry.contour import validate_contour


class _ContourCommand(QUndoCommand):
    def __init__(self, editor: "ContourEditor", before: list[Point2D], after: list[Point2D], text: str) -> None:
        super().__init__(text)
        self._editor = editor
        self._before = list(before)
        self._after = list(after)

    def undo(self) -> None:
        self._editor._apply_contour(self._before)

    def redo(self) -> None:
        self._editor._apply_contour(self._after)


class _VertexHandle(QGraphicsEllipseItem):
    def __init__(self, editor: "ContourEditor", index: int, point: Point2D) -> None:
        super().__init__(-2.5, -2.5, 5.0, 5.0)
        self._editor = editor
        self._index = index
        self._press_position = QPointF(point.x_mm, point.y_mm)
        self.setPos(point.x_mm, point.y_mm)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setBrush(editor.palette().highlight())

    def mousePressEvent(self, event) -> None:
        self._press_position = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        released = self.pos()
        if released != self._press_position:
            self._editor._commit_vertex_move(
                self._index,
                Point2D(self._press_position.x(), self._press_position.y()),
                Point2D(released.x(), released.y()),
            )


class ContourEditor(QWidget):
    contourChanged = Signal(list)
    coordinateChanged = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tool: ToolObject | None = None
        self._contour: list[Point2D] = []
        self._base_contour: list[Point2D] = []
        self._source_pixmap: QPixmap | None = None
        self._source_pixmap_capture_id: str | None = None
        self._source_pixmap_controller_ref: weakref.ReferenceType[object] | None = None
        self._calibration: CalibrationRecord | None = None
        self.undo_stack = QUndoStack(self)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

    def set_tool(
        self,
        tool: ToolObject,
        *,
        image_bytes: bytes | None = None,
        calibration: CalibrationRecord | None = None,
    ) -> None:
        self._tool = tool
        self._base_contour = list(tool.base_contour_mm)
        self._contour = list(tool.contour_mm)
        validate_contour(self._base_contour)
        validate_contour(self._contour)
        source_controller = getattr(self.window(), "controller", None)
        cached_controller = (
            self._source_pixmap_controller_ref()
            if self._source_pixmap_controller_ref is not None
            else None
        )
        same_source_controller = (
            source_controller is None
            and self._source_pixmap_controller_ref is None
        ) or (
            cached_controller is not None
            and cached_controller is source_controller
        )
        reuse_source_pixmap = (
            image_bytes is None
            and self._source_pixmap is not None
            and self._source_pixmap_capture_id == tool.source_capture_id
            and same_source_controller
        )
        image_bytes, calibration = self._resolve_source_context(
            tool,
            image_bytes,
            calibration,
            resolve_image=not reuse_source_pixmap,
        )
        if not reuse_source_pixmap:
            self._source_pixmap = None
            self._source_pixmap_capture_id = None
            self._source_pixmap_controller_ref = None
            if image_bytes is not None:
                pixmap = QPixmap()
                if not pixmap.loadFromData(image_bytes):
                    raise ValueError(
                        "Could not decode the source image for contour editing"
                    )
                self._source_pixmap = pixmap
                self._source_pixmap_capture_id = tool.source_capture_id
                if source_controller is not None:
                    self._source_pixmap_controller_ref = weakref.ref(source_controller)
        self._calibration = calibration
        self.undo_stack.clear()
        self._redraw()
        self.fit_to_tool()

    def _resolve_source_context(
        self,
        tool: ToolObject,
        image_bytes: bytes | None,
        calibration: CalibrationRecord | None,
        *,
        resolve_image: bool = True,
    ) -> tuple[bytes | None, CalibrationRecord | None]:
        if image_bytes is not None and calibration is not None:
            return image_bytes, calibration
        host = self.window()
        controller = getattr(host, "controller", None)
        if controller is None:
            return image_bytes, calibration
        if image_bytes is None and resolve_image:
            try:
                image_bytes = controller.capture_display_bytes(tool.source_capture_id)
            except (KeyError, ValueError):
                image_bytes = None
        if calibration is None:
            try:
                calibration = controller.calibration_for_capture(tool.source_capture_id)
            except (KeyError, ValueError):
                calibration = None
        return image_bytes, calibration

    def contour(self) -> list[Point2D]:
        return list(self._contour)

    def insert_vertex(self, segment_index: int, point: Point2D) -> None:
        if not self._contour:
            raise ValueError("No contour is loaded")
        if not 0 <= segment_index < len(self._contour):
            raise IndexError("Segment index is out of range")
        after = list(self._contour)
        after.insert(segment_index + 1, point)
        validate_contour(after)
        self.undo_stack.push(_ContourCommand(self, self._contour, after, "Insert vertex"))

    def delete_vertex(self, vertex_index: int) -> None:
        if len(self._contour) <= 4:
            raise ValueError("At least four contour vertices must remain")
        if not 0 <= vertex_index < len(self._contour):
            raise IndexError("Vertex index is out of range")
        after = list(self._contour)
        del after[vertex_index]
        validate_contour(after)
        self.undo_stack.push(_ContourCommand(self, self._contour, after, "Delete vertex"))

    def reset_to_base(self) -> None:
        if self._base_contour:
            self.undo_stack.push(_ContourCommand(self, self._contour, self._base_contour, "Reset contour"))

    def fit_to_tool(self) -> None:
        if not self._contour:
            return
        bounds = self._path(self._contour).boundingRect()
        largest = max(bounds.width(), bounds.height())
        margin = max(5.0, largest * 0.10)
        target = bounds.adjusted(-margin, -margin, margin, margin)
        self.view.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)

    def _commit_vertex_move(self, index: int, previous: Point2D, current: Point2D) -> None:
        if not 0 <= index < len(self._contour):
            self._redraw()
            return
        before = list(self._contour)
        before[index] = previous
        after = list(before)
        after[index] = current
        try:
            validate_contour(after)
        except ValueError:
            self._redraw()
            return
        self.undo_stack.push(_ContourCommand(self, before, after, "Move vertex"))
        self.coordinateChanged.emit(current.x_mm, current.y_mm)

    def _apply_contour(self, points: list[Point2D]) -> None:
        validate_contour(points)
        self._contour = list(points)
        self._redraw()
        self.contourChanged.emit(list(self._contour))

    @staticmethod
    def _path(points: list[Point2D]) -> QPainterPath:
        path = QPainterPath()
        if not points:
            return path
        path.moveTo(points[0].x_mm, points[0].y_mm)
        for point in points[1:]:
            path.lineTo(point.x_mm, point.y_mm)
        path.closeSubpath()
        return path

    @staticmethod
    def _pixel_to_mm_transform(record: CalibrationRecord) -> QTransform:
        matrix = record.matrix_3x3
        return QTransform(
            matrix[0][0],
            matrix[1][0],
            matrix[2][0],
            matrix[0][1],
            matrix[1][1],
            matrix[2][1],
            matrix[0][2],
            matrix[1][2],
            matrix[2][2],
        )

    def _redraw(self) -> None:
        self.scene.clear()

        if self._source_pixmap is not None and self._calibration is not None:
            image_item = QGraphicsPixmapItem(self._source_pixmap)
            image_item.setTransform(self._pixel_to_mm_transform(self._calibration))
            image_item.setZValue(-10)
            self.scene.addItem(image_item)

        base_item = QGraphicsPathItem(self._path(self._base_contour))
        base_pen = QPen(self.palette().mid().color())
        base_pen.setStyle(Qt.PenStyle.DashLine)
        base_pen.setWidthF(1.5)
        base_pen.setCosmetic(True)
        base_item.setPen(base_pen)
        base_item.setZValue(0)
        self.scene.addItem(base_item)

        edit_item = QGraphicsPathItem(self._path(self._contour))
        edit_pen = QPen(self.palette().highlight().color())
        edit_pen.setWidthF(2.0)
        edit_pen.setCosmetic(True)
        edit_item.setPen(edit_pen)
        edit_item.setZValue(1)
        self.scene.addItem(edit_item)

        for index, point in enumerate(self._contour):
            handle = _VertexHandle(self, index, point)
            handle.setZValue(2)
            self.scene.addItem(handle)
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
