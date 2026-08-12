from __future__ import annotations

from dataclasses import dataclass


MIN_AUTOMATIC_THICKNESS_CONFIDENCE = 0.80


@dataclass(frozen=True, slots=True)
class ImagePoint:
    x_px: float
    y_px: float


@dataclass(frozen=True, slots=True)
class ThicknessMeasurementResult:
    automatic_thickness_mm: float
    confidence: float
    endpoint_a_px: ImagePoint
    endpoint_b_px: ImagePoint
    silhouette_px: tuple[ImagePoint, ...]
    warnings: tuple[str, ...] = ()
