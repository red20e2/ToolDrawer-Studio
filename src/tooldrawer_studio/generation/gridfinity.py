from __future__ import annotations

from dataclasses import dataclass
import math

import cadquery as cq
from shapely.geometry import box

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.generation.cavities import polygon_workplane
from tooldrawer_studio.generation.models import GenerationIssue, GenerationSettings
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon
from tooldrawer_studio.layout.models import LayoutState


@dataclass(frozen=True, slots=True)
class GridfinityProfile:
    pitch_mm: float = 42.0
    top_footprint_mm: float = 41.5
    unit_height_mm: float = 7.0
    base_height_mm: float = 7.0
    base_profile_height_mm: float = 4.75
    top_corner_radius_mm: float = 3.75
    bottom_corner_radius_mm: float = 0.8
    hole_inset_mm: float = 8.0
    stacking_lip_support_mm: float = 1.2
    stacking_lip_guard_mm: float = 0.25
    base_profile: tuple[tuple[float, float], ...] = (
        (0.0, 0.0),
        (0.8, 0.8),
        (0.8, 2.6),
        (2.95, 4.75),
    )
    stacking_lip_profile: tuple[tuple[float, float], ...] = (
        (0.0, 0.0),
        (0.7, 0.7),
        (0.7, 2.5),
        (2.6, 4.4),
    )


@dataclass(frozen=True, slots=True)
class GridfinityFeatureSet:
    magnet_cutters: tuple[cq.Workplane, ...]
    screw_cutters: tuple[cq.Workplane, ...]
    stacking_lip: cq.Workplane | None
    warnings: tuple[GenerationIssue, ...] = ()


PROFILE = GridfinityProfile()


def snap_gridfinity_height(height_mm: float) -> float:
    height = float(height_mm)
    if not math.isfinite(height) or height <= 0.0:
        raise ValueError("Gridfinity height must be finite and positive")
    return math.ceil((height / PROFILE.unit_height_mm) - 1e-12) * PROFILE.unit_height_mm


def gridfinity_cell_centers(layout: LayoutState) -> tuple[tuple[float, float], ...]:
    if layout.mode != "gridfinity":
        raise ValueError("Gridfinity cell centers require gridfinity layout mode")
    if abs(layout.grid_pitch_mm - PROFILE.pitch_mm) > 1e-9:
        raise ValueError("V0.1 Gridfinity generation requires 42.0 mm pitch")
    assert layout.grid_columns is not None
    assert layout.grid_rows is not None
    return tuple(
        (
            (column + 0.5) * PROFILE.pitch_mm,
            (row + 0.5) * PROFILE.pitch_mm,
        )
        for row in range(layout.grid_rows)
        for column in range(layout.grid_columns)
    )


def magnet_centers(layout: LayoutState) -> tuple[tuple[float, float], ...]:
    if layout.mode != "gridfinity":
        raise ValueError("Gridfinity magnet centers require gridfinity layout mode")
    if abs(layout.grid_pitch_mm - PROFILE.pitch_mm) > 1e-9:
        raise ValueError("V0.1 Gridfinity generation requires 42.0 mm pitch")
    assert layout.grid_columns is not None
    assert layout.grid_rows is not None
    points: set[tuple[float, float]] = set()
    for row in range(layout.grid_rows):
        for column in range(layout.grid_columns):
            x0 = column * PROFILE.pitch_mm
            y0 = row * PROFILE.pitch_mm
            for x in (
                x0 + PROFILE.hole_inset_mm,
                x0 + PROFILE.pitch_mm - PROFILE.hole_inset_mm,
            ):
                for y in (
                    y0 + PROFILE.hole_inset_mm,
                    y0 + PROFILE.pitch_mm - PROFILE.hole_inset_mm,
                ):
                    points.add((round(x, 9), round(y, 9)))
    return tuple(sorted(points, key=lambda point: (point[1], point[0])))


