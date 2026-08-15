from __future__ import annotations

import cadquery as cq

from tooldrawer_studio.domain.models import ToolObject
from tooldrawer_studio.generation.models import GenerationIssue
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon
from tooldrawer_studio.layout.models import ToolPlacement

_LABEL_FONTS = ("Arial", "Segoe UI", "DejaVu Sans", "Liberation Sans")
_LABEL_DEPTH_MM = 0.6


def _label_text(name: str) -> str:
    cleaned = " ".join(name.split())
    return cleaned[:18] if cleaned else ""


def build_label_cutter(
    tool: ToolObject,
    placement: ToolPlacement,
    depth_mm: float,
    body_height_mm: float,
) -> cq.Workplane | None:
    text = _label_text(tool.name)
    if not text:
        return None
    polygon = oriented_cavity_polygon(tool, placement)
    minx, miny, maxx, maxy = polygon.bounds
    span = min(maxx - minx, maxy - miny)
    if span < 8.0:
        return None
    fontsize = max(3.5, min(7.0, span * 0.22))
    cx, cy = polygon.centroid.x, polygon.centroid.y
    floor_z = body_height_mm - depth_mm
    last_error: Exception | None = None
    for font in _LABEL_FONTS:
        try:
            solid = cq.Workplane("XY").text(
                text,
                fontsize,
                _LABEL_DEPTH_MM,
                cut=False,
                combine=False,
                font=font,
                halign="center",
                valign="center",
            )
            return solid.translate((cx, cy, floor_z - _LABEL_DEPTH_MM + 0.05))
        except Exception as exc:  # noqa: BLE001 - font availability varies by host
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return None


def apply_pocket_labels(
    body: cq.Workplane,
    placed: tuple[tuple[ToolObject, ToolPlacement, float], ...],
    body_height_mm: float,
) -> tuple[cq.Workplane, tuple[GenerationIssue, ...]]:
    warnings: list[GenerationIssue] = []
    for tool, placement, depth in placed:
        try:
            cutter = build_label_cutter(tool, placement, depth, body_height_mm)
        except Exception as exc:
            warnings.append(
                GenerationIssue(
                    "label_skipped",
                    f"Could not engrave a label for {tool.name}: {exc}",
                    "warning",
                    (tool.id,),
                )
            )
            continue
        if cutter is None:
            continue
        try:
            body = body.cut(cutter)
        except Exception as exc:
            warnings.append(
                GenerationIssue(
                    "label_skipped",
                    f"Could not cut a label for {tool.name}: {exc}",
                    "warning",
                    (tool.id,),
                )
            )
    return body, tuple(warnings)
