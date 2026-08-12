from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np

from tooldrawer_studio.calibration.presets import PaperPreset
from tooldrawer_studio.calibration.service import PixelPoint, calibrate_rectangle
from tooldrawer_studio.capture.image_loader import LoadedImage
from tooldrawer_studio.domain.models import CalibrationRecord


@dataclass(frozen=True, slots=True)
class CalibrationTargetSpec:
    paper: PaperPreset
    inset_mm: float = 20.0
    fiducial_size_mm: float = 12.0

    def __post_init__(self) -> None:
        if self.inset_mm <= 0:
            raise ValueError("Target inset must be positive")
        if self.fiducial_size_mm <= 0:
            raise ValueError("Fiducial size must be positive")
        if 2.0 * self.inset_mm >= self.paper.width_mm:
            raise ValueError("Target inset leaves no horizontal calibration span")
        if 2.0 * self.inset_mm >= self.paper.height_mm:
            raise ValueError("Target inset leaves no vertical calibration span")


@dataclass(frozen=True, slots=True)
class DetectedTarget:
    corners_px: tuple[PixelPoint, PixelPoint, PixelPoint, PixelPoint]
    confidence: float


def _number(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def target_svg(spec: CalibrationTargetSpec) -> str:
    width = spec.paper.width_mm
    height = spec.paper.height_mm
    half = spec.fiducial_size_mm / 2.0
    centers = (
        (spec.inset_mm, spec.inset_mm),
        (width - spec.inset_mm, spec.inset_mm),
        (width - spec.inset_mm, height - spec.inset_mm),
        (spec.inset_mm, height - spec.inset_mm),
    )

    fiducials = "\n".join(
        f'  <rect x="{_number(x - half)}" y="{_number(y - half)}" '
        f'width="{_number(spec.fiducial_size_mm)}" '
        f'height="{_number(spec.fiducial_size_mm)}" fill="black" />'
        for x, y in centers
    )

    crosshair_lines: list[str] = []
    arm = spec.fiducial_size_mm * 0.9
    gap = half + max(1.5, spec.fiducial_size_mm * 0.15)
    for x, y in centers:
        crosshair_lines.extend(
            (
                f'  <line x1="{_number(x - arm)}" y1="{_number(y)}" '
                f'x2="{_number(x - gap)}" y2="{_number(y)}" stroke="black" stroke-width="0.25" />',
                f'  <line x1="{_number(x + gap)}" y1="{_number(y)}" '
                f'x2="{_number(x + arm)}" y2="{_number(y)}" stroke="black" stroke-width="0.25" />',
                f'  <line x1="{_number(x)}" y1="{_number(y - arm)}" '
                f'x2="{_number(x)}" y2="{_number(y - gap)}" stroke="black" stroke-width="0.25" />',
                f'  <line x1="{_number(x)}" y1="{_number(y + gap)}" '
                f'x2="{_number(x)}" y2="{_number(y + arm)}" stroke="black" stroke-width="0.25" />',
            )
        )

    bar_x = width / 2.0 - 50.0
    bar_y = height / 2.0
    vertical_x = width / 2.0
    vertical_y = height / 2.0 - 50.0

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_number(width)}mm" '
        f'height="{_number(height)}mm" viewBox="0 0 {_number(width)} {_number(height)}">\n'
        '  <title>ToolDrawer Studio Calibration Target</title>\n'
        f'{fiducials}\n'
        f'{chr(10).join(crosshair_lines)}\n'
        f'  <line x1="{_number(bar_x)}" y1="{_number(bar_y)}" '
        f'x2="{_number(bar_x + 100.0)}" y2="{_number(bar_y)}" stroke="black" stroke-width="0.4" />\n'
        f'  <text x="{_number(width / 2.0)}" y="{_number(bar_y - 2.0)}" '
        'font-size="4" text-anchor="middle">100 mm</text>\n'
        f'  <line x1="{_number(vertical_x)}" y1="{_number(vertical_y)}" '
        f'x2="{_number(vertical_x)}" y2="{_number(vertical_y + 100.0)}" stroke="black" stroke-width="0.4" />\n'
        f'  <text x="{_number(vertical_x + 3.0)}" y="{_number(height / 2.0)}" '
        'font-size="4">100 mm</text>\n'
        '  <text x="5" y="8" font-size="4">ToolDrawer Studio - print at 100% scale</text>\n'
        '</svg>\n'
    )