def _rounded_wire(
    width_mm: float,
    height_mm: float,
    radius_mm: float,
    z_mm: float,
    center_x_mm: float,
    center_y_mm: float,
) -> cq.Wire:
    half_width = width_mm / 2.0
    half_height = height_mm / 2.0
    points = [
        cq.Vector(center_x_mm - half_width, center_y_mm - half_height, z_mm),
        cq.Vector(center_x_mm + half_width, center_y_mm - half_height, z_mm),
        cq.Vector(center_x_mm + half_width, center_y_mm + half_height, z_mm),
        cq.Vector(center_x_mm - half_width, center_y_mm + half_height, z_mm),
    ]
    raw = cq.Wire.makePolygon(points, close=True)
    return raw.fillet2D(radius_mm, raw.Vertices())


def _base_unit_solid(center_x_mm: float, center_y_mm: float) -> cq.Workplane:
    max_offset = PROFILE.base_profile[-1][0]
    bottom_size = PROFILE.top_footprint_mm - 2.0 * max_offset
    sections: list[cq.Wire] = []
    for radial_offset, z_mm in PROFILE.base_profile:
        width = bottom_size + 2.0 * radial_offset
        radius = PROFILE.bottom_corner_radius_mm + radial_offset
        sections.append(
            _rounded_wire(
                width,
                width,
                radius,
                z_mm,
                center_x_mm,
                center_y_mm,
            )
        )
    return cq.Workplane(obj=cq.Solid.makeLoft(sections, ruled=False))


def _outer_dimensions(layout: LayoutState) -> tuple[float, float]:
    gap = PROFILE.pitch_mm - PROFILE.top_footprint_mm
    return layout.width_mm - gap, layout.height_mm - gap


def _continuous_upper_body(layout: LayoutState, body_height_mm: float) -> cq.Workplane:
    width, height = _outer_dimensions(layout)
    z_start = PROFILE.base_profile_height_mm
    outer = _rounded_wire(
        width,
        height,
        PROFILE.top_corner_radius_mm,
        z_start,
        layout.width_mm / 2.0,
        layout.height_mm / 2.0,
    )
    return (
        cq.Workplane("XY")
        .add(outer)
        .toPending()
        .extrude(body_height_mm - z_start)
    )


def build_gridfinity_body(
    layout: LayoutState,
    body_height_mm: float,
    settings: GenerationSettings,
) -> cq.Workplane:
    del settings
    if layout.mode != "gridfinity":
        raise ValueError("Gridfinity body requires gridfinity layout mode")
    if abs(layout.grid_pitch_mm - PROFILE.pitch_mm) > 1e-9:
        raise ValueError("V0.1 Gridfinity generation requires 42.0 mm pitch")
    height = float(body_height_mm)
    if not math.isfinite(height) or height < PROFILE.base_height_mm:
        raise ValueError(
            f"Gridfinity body height must be at least {PROFILE.base_height_mm:.3f} mm"
        )

    body = _continuous_upper_body(layout, height)
    for center_x, center_y in gridfinity_cell_centers(layout):
        body = body.union(_base_unit_solid(center_x, center_y))
    body = body.clean()
    if len(body.solids().vals()) != 1 or not body.val().isValid():
        raise ValueError("Gridfinity body did not produce one valid solid")
    return body


def _vertical_cylinder(
    center: tuple[float, float],
    diameter_mm: float,
    depth_mm: float,
) -> cq.Workplane:
    solid = cq.Solid.makeCylinder(
        diameter_mm / 2.0,
        depth_mm,
        cq.Vector(center[0], center[1], 0.0),
        cq.Vector(0.0, 0.0, 1.0),
    )
    return cq.Workplane(obj=solid)


