from __future__ import annotations

from math import hypot

import cv2
import numpy as np
from shapely import make_valid
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from tooldrawer_studio.calibration.service import PixelPoint, pixel_to_mm
from tooldrawer_studio.capture.image_loader import LoadedImage
from tooldrawer_studio.domain.models import CalibrationRecord, Point2D
from tooldrawer_studio.geometry.contour import validate_contour
from tooldrawer_studio.tracing.models import TraceCandidate, TraceConfig


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


def _global_foreground_mask(pixels_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(pixels_bgr, cv2.COLOR_BGR2GRAY)
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
    return mask


def _known_distance_focus_line(
    image: LoadedImage,
    calibration: CalibrationRecord,
) -> tuple[PixelPoint, PixelPoint] | None:
    if calibration.method != "known_distance":
        return None

    matrix = np.asarray(calibration.matrix_3x3, dtype=np.float64)
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return None

    def map_mm(x_mm: float, y_mm: float) -> tuple[float, float] | None:
        mapped = inverse @ np.array([x_mm, y_mm, 1.0], dtype=np.float64)
        if abs(float(mapped[2])) < 1e-12:
            return None
        mapped /= mapped[2]
        x_px = float(mapped[0])
        y_px = float(mapped[1])
        if not np.isfinite(x_px) or not np.isfinite(y_px):
            return None
        return x_px, y_px

    origin = map_mm(0.0, 0.0)
    one_mm = map_mm(1.0, 0.0)
    if origin is None or one_mm is None:
        return None
    dx = one_mm[0] - origin[0]
    dy = one_mm[1] - origin[1]
    magnitude = hypot(dx, dy)
    if magnitude <= 1e-12:
        return None
    dx /= magnitude
    dy /= magnitude

    height, width = image.pixels_bgr.shape[:2]
    max_x = float(max(0, width - 1))
    max_y = float(max(0, height - 1))
    ox, oy = origin
    intersections: list[tuple[float, float]] = []

    if abs(dx) > 1e-12:
        for x in (0.0, max_x):
            t = (x - ox) / dx
            y = oy + t * dy
            if -1e-6 <= y <= max_y + 1e-6:
                intersections.append((x, min(max(y, 0.0), max_y)))
    if abs(dy) > 1e-12:
        for y in (0.0, max_y):
            t = (y - oy) / dy
            x = ox + t * dx
            if -1e-6 <= x <= max_x + 1e-6:
                intersections.append((min(max(x, 0.0), max_x), y))

    unique: list[tuple[float, float]] = []
    for point in intersections:
        if not any(hypot(point[0] - prior[0], point[1] - prior[1]) < 1e-6 for prior in unique):
            unique.append(point)
    if len(unique) < 2:
        return None

    first, second = max(
        (
            (a, b)
            for index, a in enumerate(unique)
            for b in unique[index + 1 :]
        ),
        key=lambda pair: hypot(pair[1][0] - pair[0][0], pair[1][1] - pair[0][1]),
    )
    if hypot(second[0] - first[0], second[1] - first[1]) < 12.0:
        return None
    return PixelPoint(*first), PixelPoint(*second)


def _focus_line_mask(
    pixels_bgr: np.ndarray,
    focus_line_px: tuple[PixelPoint, PixelPoint],
) -> np.ndarray | None:
    first, second = focus_line_px
    dx = float(second.x_px - first.x_px)
    dy = float(second.y_px - first.y_px)
    line_length = hypot(dx, dy)
    if line_length < 12.0:
        return None

    height, width = pixels_bgr.shape[:2]
    if width <= 0 or height <= 0:
        return None

    ax = int(round(first.x_px))
    ay = int(round(first.y_px))
    bx = int(round(second.x_px))
    by = int(round(second.y_px))
    if (
        max(ax, bx) < 0
        or max(ay, by) < 0
        or min(ax, bx) >= width
        or min(ay, by) >= height
    ):
        return None

    half_width = int(
        round(max(8.0, min(0.09 * line_length, 0.22 * min(width, height))))
    )
    grabcut_mask = np.full((height, width), cv2.GC_BGD, dtype=np.uint8)
    thickness = max(3, half_width * 2)
    cv2.line(
        grabcut_mask,
        (ax, ay),
        (bx, by),
        cv2.GC_PR_FGD,
        thickness=thickness,
        lineType=cv2.LINE_AA,
    )
    cv2.circle(grabcut_mask, (ax, ay), half_width, cv2.GC_PR_FGD, -1)
    cv2.circle(grabcut_mask, (bx, by), half_width, cv2.GC_PR_FGD, -1)

    midpoint = (int(round((ax + bx) / 2.0)), int(round((ay + by) / 2.0)))
    seed_radius = max(3, min(half_width // 4, 12))
    cv2.circle(grabcut_mask, midpoint, seed_radius, cv2.GC_FGD, -1)

    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(
            pixels_bgr,
            grabcut_mask,
            None,
            background_model,
            foreground_model,
            5,
            cv2.GC_INIT_WITH_MASK,
        )
    except cv2.error:
        return None

    foreground = np.where(
        (grabcut_mask == cv2.GC_FGD) | (grabcut_mask == cv2.GC_PR_FGD),
        255,
        0,
    ).astype(np.uint8)
    foreground_count = int(np.count_nonzero(foreground))
    if foreground_count < 20:
        return None

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    foreground = cv2.morphologyEx(
        foreground, cv2.MORPH_CLOSE, kernel, iterations=1
    )
    foreground = cv2.morphologyEx(
        foreground, cv2.MORPH_OPEN, kernel, iterations=1
    )
    return foreground


def _candidates_from_mask(
    mask: np.ndarray,
    calibration: CalibrationRecord,
    config: TraceConfig,
) -> list[TraceCandidate]:
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


def _candidate_polygon(candidate: TraceCandidate) -> Polygon | None:
    polygon = Polygon(
        [(point.x_mm, point.y_mm) for point in candidate.base_contour_mm]
    )
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 1e-9:
        return None
    return polygon


def _focus_sort_key(
    candidate: TraceCandidate,
    calibration: CalibrationRecord,
    focus_line_px: tuple[PixelPoint, PixelPoint],
) -> tuple[float, float, float, float]:
    first_mm = pixel_to_mm(calibration, focus_line_px[0])
    second_mm = pixel_to_mm(calibration, focus_line_px[1])
    midpoint = Point(
        (first_mm.x_mm + second_mm.x_mm) / 2.0,
        (first_mm.y_mm + second_mm.y_mm) / 2.0,
    )
    line = LineString(
        [
            (first_mm.x_mm, first_mm.y_mm),
            (second_mm.x_mm, second_mm.y_mm),
        ]
    )
    polygon = _candidate_polygon(candidate)
    if polygon is None:
        return (1.0, 0.0, float("inf"), candidate.area_mm2)
    midpoint_distance = float(polygon.distance(midpoint))
    overlap_length = float(polygon.intersection(line).length)
    contains_midpoint = 0.0 if polygon.buffer(1e-9).covers(midpoint) else 1.0
    return (
        contains_midpoint,
        -overlap_length,
        midpoint_distance,
        candidate.area_mm2,
    )


def _overlap_fraction(first: TraceCandidate, second: TraceCandidate) -> float:
    first_polygon = _candidate_polygon(first)
    second_polygon = _candidate_polygon(second)
    if first_polygon is None or second_polygon is None:
        return 0.0
    smaller = min(float(first_polygon.area), float(second_polygon.area))
    if smaller <= 1e-9:
        return 0.0
    return float(first_polygon.intersection(second_polygon).area) / smaller


class OpenCVTracer:
    def trace(
        self,
        image: LoadedImage,
        calibration: CalibrationRecord,
        config: TraceConfig = TraceConfig(),
        *,
        focus_line_px: tuple[PixelPoint, PixelPoint] | None = None,
    ) -> list[TraceCandidate]:
        if config.min_area_mm2 <= 0:
            raise ValueError("min_area_mm2 must be positive")
        if config.simplify_mm < 0:
            raise ValueError("simplify_mm must be non-negative")
        if calibration.capture_id != image.asset.id:
            raise ValueError("Calibration does not belong to this capture")

        global_mask = _global_foreground_mask(image.pixels_bgr)
        global_candidates = _candidates_from_mask(global_mask, calibration, config)

        effective_focus = focus_line_px
        if effective_focus is None:
            effective_focus = _known_distance_focus_line(image, calibration)
        if effective_focus is None:
            return global_candidates

        focused_mask = _focus_line_mask(image.pixels_bgr, effective_focus)
        if focused_mask is None:
            return global_candidates
        focused_candidates = _candidates_from_mask(focused_mask, calibration, config)
        if not focused_candidates:
            return global_candidates

        focused_candidates.sort(
            key=lambda candidate: _focus_sort_key(
                candidate, calibration, effective_focus
            )
        )
        primary = focused_candidates[0]
        ordered: list[TraceCandidate] = [primary]

        for candidate in global_candidates:
            if _overlap_fraction(primary, candidate) >= 0.75:
                continue
            ordered.append(candidate)
        return ordered
