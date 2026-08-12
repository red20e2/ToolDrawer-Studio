from __future__ import annotations

from dataclasses import dataclass, field

from tooldrawer_studio.measurement.models import ImagePoint


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
    schema_version: int = 2
    captures: list[CaptureAsset] = field(default_factory=list)
    calibrations: list[CalibrationRecord] = field(default_factory=list)
    tools: list[ToolObject] = field(default_factory=list)
    default_exposed_height_mm: float = 4.0
    default_bottom_clearance_mm: float = 0.8
