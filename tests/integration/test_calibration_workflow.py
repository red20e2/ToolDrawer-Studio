from pathlib import Path

from tooldrawer_studio.calibration.presets import A4
from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def test_paper_calibration_survives_save_reopen_and_traces(
    tmp_path: Path, simple_tools_image_path: Path
):
    controller = WorkflowController()
    controller.import_image(simple_tools_image_path)
    record = controller.calibrate_paper(
        (
            PixelPoint(0, 0),
            PixelPoint(299, 0),
            PixelPoint(299, 199),
            PixelPoint(0, 199),
        ),
        A4,
    )

    assert record.method == "paper:a4"
    assert record.confidence >= 0.75
    assert len(controller.trace_tools()) == 2

    project_path = tmp_path / "paper-calibrated.tds"
    controller.save(project_path)
    reopened = WorkflowController.open(project_path)

    assert reopened.active_calibration is not None
    assert reopened.active_calibration.method == "paper:a4"
    assert len(reopened.trace_tools()) == 2