def _stacking_lip(layout: LayoutState, body_height_mm: float) -> cq.Workplane:
    outer_width, outer_height = _outer_dimensions(layout)
    lip_height = PROFILE.stacking_lip_profile[-1][1]
    outer_wire = _rounded_wire(
        outer_width,
        outer_height,
        PROFILE.top_corner_radius_mm,
        body_height_mm,
        layout.width_mm / 2.0,
        layout.height_mm / 2.0,
    )
    outer = (
        cq.Workplane("XY")
        .add(outer_wire)
        .toPending()
        .extrude(lip_height)
    )

    inner_sections: list[cq.Wire] = []
    for inward_offset, z_offset in PROFILE.stacking_lip_profile:
        inset = PROFILE.stacking_lip_support_mm + inward_offset
        inner_width = outer_width - 2.0 * inset
        inner_height = outer_height - 2.0 * inset
        if inner_width <= 0.0 or inner_height <= 0.0:
            raise ValueError("Gridfinity stacking lip is too large for the selected layout")
        inner_sections.append(
            _rounded_wire(
                inner_width,
                inner_height,
                max(0.4, PROFILE.top_corner_radius_mm - inset),
                body_height_mm + z_offset,
                layout.width_mm / 2.0,
                layout.height_mm / 2.0,
            )
        )
    inner = cq.Workplane(obj=cq.Solid.makeLoft(inner_sections, ruled=False))
    return outer.cut(inner).clean()


def gridfinity_feature_cutters(
    layout: LayoutState,
    settings: GenerationSettings,
    body_height_mm: float,
) -> GridfinityFeatureSet:
    if layout.mode != "gridfinity":
        raise ValueError("Gridfinity features require gridfinity layout mode")
    height = float(body_height_mm)
    if not math.isfinite(height) or height < PROFILE.base_height_mm:
        raise ValueError(
            f"Gridfinity body height must be at least {PROFILE.base_height_mm:.3f} mm"
        )
    centers = magnet_centers(layout)
    magnets = (
        tuple(
            _vertical_cylinder(center, settings.magnet_diameter_mm, settings.magnet_depth_mm)
            for center in centers
        )
        if settings.magnets_enabled
        else ()
    )
    screws = (
        tuple(
            _vertical_cylinder(
                center,
                settings.screw_diameter_mm,
                min(PROFILE.base_height_mm, height),
            )
            for center in centers
        )
        if settings.screw_holes_enabled
        else ()
    )
    lip = _stacking_lip(layout, height) if settings.stacking_lip_enabled else None
    return GridfinityFeatureSet(magnets, screws, lip)


def stacking_lip_xy_zone(layout: LayoutState):
    if layout.mode != "gridfinity":
        raise ValueError("Stacking lip zone requires gridfinity layout mode")
    outer_width, outer_height = _outer_dimensions(layout)
    x0 = (layout.width_mm - outer_width) / 2.0
    y0 = (layout.height_mm - outer_height) / 2.0
    outer = box(x0, y0, x0 + outer_width, y0 + outer_height)
    maximum_inset = PROFILE.stacking_lip_support_mm + PROFILE.stacking_lip_profile[-1][0]
    inner = outer.buffer(-maximum_inset)
    return outer if inner.is_empty else outer.difference(inner)


def apply_stacking_lip_omissions(
    lip: cq.Workplane | None,
    project: Project,
    body_height_mm: float,
) -> tuple[cq.Workplane | None, tuple[GenerationIssue, ...]]:
    if lip is None or project.layout is None:
        return lip, ()
    zone = stacking_lip_xy_zone(project.layout)
    warnings: list[GenerationIssue] = []
    placements = {placement.tool_id: placement for placement in project.layout.placements}
    result = lip
    lip_height = PROFILE.stacking_lip_profile[-1][1]
    for tool in sorted(project.tools, key=lambda item: item.id):
        placement = placements.get(tool.id)
        if placement is None or not placement.is_placed:
            continue
        cavity = oriented_cavity_polygon(tool, placement)
        if cavity.intersection(zone).area <= 1e-9:
            continue
        guard = cavity.buffer(PROFILE.stacking_lip_guard_mm)
        cutter = polygon_workplane(guard).extrude(lip_height + 0.2).translate(
            (0.0, 0.0, body_height_mm)
        )
        result = result.cut(cutter)
        warnings.append(
            GenerationIssue(
                "stacking_lip_omitted",
                f"{tool.name} overlaps the stacking-lip region; the conflicting lip segment was omitted",
                "warning",
                (tool.id,),
            )
        )
    return result.clean(), tuple(warnings)
