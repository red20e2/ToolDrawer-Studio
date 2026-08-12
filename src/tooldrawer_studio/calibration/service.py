from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from uuid import uuid4

import cv2
import numpy as np

from tooldrawer_studio.calibration.presets import PaperPreset
from tooldrawer_studio.domain.models import CalibrationRecord, Point2D


@dataclass(frozen=True, slots=True)
class PixelPoint:
    x_px: float
    y_px: float


def _matrix_tuple(matrix: np.ndarray) -> tuple[tuple[float, float, float], ...]:
    return tuple(tuple(float(value) for value in row) for row in matrix)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _known_distance_confidence(pixel_span: float) -> float:
    progress = _clamp01((pixel_span - 20.0) / 480.0)
    return 0.35 + (0.98 - 0.35) * progress


def _rectangle_confidence(source: np.ndarray) -> float:
    edges = [
        hypot(
            float(source[(index + 1) % 4, 0] - source[index, 0]),
            float(source[(index + 1) % 4, 1] - source[index, 1]),
        )
        for index in range(4)
    ]
    shortest_edge = min(edges)
    span_score = _clamp01((shortest_edge - 20.0) / 180.0)

    area = abs(float(cv2.contourArea(source.reshape((-1, 1, 2)))))
    width = float(np.ptp(source[:, 0]))
    height = float(np.ptp(source[:, 1]))
    bounding_area = width * height
    fill_score = _clamp01(area / bounding_area) if bounding_area > 1e-12 else 0.0
    return 0.35 + (0.98 - 0.35) * min(span_score, fill_score)


def _record(
    capture_id: str,
    method: str,
    matrix: np.ndarray,
    *,
    residual_mm: float = 0.0,
    confidence: float = 1.0,
) -> CalibrationRecord:
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError("Degenerate calibration transform")
    determinant = float(np.linalg.det(matrix))
    if abs(determinant) < 1e-12:
        raise ValueError("Degenerate calibration transform")
    return CalibrationRecord(
        id=str(uuid4()),
        capture_id=capture_id,
        method=method,
        matrix_3x3=_matrix_tuple(matrix),
        residual_mm=float(residual_mm),
        confidence=_clamp01(confidence),
    )


def calibrate_known_distance(
    capture_id: str,
    pixel_a: PixelPoint,
    pixel_b: PixelPoint,
    known_distance_mm: float,
) -> CalibrationRecord:
    if known_distance_mm <= 0:
        raise ValueError("Known distance must be positive")

    dx = float(pixel_b.x_px - pixel_a.x_px)
    dy = float(pixel_b.y_px - pixel_a.y_px)
    pixel_distance = hypot(dx, dy)
    if pixel_distance <= 1e-12:
        raise ValueError("Calibration points must be distinct")

    scale = known_distance_mm / pixel_distance
    cos_theta = dx / pixel_distance
    sin_theta = dy / pixel_distance
    ax = float(pixel_a.x_px)
    ay = float(pixel_a.y_px)

    matrix = np.array(
        [
            [
                scale * cos_theta,
                scale * sin_theta,
                -scale * (cos_theta * ax + sin_theta * ay),
            ],
            [
                -scale * sin_theta,
                scale * cos_theta,
                scale * (sin_theta * ax - cos_theta * ay),
            ],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    return _record(
        capture_id,
        "known_distance",
        matrix,
        confidence=_known_distance_confidence(pixel_distance),
    )


def _calibrate_rectangle_method(
    capture_id: str,
    corners_px: tuple[PixelPoint, PixelPoint, PixelPoint, PixelPoint],
    width_mm: float,
    height_mm: float,
    method: str,
) -> CalibrationRecord:
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("Rectangle dimensions must be positive")
    if len(corners_px) != 4:
        raise ValueError("Rectangle calibration requires four corners")

    source = np.array(
        [[point.x_px, point.y_px] for point in corners_px], dtype=np.float32
    )
    contour = source.reshape((-1, 1, 2))
    area = abs(float(cv2.contourArea(contour)))
    if area <= 1e-6:
        raise ValueError("Rectangle calibration points have near-zero area")
    if not cv2.isContourConvex(contour):
        raise ValueError("Rectangle calibration points must form a convex quadrilateral")

    destination = np.array(
        [[0.0, 0.0], [width_mm, 0.0], [width_mm, height_mm], [0.0, height_mm]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(source, destination).astype(np.float64)
    return _record(
        capture_id,
        method,
        matrix,
        confidence=_rectangle_confidence(source),
    )


def calibrate_rectangle(
    capture_id: str,
    corners_px: tuple[PixelPoint, PixelPoint, PixelPoint, PixelPoint],
    width_mm: float,
    height_mm: float,
) -> CalibrationRecord:
    return _calibrate_rectangle_method(
        capture_id, corners_px, width_mm, height_mm, "rectangle"
    )


def calibrate_paper(
    capture_id: str,
    corners_px: tuple[PixelPoint, PixelPoint, PixelPoint, PixelPoint],
    preset: PaperPreset,
) -> CalibrationRecord:
    return _calibrate_rectangle_method(
        capture_id,
        corners_px,
        preset.width_mm,
        preset.height_mm,
        f"paper:{preset.key}",
    )


def calibrate_known_object(
    capture_id: str,
    corners_px: tuple[PixelPoint, PixelPoint, PixelPoint, PixelPoint],
    width_mm: float,
    height_mm: float,
) -> CalibrationRecord:
    return _calibrate_rectangle_method(
        capture_id, corners_px, width_mm, height_mm, "known_object"
    )


def pixel_to_mm(record: CalibrationRecord, pixel: PixelPoint) -> Point2D:
    matrix = np.asarray(record.matrix_3x3, dtype=np.float64)
    source = np.array([pixel.x_px, pixel.y_px, 1.0], dtype=np.float64)
    mapped = matrix @ source
    if abs(mapped[2]) < 1e-12:
        raise ValueError("Calibration transform maps point to infinity")
    mapped /= mapped[2]
    return Point2D(float(mapped[0]), float(mapped[1]))
