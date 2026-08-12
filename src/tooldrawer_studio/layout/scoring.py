from __future__ import annotations

from collections.abc import Sequence

from shapely.geometry.base import BaseGeometry

from tooldrawer_studio.layout.models import ToolPlacement


def candidate_score(
    placement: ToolPlacement,
    candidate_geometry: BaseGeometry,
    placed_geometries: Sequence[BaseGeometry],
) -> tuple[float, float, float, float, float]:
    """Return a deterministic lexicographic score for one valid candidate.

    Required spacing/grab access is enforced before scoring. This score then
    mildly rewards extra grab access, orthogonal-looking orientations, compact
    occupied area, and stable lower-left placement as deterministic tie-breaks.
    """

    if placement.grab_side == "none" or not placed_geometries:
        access_margin = 0.0
    else:
        access_margin = min(candidate_geometry.distance(item) for item in placed_geometries)

    normalized = placement.rotation_deg % 360.0
    orthogonal_distance = min(
        abs(normalized - value) for value in (0.0, 90.0, 180.0, 270.0, 360.0)
    )
    orientation_quality = -orthogonal_distance

    geometries = [*placed_geometries, candidate_geometry]
    minx = min(item.bounds[0] for item in geometries)
    miny = min(item.bounds[1] for item in geometries)
    maxx = max(item.bounds[2] for item in geometries)
    maxy = max(item.bounds[3] for item in geometries)
    occupied_bbox_area = (maxx - minx) * (maxy - miny)

    return (
        float(access_margin),
        float(orientation_quality),
        -float(occupied_bbox_area),
        -float(placement.y_mm),
        -float(placement.x_mm),
    )
