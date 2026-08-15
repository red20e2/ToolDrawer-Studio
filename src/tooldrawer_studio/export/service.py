from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import cadquery as cq

from tooldrawer_studio.domain.models import Project, ToolObject
from tooldrawer_studio.export.profiles import organizer_profile_loops
from tooldrawer_studio.export.svg import export_organizer_svg
from tooldrawer_studio.export.verification import export_organizer_pdf
from tooldrawer_studio.geometry.pocket import tool_profile

if TYPE_CHECKING:
    from tooldrawer_studio.generation.builder import GenerationResult


@dataclass(frozen=True, slots=True)
class ExportPaths:
    step: Path
    stl: Path
    dxf: Path


ORGANIZER_EXPORT_FORMATS = frozenset({"step", "stl", "dxf", "svg", "pdf"})
DEFAULT_ORGANIZER_EXPORT_FORMATS = ORGANIZER_EXPORT_FORMATS


@dataclass(frozen=True, slots=True)
class OrganizerExportPaths:
    step: Path | None = None
    stl: Path | None = None
    dxf: Path | None = None
    svg: Path | None = None
    pdf: Path | None = None


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


def export_organizer_dxf(project: Project, path: Path) -> Path:
    loops = organizer_profile_loops(project)
    entities = [(loop.layer, list(loop.coordinates)) for loop in loops]
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
    formats: frozenset[str] = DEFAULT_ORGANIZER_EXPORT_FORMATS,
) -> OrganizerExportPaths:
    unknown = formats.difference(ORGANIZER_EXPORT_FORMATS)
    if unknown:
        raise ValueError(f"Unknown organizer export format(s): {', '.join(sorted(unknown))}")
    if not formats:
        raise ValueError("Select at least one organizer export format")
    directory.mkdir(parents=True, exist_ok=True)
    stem = _safe_name(project.name, project.id)
    return OrganizerExportPaths(
        step=(
            export_organizer_step(result.model, directory / f"{stem}.step")
            if "step" in formats
            else None
        ),
        stl=(
            export_organizer_stl(result.model, directory / f"{stem}.stl")
            if "stl" in formats
            else None
        ),
        dxf=(
            export_organizer_dxf(project, directory / f"{stem}.dxf")
            if "dxf" in formats
            else None
        ),
        svg=(
            export_organizer_svg(project, directory / f"{stem}.svg")
            if "svg" in formats
            else None
        ),
        pdf=(
            export_organizer_pdf(project, directory / f"{stem}.pdf")
            if "pdf" in formats
            else None
        ),
    )
