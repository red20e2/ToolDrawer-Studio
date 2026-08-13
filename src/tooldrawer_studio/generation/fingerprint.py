from __future__ import annotations

import hashlib
import json
import math

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.measurement.depth import final_pocket_depth_mm


def _tool_depth_payload(project: Project, tool: ToolObject) -> dict[str, object]:
    resolved = final_pocket_depth_mm(project, tool)
    return {
        "accepted_thickness_mm": tool.accepted_thickness_mm,
        "thickness_measurement_mode": tool.thickness_measurement_mode,
        "thickness_accepted": tool.thickness_accepted,
        "exposed_height_override_mm": tool.exposed_height_override_mm,
        "bottom_clearance_override_mm": tool.bottom_clearance_override_mm,
        "pocket_depth_override_mm": tool.pocket_depth_override_mm,
        "thickness_review_required": tool.thickness_review_required,
        "resolved_pocket_depth_mm": resolved,
    }


def _generation_settings_payload(project: Project) -> dict[str, object]:
    settings = project.generation_settings
    return {
        "height_mode": settings.height_mode,
        "manual_height_mm": settings.manual_height_mm,
        "minimum_floor_mm": settings.minimum_floor_mm,
        "minimum_wall_mm": settings.minimum_wall_mm,
        "scoops_enabled": settings.scoops_enabled,
        "tool_scoop_modes": dict(sorted(settings.tool_scoop_modes.items())),
        "magnets_enabled": settings.magnets_enabled,
        "magnet_diameter_mm": settings.magnet_diameter_mm,
        "magnet_depth_mm": settings.magnet_depth_mm,
        "screw_holes_enabled": settings.screw_holes_enabled,
        "screw_diameter_mm": settings.screw_diameter_mm,
        "stacking_lip_enabled": settings.stacking_lip_enabled,
        "gridfinity_height_snap": settings.gridfinity_height_snap,
    }


def generation_input_payload(project: Project) -> dict[str, object]:
    """Return canonical geometry/manufacturing inputs for stale-state detection."""

    tools = []
    for tool in sorted(project.tools, key=lambda item: item.id):
        tools.append(
            {
                "id": tool.id,
                "contour_mm": [
                    [float(point.x_mm), float(point.y_mm)] for point in tool.contour_mm
                ],
                "clearance_mm": float(tool.clearance_mm),
                "depth": _tool_depth_payload(project, tool),
            }
        )

    layout_payload: dict[str, object] | None = None
    if project.layout is not None:
        layout = project.layout
        layout_payload = {
            "mode": layout.mode,
            "foam_width_mm": layout.foam_width_mm,
            "foam_height_mm": layout.foam_height_mm,
            "grid_columns": layout.grid_columns,
            "grid_rows": layout.grid_rows,
            "grid_pitch_mm": layout.grid_pitch_mm,
            "grab_clearance_mm": layout.grab_clearance_mm,
            "placements": [
                {
                    "tool_id": placement.tool_id,
                    "x_mm": placement.x_mm,
                    "y_mm": placement.y_mm,
                    "rotation_deg": placement.rotation_deg,
                    "grab_side": placement.grab_side,
                    "grab_clearance_override_mm": placement.grab_clearance_override_mm,
                    "is_placed": placement.is_placed,
                }
                for placement in sorted(layout.placements, key=lambda item: item.tool_id)
            ],
        }

    return {
        "project_measure_defaults": {
            "default_exposed_height_mm": project.default_exposed_height_mm,
            "default_bottom_clearance_mm": project.default_bottom_clearance_mm,
        },
        "tools": tools,
        "layout": layout_payload,
        "generation_settings": _generation_settings_payload(project),
    }


def generation_fingerprint(project: Project) -> str:
    payload = generation_input_payload(project)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _placed_tools_with_depths(project: Project) -> list[tuple[ToolObject, float]]:
    layout = project.layout
    if layout is None:
        raise ValueError("Configure an Arrange layout first")
    tools_by_id = {tool.id: tool for tool in project.tools}
    resolved: list[tuple[ToolObject, float]] = []
    for placement in layout.placements:
        if not placement.is_placed:
            continue
        tool = tools_by_id.get(placement.tool_id)
        if tool is None:
            raise ValueError(f"Placement references missing tool: {placement.tool_id}")
        depth = final_pocket_depth_mm(project, tool)
        if depth is None:
            raise ValueError(f"{tool.name} has no resolved pocket depth")
        numeric = float(depth)
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise ValueError(f"{tool.name} has an invalid resolved pocket depth")
        resolved.append((tool, numeric))
    if not resolved:
        raise ValueError("Place at least one tool before generating")
    return resolved


def required_body_height_mm(project: Project) -> float:
    depths = _placed_tools_with_depths(project)
    floor = float(project.generation_settings.minimum_floor_mm)
    if not math.isfinite(floor) or floor < 0.0:
        raise ValueError("minimum_floor_mm must be finite and non-negative")
    return max(depth for _tool, depth in depths) + floor


def resolve_body_height_mm(project: Project) -> float:
    required = required_body_height_mm(project)
    settings = project.generation_settings
    if settings.height_mode == "manual":
        if settings.manual_height_mm is None:
            raise ValueError("Manual organizer height is required")
        manual = float(settings.manual_height_mm)
        if not math.isfinite(manual) or manual <= 0.0:
            raise ValueError("Manual organizer height must be finite and positive")
        if manual + 1e-9 < required:
            raise ValueError(f"Organizer height must be at least {required:.3f} mm")
        return manual
    if settings.height_mode != "auto":
        raise ValueError("height_mode must be 'auto' or 'manual'")
    if (
        project.layout is not None
        and project.layout.mode == "gridfinity"
        and settings.gridfinity_height_snap
    ):
        return math.ceil((required / 7.0) - 1e-12) * 7.0
    return required
