from __future__ import annotations

from dataclasses import dataclass
import math

import cadquery as cq

from tooldrawer_studio.generation.models import GenerationSettings
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


def _continuous_upper_body(layout: LayoutState, body_height_mm: float) -> cq.Workplane:
    gap = PROFILE.pitch_mm - PROFILE.top_footprint_mm
    width = layout.width_mm - gap
    height = layout.height_mm - gap
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
    del settings  # Feature options are applied in Task 7; profile body is deterministic.
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
