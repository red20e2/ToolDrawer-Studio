from __future__ import annotations

import cv2
import numpy as np

from tooldrawer_studio.calibration.service import PixelPoint, pixel_to_mm
from tooldrawer_studio.capture.image_loader import LoadedImage
from tooldrawer_studio.domain.models import CalibrationRecord
from tooldrawer_studio.geometry.contour import (
    polygon_area_mm2,
    simplify_closed_contour,
    smooth_closed_contour,
)
from tooldrawer_studio.image_analysis import contour_contrast, foreground_mask
from tooldrawer_studio.tracing.models import TraceCandidate, TraceConfig


def _touches_image_border(vertices: np.ndarray, width: int, height: int) -> bool:
    return bool(
        np.any(vertices[:, 0] <= 0)
        or np.any(vertices[:, 1] <= 0)
        or np.any(vertices[:, 0] >= width - 1)
        or np.any(vertices[:, 1] >= height - 1)
    )


def _compactness(area_mm2: float, points) -> float:
    if len(points) < 3 or area_mm2 <= 0:
        return 0.0
    perimeter = 0.0
    for current, following in zip(points, points[1:] + points[:1]):
        dx = following.x_mm - current.x_mm
        dy = following.y_mm - current.y_mm
        perimeter += (dx * dx + dy * dy) ** 0.5
    if perimeter <= 1e-9:
        return 0.0
    return float(min(1.0, (4.0 * 3.141592653589793 * area_mm2) / (perimeter * perimeter)))


class OpenCVTracer:
    def trace(
        self,
        image: LoadedImage,
        calibration: CalibrationRecord,
        config: TraceConfig = TraceConfig(),
    ) -> list[TraceCandidate]:
        if config.min_area_mm2 <= 0:
            raise ValueError("min_area_mm2 must be positive")
        if config.simplify_mm < 0:
            raise ValueError("simplify_mm must be non-negative")
        if calibration.capture_id != image.asset.id:
            raise ValueError("Calibration does not belong to this capture")

        mask = foreground_mask(image.pixels_bgr)
        gray = cv2.cvtColor(image.pixels_bgr, cv2.COLOR_BGR2GRAY)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        height, width = mask.shape[:2]
        candidates: list[TraceCandidate] = []
        for contour in contours:
            pixel_vertices = contour.reshape(-1, 2)
            if len(pixel_vertices) < 3:
                continue
            mm_points = [
                pixel_to_mm(
                    calibration,
                    PixelPoint(float(vertex[0]), float(vertex[1])),
                )
                for vertex in pixel_vertices
            ]
            area_mm2 = polygon_area_mm2(mm_points)
            if area_mm2 < config.min_area_mm2:
                continue
            simplified = simplify_closed_contour(mm_points, config.simplify_mm)
            simplified = smooth_closed_contour(simplified, config.simplify_mm)
            touches_border = _touches_image_border(pixel_vertices, width, height)
            contrast = contour_contrast(gray, contour)
            compactness = _compactness(area_mm2, simplified)
            confidence = 1.0
            if touches_border:
                confidence -= 0.35
            if len(simplified) < 4:
                confidence -= 0.15
            if contrast < 30.0:
                confidence -= 0.20
            elif contrast < 50.0:
                confidence -= 0.08
            if compactness < 0.12:
                confidence -= 0.10
            if len(simplified) < max(4, int(0.08 * len(mm_points))) and len(mm_points) > 40:
                confidence -= 0.05
            confidence = max(0.0, min(1.0, confidence))
            candidates.append(
                TraceCandidate(
                    base_contour_mm=simplified,
                    confidence=confidence,
                    area_mm2=area_mm2,
                )
            )
        candidates.sort(key=lambda candidate: candidate.area_mm2, reverse=True)
        return candidates
