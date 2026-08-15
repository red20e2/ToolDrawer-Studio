from __future__ import annotations

from dataclasses import replace
import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainterPath, QPen, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.layout.geometry import (
    candidate_exclusion_geometry,
    oriented_cavity_polygon,
)
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.layout.validation import LayoutValidationResult


class _PlacementCommand(QUndoCommand):
    def __init__(
        self,
        owner: "ArrangementView",
        before: dict[str, ToolPlacement],
        after: dict[str, ToolPlacement],
        tool_ids: tuple[str, ...],
        text: str,
    ) -> None:
        super().__init__(text)
        self._owner = owner
        self._before = {key: replace(value) for key, value in before.items()}
        self._after = {key: replace(value) for key, value in after.items()}
        self._tool_ids = tool_ids

    def undo(self) -> None:
        self._owner._apply_snapshot(self._before, self._tool_ids)

    def redo(self) -> None:
        self._owner._apply_snapshot(self._after, self._tool_ids)


class _ToolItem(QGraphicsPathItem):
    def __init__(self, owner: "ArrangementView", tool_id: str, path: QPainterPath, locked: bool) -> None:
        super().__init__(path)
        self._owner = owner
        self.tool_id = tool_id
        self._press_position = QPointF()
        flags = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        if not locked:
            flags |= QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        self.setFlags(flags)

    def mousePressEvent(self, event) -> None:
        self._press_position = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        released = self.pos()
        delta = released - self._press_position
        if delta.manhattanLength() <= 1e-9:
            return
        selected = self._owner.selected_tool_ids()
        if self.tool_id not in selected:
            selected = {self.tool_id}
        self.setPos(self._press_position)
        try:
            self._owner.commit_translation(
                sorted(selected),
                float(delta.x()),
                float(-delta.y()),
            )
        except ValueError:
            self._owner._redraw()


