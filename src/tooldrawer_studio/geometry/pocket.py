from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq

from tooldrawer_studio.domain.models import ToolObject
from tooldrawer_studio.geometry.contour import validate_contour


@dataclass(frozen=True, slots=True)
class PocketSpec:
    base_width_mm: float
    base_height_mm: float
    base_thickness_mm: float
    pocket_depth_mm: float


def tool_profile(tool: ToolObject, apply_clearance: bool = False) -> cq.Workplane:
    validate_contour(tool.contour_mm)
    points = [(point.x_mm, point.y_mm) for point in tool.contour_mm]
    profile = cq.Workplane("XY").polyline(points).close()
    if apply_clearance and tool.clearance_mm > 0:
        profile = profile.offset2D(tool.clearance_mm, kind="arc")
    return profile


def build_pocket_insert(tool: ToolObject, spec: PocketSpec) -> cq.Workplane:
    if spec.base_width_mm <= 0 or spec.base_height_mm <= 0 or spec.base_thickness_mm <= 0:
        raise ValueError("Base dimensions must be positive")
    if spec.pocket_depth_mm <= 0:
        raise ValueError("Pocket depth must be positive")
    if spec.pocket_depth_mm >= spec.base_thickness_mm:
        raise ValueError("Pocket depth must be shallower than base thickness")
    if tool.clearance_mm < 0:
        raise ValueError("Tool clearance must be non-negative")
    base = cq.Workplane("XY").box(spec.base_width_mm, spec.base_height_mm, spec.base_thickness_mm, centered=(False, False, False))
    cavity_profile = tool_profile(tool, apply_clearance=True)
    bounds = cavity_profile.val().BoundingBox()
    margin = 0.5
    if bounds.xmin < margin or bounds.ymin < margin or bounds.xmax > spec.base_width_mm - margin or bounds.ymax > spec.base_height_mm - margin:
        raise ValueError("Tool cavity exceeds base boundary")
    cutter = cavity_profile.extrude(spec.pocket_depth_mm).translate((0.0, 0.0, spec.base_thickness_mm - spec.pocket_depth_mm))
    return base.cut(cutter).clean()
