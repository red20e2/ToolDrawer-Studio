from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Iterable

from shapely.geometry.base import BaseGeometry

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.layout.geometry import (
    boundary_exclusion_geometry,
    candidate_exclusion_geometry,
    grab_access_polygon,
    oriented_cavity_polygon,
    spacing_exclusion_polygon,
    tool_cavity_polygon,
    usable_boundary_polygon,
)
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.layout.scoring import candidate_score
from tooldrawer_studio.layout.validation import LayoutValidationResult, validate_layout

_INTERSECTION_AREA_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class PackingResult:
    placements: tuple[ToolPlacement, ...]
    unplaced_tool_ids: tuple[str, ...]
    validation: LayoutValidationResult


@dataclass(frozen=True, slots=True)
class _PackingGeometry:
    cavity: BaseGeometry
    spacing: BaseGeometry
    grab: BaseGeometry
    boundary: BaseGeometry
    search: BaseGeometry


def rotation_candidates(placement: ToolPlacement) -> tuple[float, ...]:
    if placement.rotation_policy == "fixed":
        return (float(placement.rotation_deg),)
    if placement.rotation_policy == "orthogonal":
        return (0.0, 90.0, 180.0, 270.0)
    return tuple(float(value) for value in range(0, 360, 15))


def _placement_map(layout: LayoutState) -> dict[str, ToolPlacement]:
    return {placement.tool_id: placement for placement in layout.placements}


def pack_order(project: Project, layout: LayoutState) -> tuple[ToolObject, ...]:
    placements = _placement_map(layout)

    def key(tool: ToolObject) -> tuple[int, float, float, str]:
        placement = placements.get(tool.id, ToolPlacement(tool_id=tool.id))
        policy_rank = {"fixed": 0, "orthogonal": 1, "free": 2}[placement.rotation_policy]
        polygon = tool_cavity_polygon(tool)
        minx, miny, maxx, maxy = polygon.bounds
        maximum_dimension = max(maxx - minx, maxy - miny)
        return (policy_rank, -maximum_dimension, -polygon.area, tool.id)

    return tuple(sorted(project.tools, key=key))


def _copy_layout(layout: LayoutState, placements: Iterable[ToolPlacement]) -> LayoutState:
    return LayoutState(
        mode=layout.mode,
        foam_width_mm=layout.foam_width_mm,
        foam_height_mm=layout.foam_height_mm,
        grid_columns=layout.grid_columns,
        grid_rows=layout.grid_rows,
        grid_pitch_mm=layout.grid_pitch_mm,
        spacing_mm=layout.spacing_mm,
        border_mm=layout.border_mm,
        grab_clearance_mm=layout.grab_clearance_mm,
        snap_enabled=layout.snap_enabled,
        snap_increment_mm=layout.snap_increment_mm,
        placements=list(placements),
        unplaced_tool_ids=[],
        review_required=False,
    )


def _geometry_for(
    tool: ToolObject,
    placement: ToolPlacement,
    layout: LayoutState,
) -> _PackingGeometry:
    return _PackingGeometry(
        cavity=oriented_cavity_polygon(tool, placement),
        spacing=spacing_exclusion_polygon(tool, placement, layout.spacing_mm),
        grab=grab_access_polygon(tool, placement, layout.grab_clearance_mm),
        boundary=boundary_exclusion_geometry(
            tool,
            placement,
            layout.grab_clearance_mm,
        ),
        search=candidate_exclusion_geometry(
            tool,
            placement,
            spacing_mm=layout.spacing_mm,
            default_grab_clearance_mm=layout.grab_clearance_mm,
        ),
    )


def _has_area_intersection(left: BaseGeometry, right: BaseGeometry) -> bool:
    if left.is_empty or right.is_empty:
        return False
    intersection = left.intersection(right)
    return (
        not intersection.is_empty
        and intersection.area > _INTERSECTION_AREA_TOLERANCE
    )


def _conflicts(
    candidate: _PackingGeometry,
    existing: Iterable[_PackingGeometry],
) -> bool:
    for other in existing:
        if _has_area_intersection(candidate.spacing, other.spacing):
            return True
        if _has_area_intersection(candidate.cavity, other.grab):
            return True
        if _has_area_intersection(candidate.grab, other.cavity):
            return True
    return False


def _add_if_in_range(values: set[float], value: float, low: float, high: float) -> None:
    if value < low - 1e-9 or value > high + 1e-9:
        return
    values.add(round(min(max(value, low), high), 9))


def _axis_candidates(
    low: float,
    high: float,
    boundary_local_low: float,
    boundary_local_high: float,
    anchor_local_low: float,
    anchor_local_high: float,
    existing_bounds: list[tuple[float, float, float, float]],
    *,
    x_axis: bool,
) -> list[float]:
    minimum_center = low - boundary_local_low
    maximum_center = high - boundary_local_high
    if minimum_center > maximum_center + 1e-9:
        return []

    values: set[float] = set()
    for value in (
        minimum_center,
        maximum_center,
        (minimum_center + maximum_center) / 2.0,
    ):
        _add_if_in_range(values, value, minimum_center, maximum_center)

    anchor_center = (anchor_local_low + anchor_local_high) / 2.0
    for bounds in existing_bounds:
        existing_low = bounds[0] if x_axis else bounds[1]
        existing_high = bounds[2] if x_axis else bounds[3]
        existing_center = (existing_low + existing_high) / 2.0
        for value in (
            existing_high - anchor_local_low,
            existing_low - anchor_local_high,
            existing_low - anchor_local_low,
            existing_high - anchor_local_high,
            existing_center - anchor_center,
        ):
            _add_if_in_range(values, value, minimum_center, maximum_center)
    return sorted(values)


