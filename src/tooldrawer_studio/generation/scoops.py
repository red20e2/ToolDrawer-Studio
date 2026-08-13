from __future__ import annotations

from dataclasses import dataclass
import math

import cadquery as cq
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, box

from tooldrawer_studio.domain.models import ToolObject
from tooldrawer_studio.generation.models import GenerationSettings, ScoopMode
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement

_SHRINK_FACTORS = (1.0, 0.85, 0.70, 0.55)


@dataclass(frozen=True, slots=True)
class ScoopBuildResult:
    cutter: cq.Workplane
    width_mm: float
    depth_mm: float
    shrunk: bool


def effective_scoop_mode(settings: GenerationSettings, tool_id: str) -> ScoopMode:
    if not settings.scoops_enabled:
        return "off"
    mode = settings.tool_scoop_modes.get(tool_id, "auto")
    if mode not in {"auto", "off"}:
        raise ValueError(f"Invalid scoop mode for {tool_id}: {mode}")
    return mode


def _rotate_vector(x: float, y: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(float(degrees))
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return x * cosine - y * sine, x * sine + y * cosine


def _local_cavity(tool: ToolObject, placement: ToolPlacement) -> Polygon:
    cavity = oriented_cavity_polygon(tool, placement)
    translated = translate(cavity, xoff=-placement.x_mm, yoff=-placement.y_mm)
    return rotate(
        translated,
        -placement.rotation_deg,
        origin=(0.0, 0.0),
        use_radians=False,
    )


def _side_geometry(
    tool: ToolObject,
    placement: ToolPlacement,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], float]:
    local = _local_cavity(tool, placement)
    minx, miny, maxx, maxy = local.bounds
    side = placement.grab_side
    if side == "right":
        edge = (maxx, (miny + maxy) / 2.0)
        normal = (1.0, 0.0)
        tangent = (0.0, 1.0)
        span = maxy - miny
    elif side == "left":
        edge = (minx, (miny + maxy) / 2.0)
        normal = (-1.0, 0.0)
        tangent = (0.0, 1.0)
        span = maxy - miny
    elif side == "top":
        edge = ((minx + maxx) / 2.0, maxy)
        normal = (0.0, 1.0)
        tangent = (1.0, 0.0)
        span = maxx - minx
    elif side == "bottom":
        edge = ((minx + maxx) / 2.0, miny)
        normal = (0.0, -1.0)
        tangent = (1.0, 0.0)
        span = maxx - minx
    else:
        raise ValueError(f"Invalid grab side: {side}")

    rotated_edge = _rotate_vector(edge[0], edge[1], placement.rotation_deg)
    world_edge = (
        rotated_edge[0] + placement.x_mm,
        rotated_edge[1] + placement.y_mm,
    )
    return (
        world_edge,
        _rotate_vector(*normal, placement.rotation_deg),
        _rotate_vector(*tangent, placement.rotation_deg),
        float(span),
    )


def _candidate_footprint(
    edge: tuple[float, float],
    normal: tuple[float, float],
    tangent: tuple[float, float],
    width_mm: float,
    depth_mm: float,
) -> Polygon:
    # The rounded trough overlaps the cavity by 0.4 radii and extends 1.6
    # radii into the selected grab direction. Build the corners directly
    # from tangent/normal vectors so left/right handedness cannot flip.
    points: list[tuple[float, float]] = []
    for tangent_offset, normal_offset in (
        (-width_mm / 2.0, -0.4 * depth_mm),
        (width_mm / 2.0, -0.4 * depth_mm),
        (width_mm / 2.0, 1.6 * depth_mm),
        (-width_mm / 2.0, 1.6 * depth_mm),
    ):
        points.append(
            (
                edge[0]
                + tangent[0] * tangent_offset
                + normal[0] * normal_offset,
                edge[1]
                + tangent[1] * tangent_offset
                + normal[1] * normal_offset,
            )
        )
    return Polygon(points)


def _cylinder_cutter(
    edge: tuple[float, float],
    normal: tuple[float, float],
    tangent: tuple[float, float],
    width_mm: float,
    depth_mm: float,
    body_height_mm: float,
) -> cq.Workplane:
    center_x = edge[0] + normal[0] * depth_mm * 0.6
    center_y = edge[1] + normal[1] * depth_mm * 0.6
    start = cq.Vector(
        center_x - tangent[0] * width_mm / 2.0,
        center_y - tangent[1] * width_mm / 2.0,
        body_height_mm,
    )
    direction = cq.Vector(tangent[0], tangent[1], 0.0)
    solid = cq.Solid.makeCylinder(depth_mm, width_mm, start, direction)
    return cq.Workplane(obj=solid)


def build_scoop_cutter(
    tool: ToolObject,
    placement: ToolPlacement,
    layout: LayoutState,
    settings: GenerationSettings,
    body_height_mm: float,
    pocket_depth_mm: float,
) -> ScoopBuildResult | None:
    if effective_scoop_mode(settings, tool.id) == "off" or placement.grab_side == "none":
        return None

    body_height = float(body_height_mm)
    pocket_depth = float(pocket_depth_mm)
    if not math.isfinite(body_height) or body_height <= 0.0:
        raise ValueError("body_height_mm must be finite and positive")
    if not math.isfinite(pocket_depth) or pocket_depth <= 0.0:
        raise ValueError("pocket_depth_mm must be finite and positive")

    available_depth = body_height - float(settings.minimum_floor_mm)
    if available_depth <= 0.0:
        raise ValueError(f"No valid scoop for {tool.name}: minimum floor consumes organizer height")

    edge, normal, tangent, relevant_span = _side_geometry(tool, placement)
    initial_width = min(24.0, max(12.0, 0.45 * relevant_span))
    nominal_depth = min(6.0, pocket_depth)
    initial_depth = min(nominal_depth, available_depth)
    if initial_depth <= 0.0:
        raise ValueError(f"No valid scoop for {tool.name}: insufficient depth above minimum floor")

    wall = float(settings.minimum_wall_mm)
    usable = box(0.0, 0.0, layout.width_mm, layout.height_mm)
    if wall > 0.0:
        usable = usable.buffer(-wall)
    if usable.is_empty:
        raise ValueError(f"No valid scoop for {tool.name}: minimum wall leaves no usable area")

    floor_limited = initial_depth + 1e-9 < nominal_depth
    for factor in _SHRINK_FACTORS:
        width = initial_width * factor
        depth = initial_depth * factor
        footprint = _candidate_footprint(edge, normal, tangent, width, depth)
        if not usable.covers(footprint):
            continue
        cutter = _cylinder_cutter(
            edge,
            normal,
            tangent,
            width,
            depth,
            body_height,
        )
        return ScoopBuildResult(
            cutter=cutter,
            width_mm=width,
            depth_mm=depth,
            shrunk=floor_limited or factor < 1.0,
        )

    raise ValueError(
        f"No valid scoop for {tool.name}: grab-side scoop cannot preserve boundary, wall, and floor limits"
    )
