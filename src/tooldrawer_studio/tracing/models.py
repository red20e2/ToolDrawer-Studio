from __future__ import annotations

from dataclasses import dataclass

from tooldrawer_studio.domain.models import Point2D


@dataclass(frozen=True, slots=True)
class TraceConfig:
    min_area_mm2: float = 100.0
    simplify_mm: float = 0.25


@dataclass(slots=True)
class TraceCandidate:
    base_contour_mm: list[Point2D]
    confidence: float
    area_mm2: float
