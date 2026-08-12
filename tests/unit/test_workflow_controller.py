from pathlib import Path

import cv2
import numpy as np
import pytest

from tooldrawer_studio.calibration.presets import A4
from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def _paper_corners() -> tuple[PixelPoint, PixelPoint, PixelPoint, PixelPoint]:
    return (
        PixelPoint(0, 0),
        PixelPoint(299, 0),
        PixelPoint(299, 199),
        PixelPoint(0, 199),
    )


def test_second_calibration_replaces_active_capture_calibration(simple_tools_image_path: Path):
    controller = WorkflowController()
    capture_id = controller.import_image(simple_tools_image_path)
    controller.calibrate_known_distance(
        PixelPoint(0, 0), PixelPoint(20, 0), known_distance_mm=10.0
    )
    record = controller.calibrate_paper(_paper_corners(), A4)

    matching = [
        item for item in controller.project.calibrations if item.capture_id == capture_id
    ]
    assert matching == [record]
    assert record.method == "paper:a4"
    assert controller.active_calibration is record


def test_low_confidence_calibration_blocks_tracing_without_override(simple_tools_image_path: Path):
    controller = WorkflowController()
    controller.import_image(simple_tools_image_path)
    record = controller.calibrate_known_distance(
        PixelPoint(0, 0), PixelPoint(20, 0), known_distance_mm=10.0
    )
    assert record.confidence < 0.75

    with pytest.raises(ValueError, match="Calibration confidence is too low"):
        controller.trace_tools()

    tools = controller.trace_tools(allow_low_confidence=True)
    assert len(tools) == 2


def test_active_image_display_bytes_match_normalized_capture(simple_tools_image_path: Path):
    controller = WorkflowController()
    capture_id = controller.import_image(simple_tools_image_path)
    capture = next(item for item in controller.project.captures if item.id == capture_id)

    raw = controller.active_image_display_bytes()
    pixels = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert pixels is not None
    assert pixels.shape[1] == capture.width_px
    assert pixels.shape[0] == capture.height_px


def test_save_reopen_restores_active_paper_calibration(
    tmp_path: Path, simple_tools_image_path: Path
):
    controller = WorkflowController()
    controller.import_image(simple_tools_image_path)
    original = controller.calibrate_paper(_paper_corners(), A4)
    assert original.confidence >= 0.75

    path = tmp_path / "calibrated.tds"
    controller.save(path)
    reopened = WorkflowController.open(path)

    assert reopened.active_calibration is not None
    assert reopened.active_calibration.method == "paper:a4"
    assert reopened.active_calibration.confidence == pytest.approx(original.confidence)
    assert len(reopened.trace_tools()) == 2
