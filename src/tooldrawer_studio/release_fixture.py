from __future__ import annotations

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.generation.models import GenerationSettings
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.persistence.project_archive import ProjectBundle


def _tool(tool_id: str, half_w: float, half_h: float, clearance: float, depth: float) -> ToolObject:
    contour = [
        Point2D(-half_w, -half_h),
        Point2D(half_w, -half_h),
        Point2D(half_w, half_h),
        Point2D(-half_w, half_h),
    ]
    return ToolObject(
        id=tool_id,
        name=f"Fixture {tool_id[-1].upper()}",
        source_capture_id="fixture-capture",
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        clearance_mm=clearance,
        trace_confidence=1.0,
        pocket_depth_override_mm=depth,
    )


def _tools() -> list[ToolObject]:
    return [_tool("fixture-a", 8.0, 3.5, 0.5, 6.0), _tool("fixture-b", 6.0, 4.5, 0.4, 10.0)]


def _placements(a: tuple[float, float], b: tuple[float, float]) -> list[ToolPlacement]:
    return [
        ToolPlacement(tool_id="fixture-a", x_mm=a[0], y_mm=a[1], grab_side="right", is_placed=True),
        ToolPlacement(tool_id="fixture-b", x_mm=b[0], y_mm=b[1], rotation_deg=30.0, is_placed=True),
    ]


def build_release_fixture(mode: str) -> ProjectBundle:
    mode = str(mode).strip().lower()
    if mode == "foam":
        layout = LayoutState(
            mode="foam",
            foam_width_mm=100.0,
            foam_height_mm=70.0,
            placements=_placements((25.0, 25.0), (70.0, 45.0)),
            review_required=False,
        )
        settings = GenerationSettings(magnets_enabled=False, stacking_lip_enabled=False)
    elif mode == "gridfinity":
        layout = LayoutState(
            mode="gridfinity",
            grid_columns=2,
            grid_rows=2,
            placements=_placements((21.0, 21.0), (63.0, 63.0)),
            review_required=False,
        )
        settings = GenerationSettings(screw_holes_enabled=True)
    else:
        raise ValueError("Release fixture mode must be foam or gridfinity")

    project = Project(
        id=f"release-fixture-{mode}",
        name=f"Release Fixture {mode.title()}",
        tools=_tools(),
        layout=layout,
        generation_settings=settings,
    )
    return ProjectBundle(project=project, image_bytes={})
