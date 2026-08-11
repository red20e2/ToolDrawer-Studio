from __future__ import annotations

from dataclasses import replace

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


def replace_tool_contour(tool: ToolObject, points: list[Point2D]) -> ToolObject:
    edited = list(points)
    validate_contour(edited)
    return replace(tool, contour_mm=edited)


def reset_tool_contour(tool: ToolObject) -> ToolObject:
    base = list(tool.base_contour_mm)
    validate_contour(base)
    return replace(tool, contour_mm=base)
