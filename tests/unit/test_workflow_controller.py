from pathlib import Path

import cv2
import numpy as np
import pytest

from tooldrawer_studio.calibration.presets import A4
from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.measurement.models import ImagePoint, ThicknessMeasurementResult
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def _paper_corners() -> tuple[PixelPoint, PixelPoint, PixelPoint, PixelPoint]:
    return (
        PixelPoint(0, 0),
        PixelPoint(299, 0),
        PixelPoint(299, 199),
        PixelPoint(0, 199),
    )


def _png_bytes(width: int = 41, height: int = 23) -> bytes:
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[3:-3, 5:-5] = (255, 255, 255)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def _add_tool(controller: WorkflowController, capture_id: str) -> ToolObject:
    contour = [
        Point2D(0, 0),
        Point2D(20, 0),
        Point2D(20, 10),
        Point2D(0, 10),
    ]
    tool = ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id=capture_id,
        base_contour_mm=list(contour),
        contour_mm=list(contour),
    )
    controller.project.tools.append(tool)
    controller.select_tool(tool.id)
    return tool


def _fake_result(thickness: float, confidence: float) -> ThicknessMeasurementResult:
    return ThicknessMeasurementResult(
        automatic_thickness_mm=thickness,
        confidence=confidence,
        endpoint_a_px=ImagePoint(10.0, 10.0),
        endpoint_b_px=ImagePoint(10.0, 50.0),
        silhouette_px=(
            ImagePoint(5.0, 5.0),
            ImagePoint(25.0, 5.0),
            ImagePoint(25.0, 55.0),
            ImagePoint(5.0, 55.0),
        ),
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


def test_import_image_bytes_appends_capture_without_resetting_project():
    controller = WorkflowController()
    first = controller.import_image_bytes(_png_bytes(60, 30), "phone.png")
    controller.calibrate_known_distance(
        PixelPoint(0, 0), PixelPoint(20, 0), known_distance_mm=10.0
    )
    first_calibration = controller.active_calibration
    assert first_calibration is not None

    second = controller.import_image_bytes(_png_bytes(30, 12), "webcam.png")

    assert [capture.id for capture in controller.project.captures] == [first, second]
    assert controller.active_capture_id == second
    assert controller.active_calibration is None
    assert [record.capture_id for record in controller.project.calibrations] == [first]


def test_import_image_bytes_uses_decoded_dimensions_for_active_display():
    controller = WorkflowController()

    capture_id = controller.import_image_bytes(_png_bytes(37, 19), "captured.png")
    capture = next(item for item in controller.project.captures if item.id == capture_id)
    display = cv2.imdecode(
        np.frombuffer(controller.active_image_display_bytes(), dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )

    assert (capture.width_px, capture.height_px) == (37, 19)
    assert display is not None
    assert display.shape[:2] == (19, 37)


def test_attach_side_view_and_manual_endpoints_use_side_calibration():
    controller = WorkflowController()
    top_capture_id = controller.import_image_bytes(_png_bytes(60, 30), "top.png")
    tool = _add_tool(controller, top_capture_id)
    side_capture_id = controller.import_image_bytes(_png_bytes(60, 60), "side.png")

    attached = controller.attach_side_view(tool.id, side_capture_id)
    controller.calibrate_known_distance(
        PixelPoint(0, 0), PixelPoint(40, 0), known_distance_mm=20.0
    )
    measured = controller.set_thickness_endpoints(
        tool.id, ImagePoint(10, 10), ImagePoint(10, 30)
    )

    assert attached.source_capture_id == top_capture_id
    assert attached.side_view_capture_id == side_capture_id
    assert measured.accepted_thickness_mm == pytest.approx(10.0)
    assert measured.thickness_measurement_mode == "endpoints"
    assert measured.thickness_accepted is True


def test_automatic_measurement_obeys_confidence_gate_and_manual_precedence(monkeypatch):
    controller = WorkflowController()
    top_capture_id = controller.import_image_bytes(_png_bytes(420, 220), "top.png")
    tool = _add_tool(controller, top_capture_id)
    side_capture_id = controller.import_image_bytes(_png_bytes(420, 220), "side.png")
    controller.attach_side_view(tool.id, side_capture_id)
    controller.calibrate_known_distance(
        PixelPoint(10, 20), PixelPoint(410, 20), known_distance_mm=200.0
    )

    monkeypatch.setattr(
        "tooldrawer_studio.ui.workflow_controller.ThicknessMeasurementService.measure",
        lambda _service, _pixels, _calibration: _fake_result(18.0, 0.91),
    )
    controller.measure_tool_thickness(tool.id)
    assert tool.accepted_thickness_mm == pytest.approx(18.0)
    assert tool.thickness_measurement_mode == "automatic"
    assert tool.thickness_accepted is True

    controller.set_manual_thickness(tool.id, 17.5)
    monkeypatch.setattr(
        "tooldrawer_studio.ui.workflow_controller.ThicknessMeasurementService.measure",
        lambda _service, _pixels, _calibration: _fake_result(22.0, 0.95),
    )
    controller.measure_tool_thickness(tool.id)
    assert tool.automatic_thickness_mm == pytest.approx(22.0)
    assert tool.accepted_thickness_mm == pytest.approx(17.5)
    assert tool.thickness_measurement_mode == "manual"
    assert tool.thickness_review_required is True

    controller.reset_to_automatic_thickness(tool.id)
    monkeypatch.setattr(
        "tooldrawer_studio.ui.workflow_controller.ThicknessMeasurementService.measure",
        lambda _service, _pixels, _calibration: _fake_result(21.0, 0.60),
    )
    controller.measure_tool_thickness(tool.id)
    assert tool.automatic_thickness_mm == pytest.approx(21.0)
    assert tool.accepted_thickness_mm is None
    assert tool.thickness_measurement_mode == "none"
    assert tool.thickness_accepted is False


def test_automatic_reanalysis_preserves_accepted_endpoint_measurement(monkeypatch):
    controller = WorkflowController()
    top_capture_id = controller.import_image_bytes(_png_bytes(420, 220), "top.png")
    tool = _add_tool(controller, top_capture_id)
    side_capture_id = controller.import_image_bytes(_png_bytes(420, 220), "side.png")
    controller.attach_side_view(tool.id, side_capture_id)
    controller.calibrate_known_distance(
        PixelPoint(10, 20), PixelPoint(410, 20), known_distance_mm=200.0
    )
    controller.set_thickness_endpoints(
        tool.id, ImagePoint(10.0, 20.0), ImagePoint(10.0, 60.0)
    )
    assert tool.accepted_thickness_mm == pytest.approx(20.0)
    assert tool.thickness_measurement_mode == "endpoints"

    monkeypatch.setattr(
        "tooldrawer_studio.ui.workflow_controller.ThicknessMeasurementService.measure",
        lambda _service, _pixels, _calibration: _fake_result(22.0, 0.95),
    )
    controller.measure_tool_thickness(tool.id)

    assert tool.automatic_thickness_mm == pytest.approx(22.0)
    assert tool.accepted_thickness_mm == pytest.approx(20.0)
    assert tool.thickness_measurement_mode == "endpoints"
    assert tool.thickness_accepted is True
    assert tool.thickness_review_required is True


def test_replacing_side_view_invalidates_image_measurement_but_preserves_manual_data():
    controller = WorkflowController()
    top_capture_id = controller.import_image_bytes(_png_bytes(60, 30), "top.png")
    tool = _add_tool(controller, top_capture_id)
    side_one = controller.import_image_bytes(_png_bytes(60, 60), "side-1.png")
    controller.attach_side_view(tool.id, side_one)
    controller.calibrate_known_distance(
        PixelPoint(0, 0), PixelPoint(40, 0), known_distance_mm=20.0
    )
    controller.set_thickness_endpoints(
        tool.id, ImagePoint(10, 10), ImagePoint(10, 30)
    )
    controller.set_pocket_depth_override(tool.id, 7.0)

    side_two = controller.import_image_bytes(_png_bytes(60, 60), "side-2.png")
    controller.attach_side_view(tool.id, side_two)

    assert tool.side_view_capture_id == side_two
    assert tool.accepted_thickness_mm is None
    assert tool.thickness_measurement_mode == "none"
    assert tool.pocket_depth_override_mm == pytest.approx(7.0)
    assert tool.thickness_review_required is True

    controller.set_manual_thickness(tool.id, 11.25)
    side_three = controller.import_image_bytes(_png_bytes(60, 60), "side-3.png")
    controller.attach_side_view(tool.id, side_three)

    assert tool.side_view_capture_id == side_three
    assert tool.accepted_thickness_mm == pytest.approx(11.25)
    assert tool.thickness_measurement_mode == "manual"
    assert tool.thickness_accepted is True
    assert tool.thickness_review_required is True


def test_recalibrating_side_view_invalidates_endpoint_measurement():
    controller = WorkflowController()
    top_capture_id = controller.import_image_bytes(_png_bytes(60, 30), "top.png")
    tool = _add_tool(controller, top_capture_id)
    side_capture_id = controller.import_image_bytes(_png_bytes(60, 60), "side.png")
    controller.attach_side_view(tool.id, side_capture_id)
    controller.calibrate_known_distance(
        PixelPoint(0, 0), PixelPoint(40, 0), known_distance_mm=20.0
    )
    controller.set_thickness_endpoints(
        tool.id, ImagePoint(10, 10), ImagePoint(10, 30)
    )

    controller.calibrate_known_distance(
        PixelPoint(0, 0), PixelPoint(50, 0), known_distance_mm=25.0
    )

    assert tool.accepted_thickness_mm is None
    assert tool.thickness_measurement_mode == "none"
    assert tool.corrected_thickness_endpoint_a_px is None
    assert tool.corrected_thickness_endpoint_b_px is None


def test_measure_defaults_and_tool_overrides_drive_suggestion_and_resolution():
    controller = WorkflowController()
    top_capture_id = controller.import_image_bytes(_png_bytes(60, 30), "top.png")
    tool = _add_tool(controller, top_capture_id)
    controller.set_manual_thickness(tool.id, 18.0)

    assert controller.suggested_pocket_depth(tool.id) == pytest.approx(14.8)
    controller.set_project_measure_defaults(exposed_height_mm=3.5, bottom_clearance_mm=1.0)
    assert controller.suggested_pocket_depth(tool.id) == pytest.approx(15.5)

    controller.set_exposed_height_override(tool.id, 2.0)
    controller.set_bottom_clearance_override(tool.id, 0.5)
    assert controller.suggested_pocket_depth(tool.id) == pytest.approx(16.5)

    controller.set_pocket_depth_override(tool.id, 12.25)
    assert controller.resolved_pocket_depth(tool.id) == pytest.approx(12.25)
    controller.set_pocket_depth_override(tool.id, None)
    assert controller.resolved_pocket_depth(tool.id) == pytest.approx(16.5)


def test_configure_pocket_resolves_measure_depth_when_depth_is_omitted():
    controller = WorkflowController()
    capture_id = controller.import_image_bytes(_png_bytes(60, 30), "top.png")
    tool = _add_tool(controller, capture_id)
    controller.set_manual_thickness(tool.id, 18.0)

    controller.configure_pocket(100, 80, 20, pocket_depth_mm=None)

    assert controller._pocket_spec is not None
    assert controller._pocket_spec.pocket_depth_mm == pytest.approx(14.8)


def test_configure_pocket_without_resolved_measure_depth_fails():
    controller = WorkflowController()
    capture_id = controller.import_image_bytes(_png_bytes(60, 30), "top.png")
    _add_tool(controller, capture_id)

    with pytest.raises(ValueError, match="Selected tool has no resolved pocket depth"):
        controller.configure_pocket(100, 80, 20, pocket_depth_mm=None)


def test_configure_pocket_keeps_explicit_depth_compatibility():
    controller = WorkflowController()
    capture_id = controller.import_image_bytes(_png_bytes(60, 30), "top.png")
    _add_tool(controller, capture_id)

    controller.configure_pocket(100, 80, 20, pocket_depth_mm=5.0)

    assert controller._pocket_spec is not None
    assert controller._pocket_spec.pocket_depth_mm == pytest.approx(5.0)
