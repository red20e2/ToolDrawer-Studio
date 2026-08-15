from __future__ import annotations

from pathlib import Path

from tooldrawer_studio.domain.models import Project
from tooldrawer_studio.export.pdf import write_vector_pdf
from tooldrawer_studio.export.profiles import (
    PRINT_SCALE_NOTICE,
    loop_centroid,
    organizer_profile_loops,
    organizer_size_mm,
)


def export_organizer_pdf(project: Project, path: Path) -> Path:
    width_mm, height_mm = organizer_size_mm(project)
    loops = organizer_profile_loops(project)
    polylines = [loop.coordinates for loop in loops]
    texts: list[tuple[float, float, float, str]] = [
        (2.0, height_mm - 5.0, 9.0, PRINT_SCALE_NOTICE)
    ]
    for loop in loops:
        if not loop.layer.startswith("CAVITY_"):
            continue
        cx, cy = loop_centroid(loop.coordinates)
        texts.append((cx, cy, 8.0, loop.label))
    return write_vector_pdf(path, width_mm, height_mm, polylines, texts)