def write_target_svg(path: Path, spec: CalibrationTargetSpec) -> None:
    path.write_text(target_svg(spec), encoding="utf-8")


def _order_centers(points: np.ndarray) -> np.ndarray:
    if points.shape != (4, 2):
        raise ValueError("Exactly four target points are required")
    sums = points.sum(axis=1)
    differences = points[:, 1] - points[:, 0]
    indexes = (
        int(np.argmin(sums)),
        int(np.argmin(differences)),
        int(np.argmax(sums)),
        int(np.argmax(differences)),
    )
    if len(set(indexes)) != 4:
        raise ValueError("Target points cannot be ordered unambiguously")
    return points[list(indexes)]


def _candidate_centers(image: LoadedImage) -> list[tuple[np.ndarray, float]]:
    gray = cv2.cvtColor(image.pixels_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    candidates: list[tuple[np.ndarray, float, float]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 100.0:
            continue
        perimeter = float(cv2.arcLength(contour, True))
        if perimeter <= 1e-9:
            continue
        approximate = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        if len(approximate) != 4 or not cv2.isContourConvex(approximate):
            continue

        _x, _y, width, height = cv2.boundingRect(approximate)
        if width <= 0 or height <= 0:
            continue
        aspect = float(width) / float(height)
        if not 0.65 <= aspect <= 1.35:
            continue
        fill_ratio = area / float(width * height)
        if fill_ratio < 0.70:
            continue

        moments = cv2.moments(contour)
        if abs(moments["m00"]) <= 1e-9:
            continue
        center = np.array(
            [moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]],
            dtype=np.float32,
        )
        squareness = min(min(aspect, 1.0 / aspect), min(fill_ratio, 1.0))
        candidates.append((center, squareness, area))

    candidates.sort(key=lambda item: item[2], reverse=True)

    deduplicated: list[tuple[np.ndarray, float]] = []
    for center, score, _area in candidates:
        if any(float(np.linalg.norm(center - existing)) < 12.0 for existing, _ in deduplicated):
            continue
        deduplicated.append((center, score))
        if len(deduplicated) >= 20:
            break
    return deduplicated


def detect_target(image: LoadedImage, spec: CalibrationTargetSpec) -> DetectedTarget:
    del spec  # Detection is geometric; the spec supplies physical dimensions after detection.
    candidates = _candidate_centers(image)
    if len(candidates) < 4:
        raise ValueError("Could not detect four calibration target fiducials")

    best_points: np.ndarray | None = None
    best_scores: tuple[float, ...] | None = None
    best_area = -1.0
    for indexes in combinations(range(len(candidates)), 4):
        points = np.array([candidates[index][0] for index in indexes], dtype=np.float32)
        hull = cv2.convexHull(points)
        if len(hull) != 4:
            continue
        area = abs(float(cv2.contourArea(hull)))
        if area > best_area:
            best_area = area
            best_points = points
            best_scores = tuple(candidates[index][1] for index in indexes)

    if best_points is None or best_scores is None:
        raise ValueError("Calibration target fiducials are ambiguous")

    ordered = _order_centers(best_points)
    image_area = float(image.asset.width_px * image.asset.height_px)
    coverage_score = min(1.0, best_area / max(image_area * 0.45, 1.0))
    shape_score = float(sum(best_scores) / len(best_scores))
    confidence = min(0.98, max(0.0, 0.55 + 0.43 * min(shape_score, coverage_score)))
    if confidence < 0.55:
        raise ValueError("Calibration target detection confidence is too low")

    corners = tuple(PixelPoint(float(x), float(y)) for x, y in ordered)
    return DetectedTarget(corners_px=corners, confidence=confidence)  # type: ignore[arg-type]


def calibrate_target(
    capture_id: str,
    image: LoadedImage,
    spec: CalibrationTargetSpec,
) -> CalibrationRecord:
    detected = detect_target(image, spec)
    width_span = spec.paper.width_mm - 2.0 * spec.inset_mm
    height_span = spec.paper.height_mm - 2.0 * spec.inset_mm
    record = calibrate_rectangle(
        capture_id,
        detected.corners_px,
        width_span,
        height_span,
    )
    record.method = f"target:{spec.paper.key}"
    record.confidence = min(record.confidence, detected.confidence)
    return record
