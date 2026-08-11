from __future__ import annotations

from dataclasses import dataclass, field


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
    depth_mm: float = 5.0
    trace_confidence: float = 0.0


@dataclass(slots=True)
class Project:
    id: str
    name: str
    schema_version: int = 1
    captures: list[CaptureAsset] = field(default_factory=list)
    calibrations: list[CalibrationRecord] = field(default_factory=list)
    tools: list[ToolObject] = field(default_factory=list)
