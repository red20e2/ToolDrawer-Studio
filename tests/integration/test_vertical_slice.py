from pathlib import Path

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def test_vertical_slice_from_photo_to_exports(tmp_path: Path):
    controller = WorkflowController()
    controller.import_image(Path("tests/fixtures/simple_tools.png"))
    controller.calibrate_known_distance(PixelPoint(0, 0), PixelPoint(100, 0), known_distance_mm=100.0)
    tools = controller.trace_tools()
    assert len(tools) == 2
    assert tools[0].base_contour_mm is not tools[0].contour_mm
    first = tools[0]
    controller.rename_tool(first.id, "Tool A")
    project_path = tmp_path / "drawer.tds"
    controller.save(project_path)
    reopened = WorkflowController.open(project_path)
    reopened.select_tool(first.id)
    assert reopened.selected_tool().name == "Tool A"
    assert reopened.selected_tool().base_contour_mm == first.base_contour_mm
    reopened.configure_pocket(base_width_mm=300, base_height_mm=200, base_thickness_mm=10, pocket_depth_mm=5)
    outputs = reopened.export_selected_tool(tmp_path / "exports")
    assert outputs.step.exists()
    assert outputs.stl.exists()
    assert outputs.dxf.exists()
    assert outputs.step.stat().st_size > 100
    assert outputs.stl.stat().st_size > 100
    assert outputs.dxf.stat().st_size > 100
