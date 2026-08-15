from __future__ import annotations

from math import hypot

import cv2
import numpy as np
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from tooldrawer_studio.calibration.service import PixelPoint, pixel_to_mm
from tooldrawer_studio.capture.image_loader import LoadedImage
from tooldrawer_studio.domain.models import CalibrationRecord, Point2D
from tooldrawer_studio.geometry.contour import validate_contour
from tooldrawer_studio.tracing.models import TraceCandidate, TraceConfig


def _polygon_area(points: list[Point2D]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for current, following in zip(points, points[1:] + points[:1]):
        total += current.x_mm * following.y_mm - following.x_mm * current.y_mm
    return abs(total) * 0.5


def _distance_to_segment(point: Point2D, start: Point2D, end: Point2D) -> float:
    dx = end.x_mm - start.x_mm
    dy = end.y_mm - start.y_mm
    if dx == 0.0 and dy == 0.0:
        return hypot(point.x_mm - start.x_mm, point.y_mm - start.y_mm)
    t = (
        (point.x_mm - start.x_mm) * dx + (point.y_mm - start.y_mm) * dy
    ) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nearest_x = start.x_mm + t * dx
    nearest_y = start.y_mm + t * dy
    return hypot(point.x_mm - nearest_x, point.y_mm - nearest_y)


def _rdp_open(points: list[Point2D], epsilon: float) -> list[Point2D]:
    if len(points) <= 2:
        return list(points)
    start, end = points[0], points[-1]
    max_distance = -1.0
    index = -1
    for i, point in enumerate(points[1:-1], start=1):
        distance = _distance_to_segment(point, start, end)
        if distance > max_distance:
            max_distance = distance
            index = i
    if max_distance > epsilon and index > 0:
        left = _rdp_open(points[: index + 1], epsilon)
        right = _rdp_open(points[index:], epsilon)
        return left[:-1] + right
    return [start, end]


def _simplify_closed(points: list[Point2D], epsilon: float) -> list[Point2D]:
    if len(points) <= 4 or epsilon <= 0:
        return list(points)
    anchor = points[0]
    split = max(
        range(1, len(points)),
        key=lambda i: hypot(
            points[i].x_mm - anchor.x_mm, points[i].y_mm - anchor.y_mm
        ),
    )
    first_arc = _rdp_open(points[: split + 1], epsilon)
    second_arc = _rdp_open(points[split:] + [points[0]], epsilon)
    combined = first_arc[:-1] + second_arc[:-1]
    deduped: list[Point2D] = []
    for point in combined:
        if not deduped or point != deduped[-1]:
            deduped.append(point)
    return deduped if len(deduped) >= 3 else list(points)


def _polygon_components(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        components: list[Polygon] = []
        for item in geometry.geoms:
            components.extend(_polygon_components(item))
        return components
    return []


def _valid_contour_components(points: list[Point2D]) -> list[tuple[list[Point2D], float]]:
    coordinates = [(float(point.x_mm), float(point.y_mm)) for point in points]
    if len(set(coordinates)) < 3:
        return []

    polygon = Polygon(coordinates)
    geometry: BaseGeometry = polygon if polygon.is_valid else make_valid(polygon)
    components = [
        component
        for component in _polygon_components(geometry)
        if not component.is_empty and component.area > 1e-6
    ]
    components.sort(
        key=lambda component: (
            component.area,
            component.bounds[0],
            component.bounds[1],
            component.bounds[2],
            component.bounds[3],
            component.wkb_hex,
        ),
        reverse=True,
    )

    repaired: list[tuple[list[Point2D], float]] = []
    for component in components:
        exterior = list(component.exterior.coords)
        contour = [
            Point2D(x_mm=float(x), y_mm=float(y))
            for x, y in exterior[:-1]
        ]
        try:
            validate_contour(contour)
        except ValueError:
            continue
        repaired.append((contour, float(component.area)))
    return repaired


def _border_foreground_count(mask: np.ndarray) -> int:
    border = np.concatenate((mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]))
    return int(np.count_nonzero(border))


def _select_foreground_mask(binary: np.ndarray, inverse: np.ndarray) -> np.ndarray:
    binary_border = _border_foreground_count(binary)
    inverse_border = _border_foreground_count(inverse)
    if binary_border < inverse_border:
        return binary
    if inverse_border < binary_border:
        return inverse
    binary_coverage = float(np.count_nonzero(binary)) / float(binary.size)
    inverse_coverage = float(np.count_nonzero(inverse)) / float(inverse.size)
    if binary_coverage < 0.5 <= inverse_coverage:
        return binary
    if inverse_coverage < 0.5 <= binary_coverage:
        return inverse
    return binary if binary_coverage <= inverse_coverage else inverse


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

        gray = cv2.cvtColor(image.pixels_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, binary = cv2.threshold(
            blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        _, inverse = cv2.threshold(
            blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )
        mask = _select_foreground_mask(binary, inverse)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
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
            simplified = _simplify_closed(mm_points, config.simplify_mm)
            components = _valid_contour_components(simplified)
            if not components:
                components = _valid_contour_components(mm_points)
            touches_border = any(
                int(vertex[0]) <= 0
                or int(vertex[1]) <= 0
                or int(vertex[0]) >= width - 1
                or int(vertex[1]) >= height - 1
                for vertex in pixel_vertices
            )
            for repaired_contour, area_mm2 in components:
                if area_mm2 < config.min_area_mm2:
                    continue
                confidence = 1.0
                if touches_border:
                    confidence -= 0.35
                if len(repaired_contour) < 4:
                    confidence -= 0.15
                confidence = max(0.0, min(1.0, confidence))
                candidates.append(
                    TraceCandidate(
                        base_contour_mm=repaired_contour,
                        confidence=confidence,
                        area_mm2=area_mm2,
                    )
                )
        candidates.sort(key=lambda candidate: candidate.area_mm2, reverse=True)
        return candidates
