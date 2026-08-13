from __future__ import annotations

import math

from shapely.geometry import box

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.generation.models import (
    GenerationIssue,
    GenerationValidationResult,
)
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon
from tooldrawer_studio.layout.validation import validate_layout
from tooldrawer_studio.measurement.depth import final_pocket_depth_mm

_INTERSECTION_AREA_TOLERANCE = 1e-9
_WARNING_FACTOR = 1.25


def _sort_key(issue: GenerationIssue) -> tuple[str, str, tuple[str, ...], str]:
    return (issue.severity, issue.code, issue.tool_ids, issue.message)


def _error(code: str, message: str, *tool_ids: str) -> GenerationIssue:
    return GenerationIssue(code, message, "error", tuple(sorted(tool_ids)))


def _warning(code: str, message: str, *tool_ids: str) -> GenerationIssue:
    return GenerationIssue(code, message, "warning", tuple(sorted(tool_ids)))


def validate_generation(
    project: Project,
    body_height_mm: float | None = None,
) -> GenerationValidationResult:
    """Validate manufacturing readiness without mutating project state."""

    issues: list[GenerationIssue] = []
    layout = project.layout
    if layout is None:
        return GenerationValidationResult(
            False,
            (_error("layout_missing", "Configure an Arrange layout before generating"),),
        )

    if layout.review_required:
        issues.append(
            _error(
                "layout_review_required",
                "Arrange inputs changed; review the layout before generating",
            )
        )

    try:
        layout_result = validate_layout(project, layout)
    except ValueError as exc:
        issues.append(_error("layout_invalid", str(exc)))
    else:
        for item in layout_result.issues:
            issues.append(
                _error(
                    f"layout_{item.code}",
                    item.message,
                    *item.tool_ids,
                )
            )

    tools_by_id = {tool.id: tool for tool in project.tools}
    placements_by_id = {placement.tool_id: placement for placement in layout.placements}
    placed_geometry: list[tuple[str, str, object]] = []
    depths: dict[str, float] = {}

    for tool in sorted(project.tools, key=lambda item: item.id):
        placement = placements_by_id.get(tool.id)
        if placement is None or not placement.is_placed:
            issues.append(
                _error(
                    "unplaced_tool",
                    f"{tool.name} is not placed in the Arrange layout",
                    tool.id,
                )
            )
            continue
        if tool.thickness_review_required:
            issues.append(
                _error(
                    "depth_review_required",
                    f"{tool.name} thickness/depth requires review",
                    tool.id,
                )
            )
        try:
            depth = final_pocket_depth_mm(project, tool)
        except ValueError as exc:
            issues.append(_error("invalid_depth", f"{tool.name}: {exc}", tool.id))
            depth = None
        if depth is None:
            issues.append(
                _error(
                    "missing_depth",
                    f"{tool.name} has no resolved pocket depth",
                    tool.id,
                )
            )
        else:
            numeric_depth = float(depth)
            if not math.isfinite(numeric_depth) or numeric_depth <= 0.0:
                issues.append(
                    _error(
                        "invalid_depth",
                        f"{tool.name} has an invalid resolved pocket depth",
                        tool.id,
                    )
                )
            else:
                depths[tool.id] = numeric_depth
        try:
            cavity = oriented_cavity_polygon(tool, placement)
        except ValueError as exc:
            issues.append(_error("invalid_geometry", f"{tool.name}: {exc}", tool.id))
        else:
            placed_geometry.append((tool.id, tool.name, cavity))

    for placement in layout.placements:
        if placement.tool_id not in tools_by_id:
            issues.append(
                _error(
                    "missing_tool",
                    f"Placement references missing tool: {placement.tool_id}",
                    placement.tool_id,
                )
            )

    settings = project.generation_settings
    floor = float(settings.minimum_floor_mm)
    wall = float(settings.minimum_wall_mm)
    if not math.isfinite(floor) or floor < 0.0:
        issues.append(_error("minimum_floor", "Minimum floor must be finite and non-negative"))
        floor = 0.0
    if not math.isfinite(wall) or wall < 0.0:
        issues.append(_error("minimum_wall", "Minimum wall must be finite and non-negative"))
        wall = 0.0

    resolved_height: float | None = None
    if body_height_mm is not None:
        resolved_height = float(body_height_mm)
    elif settings.height_mode == "manual":
        resolved_height = (
            None if settings.manual_height_mm is None else float(settings.manual_height_mm)
        )
    elif depths:
        resolved_height = max(depths.values()) + floor
        if layout.mode == "gridfinity" and settings.gridfinity_height_snap:
            resolved_height = math.ceil((resolved_height / 7.0) - 1e-12) * 7.0

    if resolved_height is not None:
        if not math.isfinite(resolved_height) or resolved_height <= 0.0:
            issues.append(_error("body_height", "Organizer height must be finite and positive"))
        else:
            for tool_id, depth in sorted(depths.items()):
                remaining = resolved_height - depth
                if remaining + 1e-9 < floor:
                    name = tools_by_id[tool_id].name
                    required = depth + floor
                    issues.append(
                        _error(
                            "minimum_floor",
                            f"{name}: cavity depth {depth:.3f} mm leaves {remaining:.3f} mm floor; minimum is {floor:.3f} mm. Increase organizer height to at least {required:.3f} mm.",
                            tool_id,
                        )
                    )
    elif settings.height_mode == "manual":
        issues.append(_error("body_height", "Manual organizer height is required"))

    boundary = box(0.0, 0.0, layout.width_mm, layout.height_mm)
    inset_boundary = boundary.buffer(-wall) if wall > 0.0 else boundary
    if wall > 0.0 and inset_boundary.is_empty:
        issues.append(
            _error(
                "minimum_wall",
                "Minimum wall leaves no usable organizer interior",
            )
        )

    for tool_id, name, cavity in placed_geometry:
        if not boundary.covers(cavity):
            issues.append(
                _error(
                    "cavity_boundary",
                    f"{name} cavity breaks through the organizer boundary",
                    tool_id,
                )
            )
            continue
        if wall > 0.0 and not inset_boundary.is_empty and not inset_boundary.covers(cavity):
            issues.append(
                _error(
                    "minimum_wall",
                    f"{name} leaves less than {wall:.3f} mm material at the organizer edge",
                    tool_id,
                )
            )
        elif wall > 0.0:
            edge_distance = cavity.distance(boundary.boundary)
            if wall <= edge_distance < wall * _WARNING_FACTOR:
                issues.append(
                    _warning(
                        "thin_wall_warning",
                        f"{name} edge wall is only {edge_distance:.3f} mm",
                        tool_id,
                    )
                )

    for index, (left_id, left_name, left) in enumerate(placed_geometry):
        for right_id, right_name, right in placed_geometry[index + 1 :]:
            distance = left.distance(right)
            if wall > 0.0:
                left_expanded = left.buffer(wall / 2.0)
                right_expanded = right.buffer(wall / 2.0)
                intersection = left_expanded.intersection(right_expanded)
                if (
                    not intersection.is_empty
                    and intersection.area > _INTERSECTION_AREA_TOLERANCE
                ):
                    issues.append(
                        _error(
                            "minimum_wall",
                            f"{left_name} and {right_name} leave only {distance:.3f} mm between cavities; minimum wall is {wall:.3f} mm",
                            left_id,
                            right_id,
                        )
                    )
                elif wall <= distance < wall * _WARNING_FACTOR:
                    issues.append(
                        _warning(
                            "thin_wall_warning",
                            f"{left_name} and {right_name} leave only {distance:.3f} mm between cavities",
                            left_id,
                            right_id,
                        )
                    )

    ordered = tuple(sorted(issues, key=_sort_key))
    return GenerationValidationResult(
        valid=not any(issue.severity == "error" for issue in ordered),
        issues=ordered,
    )
