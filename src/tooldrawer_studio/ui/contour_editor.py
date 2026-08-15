from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainterPath,
    QPen,
    QPixmap,
    QUndoCommand,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.domain.models import CalibrationRecord, Point2D, ToolObject
from tooldrawer_studio.geometry.contour import (
    nearest_segment_index,
    offset_contour_mm,
    simplify_closed_contour,
    smooth_closed_contour,
    validate_contour,
)
from tooldrawer_studio.image_analysis import (
    canny_edge_points_mm,
    snap_point_to_edges_mm,
    warp_pixels_to_mm,
)
from tooldrawer_studio.ui.image_view import ZoomableImageView


class _ContourCommand(QUndoCommand):
    def __init__(
        self, editor: "ContourEditor", before: list[Point2D], after: list[Point2D], text: str
    ) -> None:
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
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setBrush(editor.palette().highlight())
        self.setZValue(20)

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
                snap=not bool(event.modifiers() & Qt.KeyboardModifier.AltModifier),
            )


class _ContourCanvas(ZoomableImageView):
    edgeClicked = Signal(QPointF)
    deleteRequested = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._begin_pan(event):
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, _VertexHandle):
            super().mousePressEvent(event)
            return
        self.edgeClicked.emit(self.mapToScene(event.position().toPoint()))
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            self.deleteRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ContourEditor(QWidget):
    contourChanged = Signal(list)
    coordinateChanged = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tool: ToolObject | None = None
        self._contour: list[Point2D] = []
        self._base_contour: list[Point2D] = []
        self._clearance_mm = 0.6
        self._calibration: CalibrationRecord | None = None
        self._edge_points_mm: np.ndarray = np.empty((0, 2), dtype=np.float64)
        self._overlay_items: list[QGraphicsItem] = []
        self.undo_stack = QUndoStack(self)
        self.view = _ContourCanvas(self)
        self.view.setObjectName("imageWell")
        self.scene = self.view.scene()
        self.view.edgeClicked.connect(self._edge_clicked)
        self.view.deleteRequested.connect(self._delete_selected_vertices)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        toggles = QHBoxLayout()
        self.show_photo = QCheckBox("Photo")
        self.show_base = QCheckBox("Base trace")
        self.show_edited = QCheckBox("Edited contour")
        self.show_clearance = QCheckBox("Clearance")
        self.show_photo.setChecked(True)
        self.show_base.setChecked(True)
        self.show_edited.setChecked(True)
        self.show_clearance.setChecked(False)
        for box in (self.show_photo, self.show_base, self.show_edited, self.show_clearance):
            box.toggled.connect(lambda _checked=False: self._redraw())
            toggles.addWidget(box)
        toggles.addStretch()
        layout.addLayout(toggles)
        layout.addWidget(self.view)

        actions = QHBoxLayout()
        smooth_button = QPushButton("Smooth")
        simplify_button = QPushButton("Simplify")
        fit_button = QPushButton("Fit")
        zoom_button = QPushButton("1:1")
        smooth_button.clicked.connect(self.smooth_contour)
        simplify_button.clicked.connect(self.simplify_contour)
        fit_button.clicked.connect(self.view.fit_image)
        zoom_button.clicked.connect(self.view.zoom_1_to_1)
        actions.addWidget(smooth_button)
        actions.addWidget(simplify_button)
        actions.addWidget(fit_button)
        actions.addWidget(zoom_button)
        actions.addStretch()
        layout.addLayout(actions)

    def set_tool(
        self,
        tool: ToolObject,
        *,
        pixels_bgr: np.ndarray | None = None,
        calibration: CalibrationRecord | None = None,
    ) -> None:
        self._tool = tool
        self._base_contour = list(tool.base_contour_mm)
        self._contour = list(tool.contour_mm)
        self._clearance_mm = float(tool.clearance_mm)
        self._calibration = calibration
        validate_contour(self._base_contour)
        validate_contour(self._contour)
        self.undo_stack.clear()
        self._edge_points_mm = np.empty((0, 2), dtype=np.float64)
        if pixels_bgr is not None and calibration is not None:
            warped, origin_x, origin_y, pixels_per_mm = warp_pixels_to_mm(
                pixels_bgr, calibration
            )
            pixmap = _bgr_to_pixmap(warped)
            self.view.set_scene_image(
                pixmap,
                x=origin_x,
                y=origin_y,
                scale=1.0 / pixels_per_mm,
                visible=self.show_photo.isChecked(),
            )
            self._edge_points_mm = canny_edge_points_mm(pixels_bgr, calibration)
        else:
            self.view.set_scene_image(QPixmap(), visible=False)
        self._redraw()

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
            self.undo_stack.push(
                _ContourCommand(self, self._contour, self._base_contour, "Reset contour")
            )

    def simplify_contour(self) -> None:
        if not self._contour:
            return
        after = simplify_closed_contour(self._contour, 0.25)
        if after != self._contour:
            self.undo_stack.push(_ContourCommand(self, self._contour, after, "Simplify contour"))

    def smooth_contour(self) -> None:
        if not self._contour:
            return
        after = smooth_closed_contour(self._contour, 0.25)
        if after != self._contour:
            self.undo_stack.push(_ContourCommand(self, self._contour, after, "Smooth contour"))

    def _edge_clicked(self, scene_pos: QPointF) -> None:
        if not self._contour:
            return
        point = Point2D(float(scene_pos.x()), float(scene_pos.y()))
        index, nearest, distance = nearest_segment_index(point, self._contour)
        if distance > 2.0:
            return
        try:
            self.insert_vertex(index, nearest)
        except ValueError:
            return

    def _delete_selected_vertices(self) -> None:
        selected = [
            item._index
            for item in self.scene.selectedItems()
            if isinstance(item, _VertexHandle)
        ]
        if not selected:
            return
        after = [
            point
            for index, point in enumerate(self._contour)
            if index not in set(selected)
        ]
        if len(after) < 4:
            return
        try:
            validate_contour(after)
        except ValueError:
            return
        self.undo_stack.push(_ContourCommand(self, self._contour, after, "Delete vertex"))

    def _commit_vertex_move(
        self,
        index: int,
        previous: Point2D,
        current: Point2D,
        *,
        snap: bool = True,
    ) -> None:
        if not 0 <= index < len(self._contour):
            self._redraw()
            return
        snapped = current
        if snap:
            snapped = snap_point_to_edges_mm(current, self._edge_points_mm)
        before = list(self._contour)
        before[index] = previous
        after = list(before)
        after[index] = snapped
        try:
            validate_contour(after)
        except ValueError:
            self._redraw()
            return
        self.undo_stack.push(_ContourCommand(self, before, after, "Move vertex"))
        self.coordinateChanged.emit(snapped.x_mm, snapped.y_mm)

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

    def _clear_overlays(self) -> None:
        for item in self._overlay_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self._overlay_items.clear()

    def _redraw(self) -> None:
        self._clear_overlays()
        self.view.set_pixmap_visible(self.show_photo.isChecked())

        if self.show_base.isChecked() and self._base_contour:
            base_item = QGraphicsPathItem(self._path(self._base_contour))
            base_pen = QPen(self.palette().mid().color())
            base_pen.setStyle(Qt.PenStyle.DashLine)
            base_item.setPen(base_pen)
            base_item.setZValue(5)
            self.scene.addItem(base_item)
            self._overlay_items.append(base_item)

        if self.show_clearance.isChecked() and self._contour and self._clearance_mm > 0:
            for outline in offset_contour_mm(self._contour, self._clearance_mm):
                clearance_item = QGraphicsPathItem(self._path(outline))
                clearance_pen = QPen(self.palette().link().color())
                clearance_pen.setStyle(Qt.PenStyle.DotLine)
                clearance_item.setPen(clearance_pen)
                clearance_item.setZValue(6)
                self.scene.addItem(clearance_item)
                self._overlay_items.append(clearance_item)

        if self.show_edited.isChecked() and self._contour:
            edit_item = QGraphicsPathItem(self._path(self._contour))
            edit_item.setPen(QPen(self.palette().highlight().color()))
            edit_item.setZValue(10)
            self.scene.addItem(edit_item)
            self._overlay_items.append(edit_item)
            for index, point in enumerate(self._contour):
                handle = _VertexHandle(self, index, point)
                self.scene.addItem(handle)
                self._overlay_items.append(handle)

        rect = self.scene.itemsBoundingRect()
        if not rect.isNull():
            self.scene.setSceneRect(rect.adjusted(-8, -8, 8, 8))


def _bgr_to_pixmap(pixels_bgr: np.ndarray) -> QPixmap:
    rgb = pixels_bgr[:, :, ::-1].copy()
    height, width, _channels = rgb.shape
    image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image.copy())
