from pathlib import Path

from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.export.service import export_tool_package
from tooldrawer_studio.geometry.pocket import PocketSpec, build_pocket_insert


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