class ArrangementView(QWidget):
    placementsCommitted = Signal(object)
    selectionChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setObjectName("imageWell")
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setRenderHints(self.view.renderHints())
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.undo_stack = QUndoStack(self)
        self._project: Project | None = None
        self._layout: LayoutState | None = None
        self._tools: dict[str, ToolObject] = {}
        self._placements: dict[str, ToolPlacement] = {}
        self._validation = LayoutValidationResult(True, ())
        self._selected_ids: set[str] = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.scene.selectionChanged.connect(self._scene_selection_changed)

    def set_project_layout(
        self,
        project: Project,
        layout: LayoutState,
        validation: LayoutValidationResult,
    ) -> None:
        self._project = project
        self._layout = layout
        self._tools = {tool.id: tool for tool in project.tools}
        self._placements = {
            placement.tool_id: replace(placement) for placement in layout.placements
        }
        self._validation = validation
        self._selected_ids.intersection_update(self._placements)
        self.undo_stack.clear()
        self._redraw()

    def placement(self, tool_id: str) -> ToolPlacement:
        try:
            return replace(self._placements[tool_id])
        except KeyError as exc:
            raise KeyError(f"Unknown layout placement: {tool_id}") from exc

    def selected_tool_ids(self) -> set[str]:
        return set(self._selected_ids)

    def set_selected_tool_ids(self, tool_ids: set[str]) -> None:
        self._selected_ids = {tool_id for tool_id in tool_ids if tool_id in self._placements}
        for item in self.scene.items():
            if isinstance(item, _ToolItem):
                item.setSelected(item.tool_id in self._selected_ids)
        self.selectionChanged.emit(set(self._selected_ids))

    def model_to_scene(self, x_mm: float, y_mm: float) -> QPointF:
        layout = self._require_layout()
        return QPointF(float(x_mm), float(layout.height_mm - y_mm))

    def scene_to_model(self, x_scene: float, y_scene: float) -> tuple[float, float]:
        layout = self._require_layout()
        return float(x_scene), float(layout.height_mm - y_scene)

    def _require_layout(self) -> LayoutState:
        if self._layout is None:
            raise ValueError("No arrangement is loaded")
        return self._layout

    def _scene_selection_changed(self) -> None:
        self._selected_ids = {
            item.tool_id
            for item in self.scene.selectedItems()
            if isinstance(item, _ToolItem)
        }
        self.selectionChanged.emit(set(self._selected_ids))

    def _snap_axis(self, value: float, axis: str, moving_ids: set[str]) -> float:
        layout = self._require_layout()
        if not layout.snap_enabled:
            return value
        increment = layout.snap_increment_mm
        snapped = round(value / increment) * increment
        candidates = [snapped]
        threshold = max(2.0, increment / 2.0)

        if axis == "x":
            candidates.extend((layout.border_mm, layout.width_mm - layout.border_mm))
            if layout.mode == "gridfinity":
                assert layout.grid_columns is not None
                candidates.extend(
                    index * layout.grid_pitch_mm
                    for index in range(layout.grid_columns + 1)
                )
            candidates.extend(
                placement.x_mm
                for tool_id, placement in self._placements.items()
                if tool_id not in moving_ids and placement.is_placed
            )
        else:
            candidates.extend((layout.border_mm, layout.height_mm - layout.border_mm))
            if layout.mode == "gridfinity":
                assert layout.grid_rows is not None
                candidates.extend(
                    index * layout.grid_pitch_mm
                    for index in range(layout.grid_rows + 1)
                )
            candidates.extend(
                placement.y_mm
                for tool_id, placement in self._placements.items()
                if tool_id not in moving_ids and placement.is_placed
            )

        nearby = [candidate for candidate in candidates if abs(candidate - value) <= threshold]
        if nearby:
            return min(nearby, key=lambda candidate: (abs(candidate - value), candidate))
        return snapped

    def commit_translation(self, tool_ids: list[str], dx_mm: float, dy_mm: float) -> None:
        if not tool_ids:
            return
        ids = tuple(dict.fromkeys(tool_ids))
        before = {tool_id: self.placement(tool_id) for tool_id in ids}
        for placement in before.values():
            if placement.locked:
                raise ValueError("Locked tools cannot be moved")

        first = before[ids[0]]
        moving = set(ids)
        desired_x = first.x_mm + float(dx_mm)
        desired_y = first.y_mm + float(dy_mm)
        snapped_x = self._snap_axis(desired_x, "x", moving)
        snapped_y = self._snap_axis(desired_y, "y", moving)
        actual_dx = snapped_x - first.x_mm
        actual_dy = snapped_y - first.y_mm

        after = {
            tool_id: replace(
                placement,
                x_mm=placement.x_mm + actual_dx,
                y_mm=placement.y_mm + actual_dy,
                is_placed=True,
            )
            for tool_id, placement in before.items()
        }
        self.undo_stack.push(
            _PlacementCommand(self, before, after, ids, "Move arranged tool")
        )

    @staticmethod
    def _orthogonal_angle(value: float) -> float:
        normalized = value % 360.0
        return float(int((normalized + 45.0) // 90.0) * 90 % 360)

    def commit_rotation(self, tool_ids: list[str], rotation_deg: float) -> None:
        if not tool_ids:
            return
        ids = tuple(dict.fromkeys(tool_ids))
        before = {tool_id: self.placement(tool_id) for tool_id in ids}
        for placement in before.values():
            if placement.locked:
                raise ValueError("Locked tools cannot be rotated")
            if placement.rotation_policy == "fixed":
                raise ValueError("Tool rotation is fixed")

        requested = float(rotation_deg) % 360.0
        primary = before[ids[0]]
        target_primary = (
            self._orthogonal_angle(requested)
            if primary.rotation_policy == "orthogonal"
            else requested
        )
        delta = math.radians(target_primary - primary.rotation_deg)
        center_x = sum(item.x_mm for item in before.values()) / len(before)
        center_y = sum(item.y_mm for item in before.values()) / len(before)
        cos_a = math.cos(delta)
        sin_a = math.sin(delta)
        after: dict[str, ToolPlacement] = {}
        for tool_id, placement in before.items():
            rel_x = placement.x_mm - center_x
            rel_y = placement.y_mm - center_y
            next_rotation = (placement.rotation_deg + math.degrees(delta)) % 360.0
            if placement.rotation_policy == "orthogonal":
                next_rotation = self._orthogonal_angle(next_rotation)
            after[tool_id] = replace(
                placement,
                x_mm=center_x + rel_x * cos_a - rel_y * sin_a,
                y_mm=center_y + rel_x * sin_a + rel_y * cos_a,
                rotation_deg=next_rotation,
                is_placed=True,
            )
        self.undo_stack.push(
            _PlacementCommand(self, before, after, ids, "Rotate arranged tool")
        )

    def _apply_snapshot(
        self,
        snapshot: dict[str, ToolPlacement],
        tool_ids: tuple[str, ...],
    ) -> None:
        for tool_id, placement in snapshot.items():
            self._placements[tool_id] = replace(placement)
        self._selected_ids = set(tool_ids)
        self._redraw()
        self.placementsCommitted.emit(
            [
                (
                    tool_id,
                    self._placements[tool_id].x_mm,
                    self._placements[tool_id].y_mm,
                    self._placements[tool_id].rotation_deg,
                )
                for tool_id in tool_ids
            ]
        )

    @staticmethod
    def _polygon_path(owner: "ArrangementView", polygon) -> QPainterPath:
        path = QPainterPath()
        coordinates = list(polygon.exterior.coords)
        if not coordinates:
            return path
        first = owner.model_to_scene(*coordinates[0])
        path.moveTo(first)
        for coordinate in coordinates[1:]:
            path.lineTo(owner.model_to_scene(*coordinate))
        path.closeSubpath()
        return path

    @classmethod
    def _geometry_path(cls, owner: "ArrangementView", geometry) -> QPainterPath:
        if hasattr(geometry, "exterior"):
            return cls._polygon_path(owner, geometry)
        path = QPainterPath()
        for part in getattr(geometry, "geoms", ()):
            path.addPath(cls._geometry_path(owner, part))
        return path

    def _redraw(self) -> None:
        selected = set(self._selected_ids)
        self.scene.blockSignals(True)
        self.scene.clear()
        layout = self._layout
        if layout is None:
            self.scene.blockSignals(False)
            return

        boundary_pen = QPen(self.palette().text().color())
        self.scene.addRect(0.0, 0.0, layout.width_mm, layout.height_mm, boundary_pen)
        usable_pen = QPen(self.palette().mid().color())
        usable_pen.setStyle(Qt.PenStyle.DashLine)
        self.scene.addRect(
            layout.border_mm,
            layout.border_mm,
            layout.width_mm - 2.0 * layout.border_mm,
            layout.height_mm - 2.0 * layout.border_mm,
            usable_pen,
        )

        if layout.mode == "gridfinity":
            guide_pen = QPen(self.palette().mid().color())
            guide_pen.setStyle(Qt.PenStyle.DotLine)
            assert layout.grid_columns is not None
            assert layout.grid_rows is not None
            for index in range(1, layout.grid_columns):
                x = index * layout.grid_pitch_mm
                self.scene.addLine(x, 0.0, x, layout.height_mm, guide_pen)
            for index in range(1, layout.grid_rows):
                model_y = index * layout.grid_pitch_mm
                scene_y = layout.height_mm - model_y
                self.scene.addLine(0.0, scene_y, layout.width_mm, scene_y, guide_pen)

        invalid_ids = {
            tool_id
            for issue in self._validation.issues
            for tool_id in issue.tool_ids
        }
        for tool_id, placement in self._placements.items():
            if not placement.is_placed:
                continue
            tool = self._tools.get(tool_id)
            if tool is None:
                continue

            if placement.grab_side != "none":
                grab_geometry = candidate_exclusion_geometry(
                    tool,
                    placement,
                    layout.spacing_mm,
                    layout.grab_clearance_mm,
                )
                grab_item = QGraphicsPathItem(
                    self._geometry_path(self, grab_geometry)
                )
                grab_pen = QPen(self.palette().mid().color())
                grab_pen.setStyle(Qt.PenStyle.DashLine)
                grab_item.setPen(grab_pen)
                grab_item.setToolTip(f"Grab access: {tool.name} [{tool_id}]")
                self.scene.addItem(grab_item)

            polygon = oriented_cavity_polygon(tool, placement)
            item = _ToolItem(
                self,
                tool_id,
                self._polygon_path(self, polygon),
                placement.locked,
            )
            item.setPen(
                QPen(
                    self.palette().brightText().color()
                    if tool_id in invalid_ids
                    else self.palette().highlight().color()
                )
            )
            item.setToolTip(
                f"{tool.name} | {placement.rotation_deg:.1f}°"
                + (" | locked" if placement.locked else "")
            )
            item.setSelected(tool_id in selected)
            self.scene.addItem(item)

        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        self.scene.blockSignals(False)
        self._selected_ids = selected
