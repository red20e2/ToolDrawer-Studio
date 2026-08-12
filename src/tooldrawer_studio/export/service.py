from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cadquery as cq

from tooldrawer_studio.domain.models import ToolObject
from tooldrawer_studio.geometry.pocket import tool_profile


@dataclass(frozen=True, slots=True)
class ExportPaths:
    step: Path
    stl: Path
    dxf: Path


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


def _safe_stem(tool: ToolObject) -> str:
    stem = "".join(character if character.isalnum() or character in "-_" else "_" for character in tool.name).strip("_")
    return stem or tool.id


def export_tool_package(model: cq.Workplane, tool: ToolObject, directory: Path) -> ExportPaths:
    directory.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(tool)
    return ExportPaths(step=export_step(model, directory / f"{stem}.step"), stl=export_stl(model, directory / f"{stem}.stl"), dxf=export_dxf(tool, directory / f"{stem}.dxf"))
