from __future__ import annotations

from pathlib import Path

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.export.profiles import (
    PRINT_SCALE_NOTICE,
    loop_centroid,
    organizer_profile_loops,
    organizer_size_mm,
)


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def export_organizer_svg(project: Project, path: Path) -> Path:
    width_mm, height_mm = organizer_size_mm(project)
    loops = organizer_profile_loops(project)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm:.3f}mm" '
            f'height="{height_mm:.3f}mm" viewBox="0 0 {width_mm:.3f} {height_mm:.3f}">'
        ),
        "<desc>ToolDrawer Studio 1:1 verification drawing. Print at 100% / do not scale.</desc>",
        (
            f'<text x="2" y="5" font-size="3.2" font-family="Helvetica, Arial, sans-serif">'
            f"{_xml(PRINT_SCALE_NOTICE)}</text>"
        ),
    ]
    for loop in loops:
        points = " ".join(
            f"{x:.3f},{height_mm - y:.3f}" for x, y in loop.coordinates
        )
        stroke = "#111111" if loop.layer == "OUTER_BOUNDARY" else "#333333"
        parts.append(
            f'<polygon data-layer="{_xml(loop.layer)}" fill="none" stroke="{stroke}" '
            f'stroke-width="0.2" points="{points}"/>'
        )
        if loop.layer.startswith("CAVITY_"):
            cx, cy = loop_centroid(loop.coordinates)
            parts.append(
                f'<text x="{cx:.3f}" y="{height_mm - cy:.3f}" text-anchor="middle" '
                f'font-size="3" font-family="Helvetica, Arial, sans-serif">{_xml(loop.label)}</text>'
            )
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path
