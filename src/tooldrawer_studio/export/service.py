from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import cadquery as cq

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.generation.gridfinity import PROFILE
from tooldrawer_studio.geometry.pocket import tool_profile
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon

if TYPE_CHECKING:
    from tooldrawer_studio.generation.builder import GenerationResult


@dataclass(frozen=True, slots=True)
class ExportPaths:
    step: Path
    stl: Path
    dxf: Path


@dataclass(frozen=True, slots=True)
class OrganizerExportPaths:
    step: Path | None = None
    stl: Path | None = None
    dxf: Path | None = None


def export_step(model: cq.Workplane, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(model, str(path))
    return path


def export_stl(model: cq.Workplane, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(model, str(path))
    return path


def export_dxf(tool: ToolObject, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.exportDXF(tool_profile(tool), str(path), doc_units=4)
    return path


def _safe_name(value: str, fallback: str) -> str:
    stem = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in value
    ).strip("_")
    return stem or fallback


def _safe_stem(tool: ToolObject) -> str:
    return _safe_name(tool.name, tool.id)


def export_tool_package(model: cq.Workplane, tool: ToolObject, directory: Path) -> ExportPaths:
    directory.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(tool)
    return ExportPaths(
        step=export_step(model, directory / f"{stem}.step"),
        stl=export_stl(model, directory / f"{stem}.stl"),
        dxf=export_dxf(tool, directory / f"{stem}.dxf"),
    )


def export_organizer_step(model: cq.Workplane, path: Path) -> Path:
    return export_step(model, path)


def export_organizer_stl(model: cq.Workplane, path: Path) -> Path:
    return export_stl(model, path)


def _dxf_polyline(layer: str, coordinates: list[tuple[float, float]]) -> list[str]:
    lines = ["0", "LWPOLYLINE", "8", layer, "90", str(len(coordinates)), "70", "1"]
    for x_mm, y_mm in coordinates:
        lines.extend(("10", f"{x_mm:.6f}", "20", f"{y_mm:.6f}"))
    return lines


def _organizer_outer_boundary(project: Project) -> list[tuple[float, float]]:
    layout = project.layout
    if layout is None:
        raise ValueError("Configure an Arrange layout before exporting DXF")
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
    return [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]


def export_organizer_dxf(project: Project, path: Path) -> Path:
    layout = project.layout
    if layout is None:
        raise ValueError("Configure an Arrange layout before exporting DXF")
    tools = {tool.id: tool for tool in project.tools}
    entities: list[tuple[str, list[tuple[float, float]]]] = [
        ("OUTER_BOUNDARY", _organizer_outer_boundary(project))
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
        coordinates = [
            (float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]
        ]
        entities.append((f"CAVITY_{cavity_index:03d}", coordinates))

    layer_names = [layer for layer, _coordinates in entities]
    lines = [
        "0",
        "SECTION",
        "2",
        "HEADER",
        "9",
        "$INSUNITS",
        "70",
        "4",
        "0",
        "ENDSEC",
        "0",
        "SECTION",
        "2",
        "TABLES",
        "0",
        "TABLE",
        "2",
        "LAYER",
        "70",
        str(len(layer_names)),
    ]
    for layer in layer_names:
        lines.extend(("0", "LAYER", "2", layer, "70", "0", "62", "7", "6", "CONTINUOUS"))
    lines.extend(("0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"))
    for layer, coordinates in entities:
        lines.extend(_dxf_polyline(layer, coordinates))
    lines.extend(("0", "ENDSEC", "0", "EOF"))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def export_organizer_package(
    result: GenerationResult,
    project: Project,
    directory: Path,
) -> OrganizerExportPaths:
    directory.mkdir(parents=True, exist_ok=True)
    stem = _safe_name(project.name, project.id)
    return OrganizerExportPaths(
        step=export_organizer_step(result.model, directory / f"{stem}.step"),
        stl=export_organizer_stl(result.model, directory / f"{stem}.stl"),
        dxf=export_organizer_dxf(project, directory / f"{stem}.dxf"),
    )
