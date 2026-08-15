from pathlib import Path

from tooldrawer_studio.domain.models import Point2D, Project, ToolObject
from tooldrawer_studio.export.service import (
    export_organizer_dxf,
    export_organizer_package,
    export_tool_package,
)
from tooldrawer_studio.export.svg import export_organizer_svg
from tooldrawer_studio.export.verification import export_organizer_pdf
from tooldrawer_studio.generation.builder import generate_organizer
from tooldrawer_studio.geometry.pocket import PocketSpec, build_pocket_insert
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement


def test_exports_create_nonempty_manufacturing_files(tmp_path: Path):
    contour = [Point2D(10, 10), Point2D(30, 10), Point2D(30, 20), Point2D(10, 20)]
    tool = ToolObject(id="tool-1", name="Block", source_capture_id="capture-1", base_contour_mm=list(contour), contour_mm=list(contour))
    model = build_pocket_insert(tool, PocketSpec(60, 40, 8, 4))
    paths = export_tool_package(model, tool, tmp_path)
    assert paths.step.stat().st_size > 100
    assert paths.stl.stat().st_size > 100
    assert paths.dxf.stat().st_size > 100
    assert paths.step.suffix == ".step"
    assert paths.stl.suffix == ".stl"
    assert paths.dxf.suffix == ".dxf"


def _organizer_project() -> Project:
    contour = [
        Point2D(-10.0, -5.0),
        Point2D(10.0, -5.0),
        Point2D(10.0, 5.0),
        Point2D(-10.0, 5.0),
    ]
    tools = [
        ToolObject(
            id="a",
            name="Ratchet",
            source_capture_id="capture-1",
            base_contour_mm=list(contour),
            contour_mm=list(contour),
            clearance_mm=0.5,
            pocket_depth_override_mm=5.0,
        ),
        ToolObject(
            id="b",
            name="Extension",
            source_capture_id="capture-1",
            base_contour_mm=list(contour),
            contour_mm=list(contour),
            clearance_mm=0.5,
            pocket_depth_override_mm=7.0,
        ),
    ]
    layout = LayoutState(
        mode="foam",
        foam_width_mm=100.0,
        foam_height_mm=60.0,
        placements=[
            ToolPlacement(tool_id="a", x_mm=25.0, y_mm=30.0, is_placed=True),
            ToolPlacement(tool_id="b", x_mm=70.0, y_mm=30.0, is_placed=True),
        ],
        review_required=False,
    )
    return Project(id="drawer-id", name="My Drawer", tools=tools, layout=layout)


def test_export_complete_organizer_package(tmp_path: Path):
    project = _organizer_project()
    result = generate_organizer(project)
    paths = export_organizer_package(result, project, tmp_path)
    assert paths.step is not None and paths.step.exists() and paths.step.stat().st_size > 100
    assert paths.stl is not None and paths.stl.exists() and paths.stl.stat().st_size > 100
    assert paths.dxf is not None and paths.dxf.exists() and paths.dxf.stat().st_size > 100
    assert paths.svg is not None and paths.svg.exists() and paths.svg.stat().st_size > 100
    assert paths.pdf is not None and paths.pdf.exists() and paths.pdf.stat().st_size > 100
    assert paths.step.name == "My_Drawer.step"
    assert paths.stl.name == "My_Drawer.stl"
    assert paths.dxf.name == "My_Drawer.dxf"
    assert paths.svg.name == "My_Drawer.svg"
    assert paths.pdf.name == "My_Drawer.pdf"


def test_dxf_contains_outer_boundary_and_every_cavity(tmp_path: Path):
    project = _organizer_project()
    path = export_organizer_dxf(project, tmp_path / "drawer.dxf")
    text = path.read_text(errors="ignore")
    assert "OUTER_BOUNDARY" in text
    assert "CAVITY_001" in text
    assert "CAVITY_002" in text
    assert text.count("LWPOLYLINE") >= 3


def test_svg_and_pdf_are_true_scale_and_named(tmp_path: Path):
    project = _organizer_project()
    svg = export_organizer_svg(project, tmp_path / "drawer.svg").read_text(encoding="utf-8")
    pdf = export_organizer_pdf(project, tmp_path / "drawer.pdf").read_bytes()
    assert 'width="100.000mm"' in svg
    assert 'height="60.000mm"' in svg
    assert "PRINT AT 100% - DO NOT SCALE" in svg
    assert "Ratchet" in svg
    assert "Extension" in svg
    assert b"PRINT AT 100% - DO NOT SCALE" in pdf
    assert b"Ratchet" in pdf
    assert b"MediaBox" in pdf
