from __future__ import annotations

from dataclasses import dataclass

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.generation.gridfinity import PROFILE
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon

PRINT_SCALE_NOTICE = "PRINT AT 100% - DO NOT SCALE"


@dataclass(frozen=True, slots=True)
class ProfileLoop:
    layer: str
    label: str
    coordinates: tuple[tuple[float, float], ...]


def organizer_size_mm(project: Project) -> tuple[float, float]:
    layout = project.layout
    if layout is None:
        raise ValueError("Configure an Arrange layout before exporting a 2D profile")
    return float(layout.width_mm), float(layout.height_mm)


def organizer_outer_boundary(project: Project) -> tuple[tuple[float, float], ...]:
    layout = project.layout
    if layout is None:
        raise ValueError("Configure an Arrange layout before exporting a 2D profile")
    if layout.mode == "gridfinity":
        gap = PROFILE.pitch_mm - PROFILE.top_footprint_mm
        inset = gap / 2.0
        minx = inset
        miny = inset
        maxx = layout.width_mm - inset
        maxy = layout.height_mm - inset
    else:
        minx = 0.0
        miny = 0.0
        maxx = layout.width_mm
        maxy = layout.height_mm
    return ((minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy))


def organizer_profile_loops(project: Project) -> tuple[ProfileLoop, ...]:
    layout = project.layout
    if layout is None:
        raise ValueError("Configure an Arrange layout before exporting a 2D profile")
    tools = {tool.id: tool for tool in project.tools}
    loops = [
        ProfileLoop("OUTER_BOUNDARY", project.name, organizer_outer_boundary(project))
    ]
    cavity_index = 0
    for placement in sorted(layout.placements, key=lambda item: item.tool_id):
        if not placement.is_placed:
            continue
        tool = tools.get(placement.tool_id)
        if tool is None:
            raise ValueError(f"Placement references missing tool: {placement.tool_id}")
        cavity_index += 1
        polygon = oriented_cavity_polygon(tool, placement)
        coordinates = tuple(
            (float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]
        )
        loops.append(
            ProfileLoop(f"CAVITY_{cavity_index:03d}", tool.name, coordinates)
        )
    return tuple(loops)


def loop_centroid(coordinates: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    if not coordinates:
        return (0.0, 0.0)
    xs = [point[0] for point in coordinates]
    ys = [point[1] for point in coordinates]
    return (sum(xs) / len(xs), sum(ys) / len(ys))
