from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tooldrawer_studio.generation.models import GenerationSettings, GenerationState
from tooldrawer_studio.measurement.models import ImagePoint

if TYPE_CHECKING:
    from tooldrawer_studio.layout.models import LayoutState


@dataclass(frozen=True, slots=True)
class Point2D:
    x_mm: float
    y_mm: float


@dataclass(slots=True)
class CaptureAsset:
    id: str
    filename: str
    width_px: int
    height_px: int
    archive_path: str


@dataclass(slots=True)
class CalibrationRecord:
    id: str
    capture_id: str
    method: str
    matrix_3x3: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    residual_mm: float
    confidence: float


@dataclass(slots=True)
class ToolObject:
    id: str
    name: str
    source_capture_id: str
    base_contour_mm: list[Point2D]
    contour_mm: list[Point2D]
    clearance_mm: float = 0.6
    trace_confidence: float = 0.0
    side_view_capture_id: str | None = None
    automatic_thickness_mm: float | None = None
    automatic_thickness_confidence: float | None = None
    automatic_thickness_endpoint_a_px: ImagePoint | None = None
    automatic_thickness_endpoint_b_px: ImagePoint | None = None
    corrected_thickness_endpoint_a_px: ImagePoint | None = None
    corrected_thickness_endpoint_b_px: ImagePoint | None = None
    side_view_silhouette_px: list[ImagePoint] = field(default_factory=list)
    accepted_thickness_mm: float | None = None
    thickness_measurement_mode: str = "none"
    thickness_accepted: bool = False
    exposed_height_override_mm: float | None = None
    bottom_clearance_override_mm: float | None = None
    pocket_depth_override_mm: float | None = None
    thickness_review_required: bool = False


@dataclass(slots=True)
class Project:
    id: str
    name: str
    schema_version: int = 4
    captures: list[CaptureAsset] = field(default_factory=list)
    calibrations: list[CalibrationRecord] = field(default_factory=list)
    tools: list[ToolObject] = field(default_factory=list)
    default_exposed_height_mm: float = 4.0
    default_bottom_clearance_mm: float = 0.8
    default_layout_spacing_mm: float = 3.0
    default_layout_border_mm: float = 4.0
    default_grab_clearance_mm: float = 12.0
    default_snap_increment_mm: float = 1.0
    gridfinity_pitch_mm: float = 42.0
    layout: LayoutState | None = None
    generation_settings: GenerationSettings = field(default_factory=GenerationSettings)
    generation_state: GenerationState = field(default_factory=GenerationState)
