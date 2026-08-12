from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.layout.geometry import (
    boundary_exclusion_geometry,
    grab_access_polygon,
    oriented_cavity_polygon,
    spacing_exclusion_polygon,
    usable_boundary_polygon,
)
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement

_INTERSECTION_AREA_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class LayoutIssue:
    code: str
    message: str
    tool_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LayoutValidationResult:
    valid: bool
    issues: tuple[LayoutIssue, ...]


@dataclass(frozen=True, slots=True)
class _PlacedGeometry:
    tool_id: str
    cavity: BaseGeometry
    spacing: BaseGeometry
    grab: BaseGeometry


def _issue_sort_key(issue: LayoutIssue) -> tuple[str, tuple[str, ...], str]:
    return (issue.code, issue.tool_ids, issue.message)


def _tool_map(project: Project) -> dict[str, ToolObject]:
    return {tool.id: tool for tool in project.tools}


def _has_area_intersection(left: BaseGeometry, right: BaseGeometry) -> bool:
    if left.is_empty or right.is_empty:
        return False
    intersection = left.intersection(right)
    return (
        not intersection.is_empty
        and intersection.area > _INTERSECTION_AREA_TOLERANCE
    )


def _overlap_issue(left_id: str, right_id: str, reason: str) -> LayoutIssue:
    tool_ids = tuple(sorted((left_id, right_id)))
    return LayoutIssue(
        code="overlap",
        message=f"{reason}: {tool_ids[0]} / {tool_ids[1]}",
        tool_ids=tool_ids,
    )


def validate_layout(project: Project, layout: LayoutState) -> LayoutValidationResult:
    """Validate the current layout without modifying any project state."""

    issues: list[LayoutIssue] = []
    tools_by_id = _tool_map(project)
    boundary = usable_boundary_polygon(layout)
    placed: list[_PlacedGeometry] = []

    for placement in layout.placements:
        tool = tools_by_id.get(placement.tool_id)
        if tool is None:
            issues.append(
                LayoutIssue(
                    code="missing_tool",
                    message=f"Placement references missing tool: {placement.tool_id}",
                    tool_ids=(placement.tool_id,),
                )
            )
            continue
        if not placement.is_placed:
            continue

        try:
            cavity = oriented_cavity_polygon(tool, placement)
            spacing = spacing_exclusion_polygon(
                tool,
                placement,
                layout.spacing_mm,
            )
            grab = grab_access_polygon(
                tool,
                placement,
                layout.grab_clearance_mm,
            )
            boundary_geometry = boundary_exclusion_geometry(
                tool,
                placement,
                layout.grab_clearance_mm,
            )
        except ValueError as exc:
            issues.append(
                LayoutIssue(
                    code="invalid_geometry",
                    message=str(exc),
                    tool_ids=(placement.tool_id,),
                )
            )
            continue

        if not boundary.covers(boundary_geometry):
            issues.append(
                LayoutIssue(
                    code="boundary",
                    message=f"{tool.name} exceeds the usable organizer boundary",
                    tool_ids=(placement.tool_id,),
                )
            )
        placed.append(
            _PlacedGeometry(
                tool_id=placement.tool_id,
                cavity=cavity,
                spacing=spacing,
                grab=grab,
            )
        )

    for index, left in enumerate(placed):
        for right in placed[index + 1 :]:
            if _has_area_intersection(left.spacing, right.spacing):
                issues.append(
                    _overlap_issue(
                        left.tool_id,
                        right.tool_id,
                        "Required cavity spacing is violated",
                    )
                )
                continue
            if _has_area_intersection(left.cavity, right.grab) or _has_area_intersection(
                right.cavity,
                left.grab,
            ):
                issues.append(
                    _overlap_issue(
                        left.tool_id,
                        right.tool_id,
                        "Required grab access is obstructed",
                    )
                )

    ordered = tuple(sorted(issues, key=_issue_sort_key))
    return LayoutValidationResult(valid=not ordered, issues=ordered)
