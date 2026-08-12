from __future__ import annotations

from math import isfinite

from tooldrawer_studio.domain.models import Project, ToolObject


def _nonnegative(value: float, label: str) -> float:
    value = float(value)
    if not isfinite(value) or value < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return value


def _positive(value: float, label: str) -> float:
    value = float(value)
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return value


def effective_exposed_height_mm(project: Project, tool: ToolObject) -> float:
    value = (
        project.default_exposed_height_mm
        if tool.exposed_height_override_mm is None
        else tool.exposed_height_override_mm
    )
    return _nonnegative(value, "Exposed height")


def effective_bottom_clearance_mm(project: Project, tool: ToolObject) -> float:
    value = (
        project.default_bottom_clearance_mm
        if tool.bottom_clearance_override_mm is None
        else tool.bottom_clearance_override_mm
    )
    return _nonnegative(value, "Bottom clearance")


def suggested_pocket_depth_mm(project: Project, tool: ToolObject) -> float | None:
    if not tool.thickness_accepted or tool.accepted_thickness_mm is None:
        return None
    thickness = _positive(tool.accepted_thickness_mm, "Accepted thickness")
    depth = (
        thickness
        - effective_exposed_height_mm(project, tool)
        + effective_bottom_clearance_mm(project, tool)
    )
    if not isfinite(depth) or depth <= 0:
        raise ValueError("Measurement settings must produce a positive pocket depth")
    return float(depth)


def final_pocket_depth_mm(project: Project, tool: ToolObject) -> float | None:
    if tool.pocket_depth_override_mm is not None:
        return _positive(tool.pocket_depth_override_mm, "Pocket depth override")
    return suggested_pocket_depth_mm(project, tool)
