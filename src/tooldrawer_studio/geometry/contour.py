from __future__ import annotations

from dataclasses import replace
from math import hypot

from tooldrawer_studio.domain.models import Point2D, ToolObject

_EPSILON = 1e-9


def polygon_area_mm2(points: list[Point2D]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for current, following in zip(points, points[1:] + points[:1]):
        total += current.x_mm * following.y_mm - following.x_mm * current.y_mm
    return abs(total) * 0.5


def _orientation(a: Point2D, b: Point2D, c: Point2D) -> float:
    return (b.x_mm - a.x_mm) * (c.y_mm - a.y_mm) - (b.y_mm - a.y_mm) * (c.x_mm - a.x_mm)


def _on_segment(a: Point2D, b: Point2D, p: Point2D) -> bool:
    return (
        min(a.x_mm, b.x_mm) - _EPSILON <= p.x_mm <= max(a.x_mm, b.x_mm) + _EPSILON
        and min(a.y_mm, b.y_mm) - _EPSILON <= p.y_mm <= max(a.y_mm, b.y_mm) + _EPSILON
        and abs(_orientation(a, b, p)) <= _EPSILON
    )


def _segments_intersect(a: Point2D, b: Point2D, c: Point2D, d: Point2D) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    if ((o1 > _EPSILON and o2 < -_EPSILON) or (o1 < -_EPSILON and o2 > _EPSILON)) and (
        (o3 > _EPSILON and o4 < -_EPSILON) or (o3 < -_EPSILON and o4 > _EPSILON)
    ):
        return True
    return (
        (abs(o1) <= _EPSILON and _on_segment(a, b, c))
        or (abs(o2) <= _EPSILON and _on_segment(a, b, d))
        or (abs(o3) <= _EPSILON and _on_segment(c, d, a))
        or (abs(o4) <= _EPSILON and _on_segment(c, d, b))
    )


def _has_self_intersection(points: list[Point2D]) -> bool:
    count = len(points)
    for i in range(count):
        a = points[i]
        b = points[(i + 1) % count]
        for j in range(i + 1, count):
            if j == i or j == (i + 1) % count or (j + 1) % count == i:
                continue
            if i == 0 and j == count - 1:
                continue
            c = points[j]
            d = points[(j + 1) % count]
            if _segments_intersect(a, b, c, d):
                return True
    return False


def validate_contour(points: list[Point2D]) -> None:
    if len({(point.x_mm, point.y_mm) for point in points}) < 3:
        raise ValueError("Contour requires at least three unique points")
    if _has_self_intersection(points):
        raise ValueError("Contour is self-intersecting")
    if polygon_area_mm2(points) <= 1e-6:
        raise ValueError("Contour area must be greater than zero")


def distance_to_segment(point: Point2D, start: Point2D, end: Point2D) -> float:
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


def closest_point_on_segment(point: Point2D, start: Point2D, end: Point2D) -> Point2D:
    dx = end.x_mm - start.x_mm
    dy = end.y_mm - start.y_mm
    if dx == 0.0 and dy == 0.0:
        return start
    t = (
        (point.x_mm - start.x_mm) * dx + (point.y_mm - start.y_mm) * dy
    ) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return Point2D(start.x_mm + t * dx, start.y_mm + t * dy)


def nearest_segment_index(
    point: Point2D, points: list[Point2D]
) -> tuple[int, Point2D, float]:
    if len(points) < 2:
        raise ValueError("A contour requires at least two points")
    best_index = 0
    best_point = points[0]
    best_distance = float("inf")
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        candidate = closest_point_on_segment(point, start, end)
        distance = hypot(point.x_mm - candidate.x_mm, point.y_mm - candidate.y_mm)
        if distance < best_distance:
            best_index = index
            best_point = candidate
            best_distance = distance
    return best_index, best_point, best_distance


def _rdp_open(points: list[Point2D], epsilon: float) -> list[Point2D]:
    if len(points) <= 2:
        return list(points)
    start, end = points[0], points[-1]
    max_distance = -1.0
    index = -1
    for i, point in enumerate(points[1:-1], start=1):
        distance = distance_to_segment(point, start, end)
        if distance > max_distance:
            max_distance = distance
            index = i
    if max_distance > epsilon and index > 0:
        left = _rdp_open(points[: index + 1], epsilon)
        right = _rdp_open(points[index:], epsilon)
        return left[:-1] + right
    return [start, end]


def simplify_closed_contour(points: list[Point2D], epsilon: float) -> list[Point2D]:
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
    simplified = deduped if len(deduped) >= 3 else list(points)
    try:
        validate_contour(simplified)
    except ValueError:
        return list(points)
    return simplified


def smooth_closed_contour(
    points: list[Point2D], epsilon: float, *, iterations: int = 1
) -> list[Point2D]:
    """Chaikin-style smoothing clamped so no vertex moves more than epsilon."""
    if len(points) < 4 or epsilon <= 0 or iterations <= 0:
        return list(points)
    current = list(points)
    original = list(points)
    for _ in range(iterations):
        smoothed: list[Point2D] = []
        count = len(current)
        for index, start in enumerate(current):
            end = current[(index + 1) % count]
            q = Point2D(
                0.75 * start.x_mm + 0.25 * end.x_mm,
                0.75 * start.y_mm + 0.25 * end.y_mm,
            )
            r = Point2D(
                0.25 * start.x_mm + 0.75 * end.x_mm,
                0.25 * start.y_mm + 0.75 * end.y_mm,
            )
            smoothed.extend((q, r))
        current = smoothed
    if len(current) < 3:
        return original

    # Resample back onto the original vertex count by nearest original-arc points,
    # then clamp displacement so manufacturing geometry cannot drift past epsilon.
    if len(current) != len(original):
        resampled: list[Point2D] = []
        for point in original:
            _index, nearest, _distance = nearest_segment_index(point, current)
            resampled.append(nearest)
        current = resampled

    clamped: list[Point2D] = []
    for previous, proposed in zip(original, current):
        dx = proposed.x_mm - previous.x_mm
        dy = proposed.y_mm - previous.y_mm
        distance = hypot(dx, dy)
        if distance > epsilon and distance > 0:
            scale = epsilon / distance
            clamped.append(
                Point2D(previous.x_mm + dx * scale, previous.y_mm + dy * scale)
            )
        else:
            clamped.append(proposed)
    try:
        validate_contour(clamped)
    except ValueError:
        return original
    return clamped


def offset_contour_mm(points: list[Point2D], offset_mm: float) -> list[list[Point2D]]:
    if abs(offset_mm) <= 1e-12:
        return [list(points)]
    from shapely.geometry import Polygon

    polygon = Polygon([(point.x_mm, point.y_mm) for point in points])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    buffered = polygon.buffer(offset_mm, join_style=1)
    if buffered.is_empty:
        return []
    geometries = [buffered] if buffered.geom_type == "Polygon" else list(buffered.geoms)
    outlines: list[list[Point2D]] = []
    for geometry in geometries:
        coords = list(geometry.exterior.coords)
        if len(coords) >= 2 and coords[0] == coords[-1]:
            coords = coords[:-1]
        outline = [Point2D(float(x), float(y)) for x, y in coords]
        if len(outline) >= 3:
            outlines.append(outline)
    return outlines


def replace_tool_contour(tool: ToolObject, points: list[Point2D]) -> ToolObject:
    edited = list(points)
    validate_contour(edited)
    return replace(tool, contour_mm=edited)


def reset_tool_contour(tool: ToolObject) -> ToolObject:
    base = list(tool.base_contour_mm)
    validate_contour(base)
    return replace(tool, contour_mm=base)
