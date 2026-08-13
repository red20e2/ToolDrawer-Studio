from __future__ import annotations

import math

import cadquery as cq
from shapely.geometry import Polygon

from tooldrawer_studio.domain.models import ToolObject
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon
from tooldrawer_studio.layout.models import ToolPlacement


def _positive(value: float, label: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return numeric


def polygon_workplane(polygon: Polygon) -> cq.Workplane:
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 0.0:
        raise ValueError("Cavity polygon must be valid and non-empty")
    if len(polygon.interiors):
        raise ValueError("Cavity polygons with interior rings are not supported")
    exterior = [(float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]]
    if len(exterior) < 3:
        raise ValueError("Cavity polygon requires at least three vertices")
    return cq.Workplane("XY").polyline(exterior).close()


def build_cavity_cutter(
    tool: ToolObject,
    placement: ToolPlacement,
    depth_mm: float,
    body_height_mm: float,
) -> cq.Workplane:
    depth = _positive(depth_mm, "depth_mm")
    height = _positive(body_height_mm, "body_height_mm")
    if depth > height:
        raise ValueError("depth_mm cannot exceed body_height_mm")
    polygon = oriented_cavity_polygon(tool, placement)
    return polygon_workplane(polygon).extrude(depth).translate(
        (0.0, 0.0, height - depth)
    )