def _coarse_axis_values(low: float, high: float, step: float = 10.0) -> list[float]:
    if low > high:
        return []
    values = {round(low, 9), round(high, 9)}
    current = math.ceil(low / step) * step
    while current <= high + 1e-9:
        values.add(round(current, 9))
        current += step
    return sorted(values)


def _candidate_positions(
    tool: ToolObject,
    prototype: ToolPlacement,
    layout: LayoutState,
    existing_geometries: list[_PackingGeometry],
) -> list[ToolPlacement]:
    boundary = usable_boundary_polygon(layout)
    bminx, bminy, bmaxx, bmaxy = boundary.bounds
    existing_bounds = [geometry.search.bounds for geometry in existing_geometries]
    candidates: list[ToolPlacement] = []

    for rotation in rotation_candidates(prototype):
        at_origin = replace(
            prototype,
            x_mm=0.0,
            y_mm=0.0,
            rotation_deg=rotation,
            is_placed=True,
        )
        geometry = _geometry_for(tool, at_origin, layout)
        bound_minx, bound_miny, bound_maxx, bound_maxy = geometry.boundary.bounds
        search_minx, search_miny, search_maxx, search_maxy = geometry.search.bounds

        xs = _axis_candidates(
            bminx,
            bmaxx,
            bound_minx,
            bound_maxx,
            search_minx,
            search_maxx,
            existing_bounds,
            x_axis=True,
        )
        ys = _axis_candidates(
            bminy,
            bmaxy,
            bound_miny,
            bound_maxy,
            search_miny,
            search_maxy,
            existing_bounds,
            x_axis=False,
        )
        for y in ys:
            for x in xs:
                candidates.append(
                    replace(
                        prototype,
                        x_mm=x,
                        y_mm=y,
                        rotation_deg=rotation,
                        is_placed=True,
                    )
                )

        # A bounded coarse fallback catches usable interior pockets that are not
        # represented by simple edge-contact anchors. Border limits are based on
        # cavity + exact grab access, never on tool-to-tool structural spacing.
        min_center_x = bminx - bound_minx
        max_center_x = bmaxx - bound_maxx
        min_center_y = bminy - bound_miny
        max_center_y = bmaxy - bound_maxy
        for y in _coarse_axis_values(min_center_y, max_center_y):
            for x in _coarse_axis_values(min_center_x, max_center_x):
                candidates.append(
                    replace(
                        prototype,
                        x_mm=x,
                        y_mm=y,
                        rotation_deg=rotation,
                        is_placed=True,
                    )
                )

    unique: dict[tuple[float, float, float], ToolPlacement] = {}
    for candidate in candidates:
        key = (
            round(candidate.x_mm, 9),
            round(candidate.y_mm, 9),
            round(candidate.rotation_deg, 9),
        )
        unique[key] = candidate
    return [unique[key] for key in sorted(unique)]


def _best_candidate(
    tool: ToolObject,
    prototype: ToolPlacement,
    layout: LayoutState,
    existing_geometries: list[_PackingGeometry],
) -> tuple[ToolPlacement, _PackingGeometry] | None:
    boundary = usable_boundary_polygon(layout)
    score_geometries = [geometry.boundary for geometry in existing_geometries]
    best: tuple[
        tuple[float, float, float, float, float],
        tuple[float, float, float],
        ToolPlacement,
        _PackingGeometry,
    ] | None = None

    for candidate in _candidate_positions(
        tool,
        prototype,
        layout,
        existing_geometries,
    ):
        geometry = _geometry_for(tool, candidate, layout)
        if not boundary.covers(geometry.boundary):
            continue
        if _conflicts(geometry, existing_geometries):
            continue
        score = candidate_score(candidate, geometry.boundary, score_geometries)
        stable = (-candidate.rotation_deg, -candidate.y_mm, -candidate.x_mm)
        record = (score, stable, candidate, geometry)
        if best is None or record[:2] > best[:2]:
            best = record

    if best is None:
        return None
    return best[2], best[3]


def pack_layout(
    project: Project,
    layout: LayoutState,
    *,
    repack_unlocked_only: bool = False,
) -> PackingResult:
    """Pack tools into a layout deterministically without mutating input state."""

    source = _placement_map(layout)
    working: dict[str, ToolPlacement] = {}
    existing_geometries: list[_PackingGeometry] = []

    for tool in project.tools:
        original = source.get(tool.id, ToolPlacement(tool_id=tool.id))
        if original.locked and original.is_placed:
            copied = replace(original)
            working[tool.id] = copied
            existing_geometries.append(_geometry_for(tool, copied, layout))
        else:
            working[tool.id] = replace(original, is_placed=False)

    unplaced: list[str] = []
    for tool in pack_order(project, layout):
        prototype = working[tool.id]
        if prototype.locked and prototype.is_placed:
            continue

        found = _best_candidate(tool, prototype, layout, existing_geometries)
        if found is None:
            working[tool.id] = replace(prototype, is_placed=False)
            unplaced.append(tool.id)
            continue
        placed, geometry = found
        working[tool.id] = placed
        existing_geometries.append(geometry)

    result_placements = tuple(working[tool.id] for tool in project.tools)
    result_layout = _copy_layout(layout, result_placements)
    result_layout.unplaced_tool_ids = list(unplaced)
    validation = validate_layout(project, result_layout)
    return PackingResult(
        placements=result_placements,
        unplaced_tool_ids=tuple(unplaced),
        validation=validation,
    )
