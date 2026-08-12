from __future__ import annotations

from dataclasses import dataclass

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.layout.geometry import (
    candidate_exclusion_geometry,
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


def _issue_sort_key(issue: LayoutIssue) -> tuple[str, tuple[str, ...], str]:
    return (issue.code, issue.tool_ids, issue.message)


def _tool_map(project: Project) -> dict[str, ToolObject]:
    return {tool.id: tool for tool in project.tools}


def _placed_geometry(
    tool: ToolObject,
    placement: ToolPlacement,
    layout: LayoutState,
):
    return candidate_exclusion_geometry(
        tool,
        placement,
        spacing_mm=layout.spacing_mm,
        default_grab_clearance_mm=layout.grab_clearance_mm,
    )


def validate_layout(project: Project, layout: LayoutState) -> LayoutValidationResult:
    """Validate the current layout without modifying any project state."""

    issues: list[LayoutIssue] = []
    tools_by_id = _tool_map(project)
    boundary = usable_boundary_polygon(layout)
    placed: list[tuple[str, object]] = []

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
            exclusion = _placed_geometry(tool, placement, layout)
        except ValueError as exc:
            issues.append(
                LayoutIssue(
                    code="invalid_geometry",
                    message=str(exc),
                    tool_ids=(placement.tool_id,),
                )
            )
            continue

        if not boundary.covers(exclusion):
            issues.append(
                LayoutIssue(
                    code="boundary",
                    message=f"{tool.name} exceeds the usable organizer boundary",
                    tool_ids=(placement.tool_id,),
                )
            )
        placed.append((placement.tool_id, exclusion))

    for index, (left_id, left_geometry) in enumerate(placed):
        for right_id, right_geometry in placed[index + 1 :]:
            intersection = left_geometry.intersection(right_geometry)
            if not intersection.is_empty and intersection.area > _INTERSECTION_AREA_TOLERANCE:
                tool_ids = tuple(sorted((left_id, right_id)))
                issues.append(
                    LayoutIssue(
                        code="overlap",
                        message=f"Required layout exclusion regions overlap: {tool_ids[0]} / {tool_ids[1]}",
                        tool_ids=tool_ids,
                    )
                )

    ordered = tuple(sorted(issues, key=_issue_sort_key))
    return LayoutValidationResult(valid=not ordered, issues=ordered)
