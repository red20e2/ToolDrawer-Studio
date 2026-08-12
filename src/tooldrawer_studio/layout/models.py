from __future__ import annotations

from dataclasses import dataclass, field
import math

_LAYOUT_MODES = frozenset({"foam", "gridfinity"})
_ROTATION_POLICIES = frozenset({"free", "orthogonal", "fixed"})
_GRAB_SIDES = frozenset({"none", "left", "right", "top", "bottom"})


def _finite(value: float, label: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric


def _positive(value: float, label: str) -> float:
    numeric = _finite(value, label)
    if numeric <= 0.0:
        raise ValueError(f"{label} must be greater than zero")
    return numeric


def _nonnegative(value: float, label: str) -> float:
    numeric = _finite(value, label)
    if numeric < 0.0:
        raise ValueError(f"{label} must not be negative")
    return numeric


@dataclass(slots=True)
class ToolPlacement:
    tool_id: str
    x_mm: float = 0.0
    y_mm: float = 0.0
    rotation_deg: float = 0.0
    locked: bool = False
    rotation_policy: str = "free"
    grab_side: str = "none"
    grab_clearance_override_mm: float | None = None
    is_placed: bool = False

    def __post_init__(self) -> None:
        self.tool_id = str(self.tool_id)
        if not self.tool_id:
            raise ValueError("Tool placement requires a tool id")
        self.x_mm = _finite(self.x_mm, "x_mm")
        self.y_mm = _finite(self.y_mm, "y_mm")
        self.rotation_deg = _finite(self.rotation_deg, "rotation_deg") % 360.0
        self.rotation_policy = str(self.rotation_policy)
        if self.rotation_policy not in _ROTATION_POLICIES:
            raise ValueError(f"Invalid rotation policy: {self.rotation_policy}")
        self.grab_side = str(self.grab_side)
        if self.grab_side not in _GRAB_SIDES:
            raise ValueError(f"Invalid grab side: {self.grab_side}")
        if self.grab_clearance_override_mm is not None:
            self.grab_clearance_override_mm = _nonnegative(
                self.grab_clearance_override_mm, "grab_clearance_override_mm"
            )
        self.locked = bool(self.locked)
        self.is_placed = bool(self.is_placed)


@dataclass(slots=True)
class LayoutState:
    mode: str
    foam_width_mm: float | None = None
    foam_height_mm: float | None = None
    grid_columns: int | None = None
    grid_rows: int | None = None
    grid_pitch_mm: float = 42.0
    spacing_mm: float = 3.0
    border_mm: float = 4.0
    grab_clearance_mm: float = 12.0
    snap_enabled: bool = False
    snap_increment_mm: float = 1.0
    placements: list[ToolPlacement] = field(default_factory=list)
    unplaced_tool_ids: list[str] = field(default_factory=list)
    review_required: bool = False

    def __post_init__(self) -> None:
        self.mode = str(self.mode)
        if self.mode not in _LAYOUT_MODES:
            raise ValueError(f"Invalid layout mode: {self.mode}")

        self.grid_pitch_mm = _positive(self.grid_pitch_mm, "grid_pitch_mm")
        self.spacing_mm = _nonnegative(self.spacing_mm, "spacing_mm")
        self.border_mm = _nonnegative(self.border_mm, "border_mm")
        self.grab_clearance_mm = _nonnegative(
            self.grab_clearance_mm, "grab_clearance_mm"
        )
        self.snap_increment_mm = _positive(
            self.snap_increment_mm, "snap_increment_mm"
        )
        self.snap_enabled = bool(self.snap_enabled)
        self.review_required = bool(self.review_required)

        if self.mode == "foam":
            if self.foam_width_mm is None or self.foam_height_mm is None:
                raise ValueError("Foam layout requires width and height")
            self.foam_width_mm = _positive(self.foam_width_mm, "foam_width_mm")
            self.foam_height_mm = _positive(self.foam_height_mm, "foam_height_mm")
            self.grid_columns = None
            self.grid_rows = None
        else:
            if self.grid_columns is None or self.grid_rows is None:
                raise ValueError("Gridfinity layout requires columns and rows")
            self.grid_columns = int(self.grid_columns)
            self.grid_rows = int(self.grid_rows)
            if self.grid_columns <= 0 or self.grid_rows <= 0:
                raise ValueError("Gridfinity columns and rows must be greater than zero")
            self.foam_width_mm = None
            self.foam_height_mm = None

        placement_ids = [placement.tool_id for placement in self.placements]
        if len(placement_ids) != len(set(placement_ids)):
            raise ValueError("Duplicate tool placement")

        self.unplaced_tool_ids = [str(tool_id) for tool_id in self.unplaced_tool_ids]
        if len(self.unplaced_tool_ids) != len(set(self.unplaced_tool_ids)):
            raise ValueError("Duplicate unplaced tool id")

    @property
    def width_mm(self) -> float:
        if self.mode == "gridfinity":
            assert self.grid_columns is not None
            return float(self.grid_columns) * self.grid_pitch_mm
        assert self.foam_width_mm is not None
        return self.foam_width_mm

    @property
    def height_mm(self) -> float:
        if self.mode == "gridfinity":
            assert self.grid_rows is not None
            return float(self.grid_rows) * self.grid_pitch_mm
        assert self.foam_height_mm is not None
        return self.foam_height_mm

    def placement_for(self, tool_id: str) -> ToolPlacement | None:
        return next(
            (placement for placement in self.placements if placement.tool_id == tool_id),
            None,
        )
