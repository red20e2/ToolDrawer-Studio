from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import cv2
import numpy as np

from tooldrawer_studio.domain.models import CalibrationRecord
from tooldrawer_studio.measurement.models import ImagePoint, ThicknessMeasurementResult


@dataclass(frozen=True, slots=True)
class _Candidate:
    area_px2: float
    contour: np.ndarray
    touches_boundary: bool


def _threshold_masks(pixels_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(pixels_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, light = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return light, cv2.bitwise_not(light)


def _candidate_contours(pixels_bgr: np.ndarray) -> list[_Candidate]:
    height, width = pixels_bgr.shape[:2]
    image_area = float(width * height)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    candidates: list[_Candidate] = []

    for threshold in _threshold_masks(pixels_bgr):
        cleaned = cv2.morphologyEx(threshold, cv2.MORPH_OPEN, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(
            cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )
        for contour in contours:
            area = abs(float(cv2.contourArea(contour)))
            if area < image_area * 0.005 or area > image_area * 0.85:
                continue
            points = contour[:, 0, :]
            touches = bool(
                np.any(points[:, 0] <= 0)
                or np.any(points[:, 1] <= 0)
                or np.any(points[:, 0] >= width - 1)
                or np.any(points[:, 1] >= height - 1)
            )
            candidates.append(_Candidate(area, contour, touches))

    candidates.sort(key=lambda candidate: candidate.area_px2, reverse=True)
    return candidates


def _map_pixels_to_mm(
    contour_px: np.ndarray, calibration: CalibrationRecord
) -> np.ndarray:
    matrix = np.asarray(calibration.matrix_3x3, dtype=np.float64)
    pixels = contour_px.astype(np.float64)
    homogeneous = np.column_stack(
        (pixels[:, 0], pixels[:, 1], np.ones(len(pixels), dtype=np.float64))
    )
    mapped = (matrix @ homogeneous.T).T
    denominators = mapped[:, 2]
    if np.any(np.abs(denominators) < 1e-12):
        raise ValueError("Calibration transform maps side profile to infinity")
    mm_points = mapped[:, :2] / denominators[:, None]
    if not np.isfinite(mm_points).all():
        raise ValueError("Calibration produced non-finite side-profile geometry")
    return mm_points


def _maximum_cross_section(
    contour: np.ndarray, calibration: CalibrationRecord
) -> tuple[float, int, int, float]:
    source_points = contour[:, 0, :].astype(np.float64)
    mm_points = _map_pixels_to_mm(source_points, calibration)
    if len(mm_points) < 3:
        raise ValueError("No usable side-profile silhouette")

    centered = mm_points - mm_points.mean(axis=0)
    _, singular_values, vh = np.linalg.svd(centered, full_matrices=False)
    if len(singular_values) < 2 or not np.isfinite(singular_values).all():
        raise ValueError("No usable side-profile silhouette")

    long_axis = vh[0]
    normal_axis = np.array([-long_axis[1], long_axis[0]], dtype=np.float64)
    long_position = centered @ long_axis
    normal_position = centered @ normal_axis
    long_span_mm = float(np.ptp(long_position))
    if not np.isfinite(long_span_mm) or long_span_mm <= 0:
        raise ValueError("No usable side-profile silhouette")

    bin_count = max(64, int(round(long_span_mm)))
    edges = np.linspace(
        float(long_position.min()), float(long_position.max()), bin_count + 1
    )
    spans: list[float] = []
    best: tuple[float, int, int] | None = None

    for index in range(bin_count):
        if index == bin_count - 1:
            members = np.flatnonzero(
                (long_position >= edges[index])
                & (long_position <= edges[index + 1])
            )
        else:
            members = np.flatnonzero(
                (long_position >= edges[index])
                & (long_position < edges[index + 1])
            )
        if len(members) < 2:
            continue

        normal_values = normal_position[members]
        low_index = int(members[int(np.argmin(normal_values))])
        high_index = int(members[int(np.argmax(normal_values))])
        span = float(normal_position[high_index] - normal_position[low_index])
        if not np.isfinite(span) or span <= 0:
            continue
        spans.append(span)
        if best is None or span > best[0]:
            best = (span, low_index, high_index)

    if best is None:
        raise ValueError("No usable side-profile silhouette")

    largest = best[0]
    top_three = sorted(spans, reverse=True)[:3]
    peak_stability = float(median(top_three) / largest) if top_three else 0.0
    return largest, best[1], best[2], peak_stability


def _contrast_delta(gray: np.ndarray, contour: np.ndarray) -> float:
    selected = np.zeros(gray.shape, dtype=np.uint8)
    cv2.drawContours(selected, [contour], -1, 255, thickness=cv2.FILLED)
    foreground = gray[selected > 0]
    background = gray[selected == 0]
    if foreground.size == 0 or background.size == 0:
        return 0.0
    return abs(float(foreground.mean()) - float(background.mean()))


def _silhouette_points(contour: np.ndarray) -> tuple[ImagePoint, ...]:
    simplified = cv2.approxPolyDP(contour, 1.0, True)
    return tuple(
        ImagePoint(float(point[0][0]), float(point[0][1])) for point in simplified
    )


class ThicknessMeasurementService:
    def measure(
        self, pixels_bgr: np.ndarray, calibration: CalibrationRecord
    ) -> ThicknessMeasurementResult:
        if (
            pixels_bgr.ndim != 3
            or pixels_bgr.shape[2] != 3
            or pixels_bgr.size == 0
        ):
            raise ValueError("Side-view image must be a non-empty BGR image")
        if not np.isfinite(float(calibration.confidence)):
            raise ValueError("Calibration confidence must be finite")

        candidates = _candidate_contours(pixels_bgr)
        if not candidates:
            raise ValueError("No usable side-profile silhouette")

        selected = candidates[0]
        second_area_ratio = (
            candidates[1].area_px2 / selected.area_px2
            if len(candidates) > 1 and selected.area_px2 > 0
            else 0.0
        )
        thickness_mm, endpoint_a_index, endpoint_b_index, peak_stability = (
            _maximum_cross_section(selected.contour, calibration)
        )
        if not np.isfinite(thickness_mm) or thickness_mm <= 0:
            raise ValueError("Automatic thickness must be finite and positive")

        source_points = selected.contour[:, 0, :]
        endpoint_a = source_points[endpoint_a_index]
        endpoint_b = source_points[endpoint_b_index]
        gray = cv2.cvtColor(pixels_bgr, cv2.COLOR_BGR2GRAY)
        contrast_delta = _contrast_delta(gray, selected.contour)

        confidence = max(0.0, min(1.0, float(calibration.confidence)))
        warnings: list[str] = []
        if selected.touches_boundary:
            confidence *= 0.55
            warnings.append("silhouette touches image boundary")
        if second_area_ratio >= 0.60:
            confidence *= 0.70
            warnings.append("multiple plausible silhouettes")
        if contrast_delta < 30.0:
            confidence *= 0.70
            warnings.append("low foreground/background contrast")
        if peak_stability < 0.65:
            confidence *= 0.80
            warnings.append("maximum thickness is unstable")
        confidence = max(0.0, min(1.0, float(confidence)))

        return ThicknessMeasurementResult(
            automatic_thickness_mm=float(thickness_mm),
            confidence=confidence,
            endpoint_a_px=ImagePoint(float(endpoint_a[0]), float(endpoint_a[1])),
            endpoint_b_px=ImagePoint(float(endpoint_b[0]), float(endpoint_b[1])),
            silhouette_px=_silhouette_points(selected.contour),
            warnings=tuple(warnings),
        )
