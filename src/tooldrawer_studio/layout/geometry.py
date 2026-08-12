from __future__ import annotations

import math

from shapely import make_valid
from shapely.affinity import rotate, translate
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from tooldrawer_studio.domain.models import ToolObject
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement


def _finite_nonnegative(value: float, label: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{label} must be a finite non-negative value")
    return numeric


def _polygon_components(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        result: list[Polygon] = []
        for item in geometry.geoms:
            result.extend(_polygon_components(item))
        return result
    return []


def _largest_valid_polygon(geometry: BaseGeometry) -> Polygon:
    candidates = [
        polygon
        for polygon in _polygon_components(geometry)
        if not polygon.is_empty and polygon.area > 0.0
    ]
    if not candidates:
        raise ValueError("Tool contour must define a valid polygon")
    candidates.sort(
        key=lambda polygon: (
            polygon.area,
            polygon.bounds[0],
            polygon.bounds[1],
            polygon.bounds[2],
            polygon.bounds[3],
            polygon.wkb_hex,
        )
    )
    result = candidates[-1]
    if not result.is_valid:
        raise ValueError("Tool contour must define a valid polygon")
    return result


def _raw_tool_polygon(tool: ToolObject) -> Polygon:
    coordinates = [(float(point.x_mm), float(point.y_mm)) for point in tool.contour_mm]
    if len(coordinates) < 3 or len(set(coordinates)) < 3:
        raise ValueError("Tool contour must define a valid polygon")
    if any(not math.isfinite(value) for coordinate in coordinates for value in coordinate):
        raise ValueError("Tool contour must define a valid polygon")
    polygon = Polygon(coordinates)
    if polygon.is_empty or polygon.area <= 0.0:
        raise ValueError("Tool contour must define a valid polygon")
    if not polygon.is_valid:
        polygon = _largest_valid_polygon(make_valid(polygon))
    return polygon


def tool_cavity_polygon(tool: ToolObject) -> Polygon:
    """Return the manufacturing cavity footprint in source millimetres.

    The edited trace is authoritative. Existing per-tool manufacturing clearance is
    applied here before any Arrange-specific structural spacing is considered.
    """

    polygon = _raw_tool_polygon(tool)
    clearance = _finite_nonnegative(tool.clearance_mm, "clearance_mm")
    if clearance <= 0.0:
        return polygon
    buffered = polygon.buffer(clearance)
    return _largest_valid_polygon(buffered)


def _local_cavity_polygon(tool: ToolObject) -> Polygon:
    cavity = tool_cavity_polygon(tool)
    anchor = cavity.centroid
    return _largest_valid_polygon(
        translate(cavity, xoff=-anchor.x, yoff=-anchor.y)
    )


def _place_local_geometry(geometry: BaseGeometry, placement: ToolPlacement) -> BaseGeometry:
    rotated = rotate(
        geometry,
        placement.rotation_deg,
        origin=(0.0, 0.0),
        use_radians=False,
    )
    return translate(rotated, xoff=placement.x_mm, yoff=placement.y_mm)


def oriented_cavity_polygon(tool: ToolObject, placement: ToolPlacement) -> Polygon:
    """Rotate a cavity about its stable centroid, then move it to placement X/Y."""

    return _largest_valid_polygon(
        _place_local_geometry(_local_cavity_polygon(tool), placement)
    )


def spacing_exclusion_polygon(
    tool: ToolObject,
    placement: ToolPlacement,
    spacing_mm: float,
) -> Polygon:
    """Return half-spacing expansion around a cavity.

    Pairwise half-spacing buffers make two just-touching exclusion polygons equal
    to the requested cavity-to-cavity structural gap.
    """

    spacing = _finite_nonnegative(spacing_mm, "spacing_mm")
    local = _local_cavity_polygon(tool)
    if spacing > 0.0:
        local = _largest_valid_polygon(local.buffer(spacing / 2.0))
    return _largest_valid_polygon(_place_local_geometry(local, placement))


def grab_exclusion_polygon(
    tool: ToolObject,
    placement: ToolPlacement,
    spacing_mm: float,
    default_grab_clearance_mm: float,
) -> BaseGeometry:
    spacing = _finite_nonnegative(spacing_mm, "spacing_mm")
    local_normal: BaseGeometry = _local_cavity_polygon(tool)
    if spacing > 0.0:
        local_normal = _largest_valid_polygon(local_normal.buffer(spacing / 2.0))

    if placement.grab_side == "none":
        return _place_local_geometry(local_normal, placement)

    requested = (
        placement.grab_clearance_override_mm
        if placement.grab_clearance_override_mm is not None
        else default_grab_clearance_mm
    )
    clearance = _finite_nonnegative(requested, "grab_clearance_mm")
    if clearance <= 0.0:
        return _place_local_geometry(local_normal, placement)

    minx, miny, maxx, maxy = local_normal.bounds
    if placement.grab_side == "right":
        extra = box(maxx, miny, maxx + clearance, maxy)
    elif placement.grab_side == "left":
        extra = box(minx - clearance, miny, minx, maxy)
    elif placement.grab_side == "top":
        extra = box(minx, maxy, maxx, maxy + clearance)
    else:  # bottom
        extra = box(minx, miny - clearance, maxx, miny)

    local_with_grab = unary_union((local_normal, extra))
    return _place_local_geometry(local_with_grab, placement)


def candidate_exclusion_geometry(
    tool: ToolObject,
    placement: ToolPlacement,
    spacing_mm: float,
    default_grab_clearance_mm: float,
) -> BaseGeometry:
    return grab_exclusion_polygon(
        tool,
        placement,
        spacing_mm,
        default_grab_clearance_mm,
    )


def usable_boundary_polygon(layout: LayoutState) -> Polygon:
    border = _finite_nonnegative(layout.border_mm, "border_mm")
    width = float(layout.width_mm)
    height = float(layout.height_mm)
    if not math.isfinite(width) or not math.isfinite(height):
        raise ValueError("Layout dimensions must be finite")
    if width <= border * 2.0 or height <= border * 2.0:
        raise ValueError("Layout border leaves no usable boundary")
    return box(border, border, width - border, height - border)
