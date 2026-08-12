from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Iterable

from shapely.geometry.base import BaseGeometry

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.layout.geometry import (
    candidate_exclusion_geometry,
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


def _geometry_for(tool: ToolObject, placement: ToolPlacement, layout: LayoutState) -> BaseGeometry:
    return candidate_exclusion_geometry(
        tool,
        placement,
        spacing_mm=layout.spacing_mm,
        default_grab_clearance_mm=layout.grab_clearance_mm,
    )


def _overlaps_any(candidate: BaseGeometry, existing: Iterable[BaseGeometry]) -> bool:
    for other in existing:
        intersection = candidate.intersection(other)
        if not intersection.is_empty and intersection.area > _INTERSECTION_AREA_TOLERANCE:
            return True
    return False


def _add_if_in_range(values: set[float], value: float, low: float, high: float) -> None:
    if value < low - 1e-9 or value > high + 1e-9:
        return
    values.add(round(min(max(value, low), high), 9))


def _axis_candidates(
    low: float,
    high: float,
    local_low: float,
    local_high: float,
    existing_bounds: list[tuple[float, float, float, float]],
    *,
    x_axis: bool,
) -> list[float]:
    minimum_center = low - local_low
    maximum_center = high - local_high
    if minimum_center > maximum_center + 1e-9:
        return []

    values: set[float] = set()
    for value in (minimum_center, maximum_center, (minimum_center + maximum_center) / 2.0):
        _add_if_in_range(values, value, minimum_center, maximum_center)

    local_center = (local_low + local_high) / 2.0
    for bounds in existing_bounds:
        existing_low = bounds[0] if x_axis else bounds[1]
        existing_high = bounds[2] if x_axis else bounds[3]
        existing_center = (existing_low + existing_high) / 2.0
        for value in (
            existing_high - local_low,
            existing_low - local_high,
            existing_low - local_low,
            existing_high - local_high,
            existing_center - local_center,
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
    existing_geometries: list[BaseGeometry],
) -> list[ToolPlacement]:
    boundary = usable_boundary_polygon(layout)
    bminx, bminy, bmaxx, bmaxy = boundary.bounds
    existing_bounds = [geometry.bounds for geometry in existing_geometries]
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
        gminx, gminy, gmaxx, gmaxy = geometry.bounds

        xs = _axis_candidates(
            bminx, bmaxx, gminx, gmaxx, existing_bounds, x_axis=True
        )
        ys = _axis_candidates(
            bminy, bmaxy, gminy, gmaxy, existing_bounds, x_axis=False
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
        # represented by simple edge-contact anchors. It is deterministic and
        # intentionally coarse; edge candidates remain the primary search.
        min_center_x = bminx - gminx
        max_center_x = bmaxx - gmaxx
        min_center_y = bminy - gminy
        max_center_y = bmaxy - gmaxy
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
    existing_geometries: list[BaseGeometry],
) -> tuple[ToolPlacement, BaseGeometry] | None:
    boundary = usable_boundary_polygon(layout)
    best: tuple[tuple[float, float, float, float, float], tuple[float, float, float], ToolPlacement, BaseGeometry] | None = None

    for candidate in _candidate_positions(tool, prototype, layout, existing_geometries):
        geometry = _geometry_for(tool, candidate, layout)
        if not boundary.covers(geometry):
            continue
        if _overlaps_any(geometry, existing_geometries):
            continue
        score = candidate_score(candidate, geometry, existing_geometries)
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
    existing_geometries: list[BaseGeometry] = []
    tools_by_id = {tool.id: tool for tool in project.tools}

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
