import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import numpy as np
import pytest

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.measurement.models import ImagePoint, ThicknessMeasurementResult
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def _png_bytes(width: int = 420, height: int = 220) -> bytes:
    pixels = np.full((height, width, 3), 245, dtype=np.uint8)
    cv2.rectangle(pixels, (80, 90), (340, 130), (20, 20, 20), -1)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def _add_tool(controller: WorkflowController, capture_id: str) -> ToolObject:
    contour = [
        Point2D(10, 10),
        Point2D(80, 10),
        Point2D(80, 35),
        Point2D(10, 35),
    ]
    tool = ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id=capture_id,
        base_contour_mm=list(contour),
        contour_mm=list(contour),
        trace_confidence=0.94,
    )
    controller.project.tools.append(tool)
    controller.select_tool(tool.id)
    return tool


def _result(thickness: float = 20.0, confidence: float = 0.91) -> ThicknessMeasurementResult:
    return ThicknessMeasurementResult(
        automatic_thickness_mm=thickness,
        confidence=confidence,
        endpoint_a_px=ImagePoint(10.0, 20.0),
        endpoint_b_px=ImagePoint(10.0, 60.0),
        silhouette_px=(
            ImagePoint(5.0, 5.0),
            ImagePoint(30.0, 5.0),
            ImagePoint(30.0, 70.0),
            ImagePoint(5.0, 70.0),
        ),
        warnings=("synthetic fixture",),
    )


class FakeMeasurementService:
    def __init__(self, result: ThicknessMeasurementResult) -> None:
        self.result = result
        self.calls = 0

    def measure(self, _pixels, _calibration) -> ThicknessMeasurementResult:
        self.calls += 1
        return self.result


class ExplodingMeasurementService:
    def measure(self, _pixels, _calibration) -> ThicknessMeasurementResult:
        raise AssertionError("reopen must not run automatic thickness analysis")


def _side_calibration(controller: WorkflowController) -> None:
    tool = controller.selected_tool()
    if tool.side_view_capture_id is None:
        raise AssertionError("test requires an attached side-view capture")
    controller.activate_capture(tool.side_view_capture_id)
    controller.calibrate_known_distance(
        PixelPoint(10, 20),
        PixelPoint(410, 20),
        known_distance_mm=200.0,
    )


def test_measure_state_round_trip_reopens_without_reanalysis(tmp_path: Path):
    service = FakeMeasurementService(_result())
    controller = WorkflowController(measurement_service=service)
    top_capture = controller.import_image_bytes(_png_bytes(), "top.png")
    tool = _add_tool(controller, top_capture)
    side_capture = controller.import_image_bytes(_png_bytes(), "side.png")
    controller.attach_side_view(tool.id, side_capture)
    _side_calibration(controller)

    controller.measure_tool_thickness(tool.id)
    controller.set_thickness_endpoints(
        tool.id, ImagePoint(12.0, 21.0), ImagePoint(12.0, 59.0)
    )
    controller.set_project_measure_defaults(
        exposed_height_mm=4.5,
        bottom_clearance_mm=0.9,
    )
    controller.set_exposed_height_override(tool.id, 3.0)
    controller.set_bottom_clearance_override(tool.id, 1.0)
    controller.set_pocket_depth_override(tool.id, 17.0)

    path = tmp_path / "measured.tds"
    controller.save(path)
    assert service.calls == 1

    reopened = WorkflowController.open(
        path, measurement_service=ExplodingMeasurementService()
    )
    saved = reopened.project.tools[0]

    assert reopened.project.schema_version == 4
    assert saved.side_view_capture_id == side_capture
    assert saved.automatic_thickness_mm == pytest.approx(20.0)
    assert saved.automatic_thickness_confidence == pytest.approx(0.91)
    assert saved.automatic_thickness_endpoint_a_px == ImagePoint(10.0, 20.0)
    assert saved.automatic_thickness_endpoint_b_px == ImagePoint(10.0, 60.0)
    assert saved.corrected_thickness_endpoint_a_px == ImagePoint(12.0, 21.0)
    assert saved.corrected_thickness_endpoint_b_px == ImagePoint(12.0, 59.0)
    assert saved.side_view_silhouette_px == list(_result().silhouette_px)
    assert saved.accepted_thickness_mm == pytest.approx(19.0)
    assert saved.thickness_measurement_mode == "endpoints"
    assert saved.thickness_accepted is True
    assert reopened.project.default_exposed_height_mm == pytest.approx(4.5)
    assert reopened.project.default_bottom_clearance_mm == pytest.approx(0.9)
    assert saved.exposed_height_override_mm == pytest.approx(3.0)
    assert saved.bottom_clearance_override_mm == pytest.approx(1.0)
    assert saved.pocket_depth_override_mm == pytest.approx(17.0)
    assert reopened.resolved_pocket_depth(saved.id) == pytest.approx(17.0)


def test_low_confidence_measurement_stays_blocked_until_explicit_acceptance():
    controller = WorkflowController(
        measurement_service=FakeMeasurementService(_result(18.0, 0.79))
    )
    top_capture = controller.import_image_bytes(_png_bytes(), "top.png")
    tool = _add_tool(controller, top_capture)
    side_capture = controller.import_image_bytes(_png_bytes(), "side.png")
    controller.attach_side_view(tool.id, side_capture)
    _side_calibration(controller)

    controller.measure_tool_thickness(tool.id)

    assert tool.automatic_thickness_mm == pytest.approx(18.0)
    assert tool.thickness_accepted is False
    assert tool.accepted_thickness_mm is None
    assert controller.suggested_pocket_depth(tool.id) is None

    controller.accept_automatic_thickness(tool.id)

    assert tool.thickness_accepted is True
    assert tool.accepted_thickness_mm == pytest.approx(18.0)
    assert controller.suggested_pocket_depth(tool.id) == pytest.approx(14.8)


def test_replacement_and_recalibration_preserve_only_explicit_manual_values():
    controller = WorkflowController()
    top_capture = controller.import_image_bytes(_png_bytes(), "top.png")
    tool = _add_tool(controller, top_capture)
    side_a = controller.import_image_bytes(_png_bytes(), "side-a.png")
    controller.attach_side_view(tool.id, side_a)
    _side_calibration(controller)
    controller.set_thickness_endpoints(
        tool.id, ImagePoint(10.0, 20.0), ImagePoint(10.0, 60.0)
    )

    side_b = controller.import_image_bytes(_png_bytes(), "side-b.png")
    controller.attach_side_view(tool.id, side_b)

    assert tool.automatic_thickness_mm is None
    assert tool.corrected_thickness_endpoint_a_px is None
    assert tool.corrected_thickness_endpoint_b_px is None
    assert tool.accepted_thickness_mm is None
    assert tool.thickness_measurement_mode == "none"

    controller.set_manual_thickness(tool.id, 18.0)
    controller.set_pocket_depth_override(tool.id, 13.5)
    _side_calibration(controller)
    _side_calibration(controller)

    assert tool.accepted_thickness_mm == pytest.approx(18.0)
    assert tool.thickness_measurement_mode == "manual"
    assert tool.thickness_accepted is True
    assert tool.pocket_depth_override_mm == pytest.approx(13.5)
    assert tool.thickness_review_required is True


def test_v1_migrate_save_reopen_preserves_legacy_depth_exactly(tmp_path: Path):
    legacy_path = tmp_path / "legacy.tds"
    payload = {
        "id": "legacy-project",
        "name": "Legacy",
        "schema_version": 1,
        "captures": [],
        "calibrations": [],
        "tools": [
            {
                "id": "legacy-tool",
                "name": "Legacy Tool",
                "source_capture_id": "legacy-capture",
                "base_contour_mm": [
                    {"x_mm": 0.0, "y_mm": 0.0},
                    {"x_mm": 10.0, "y_mm": 0.0},
                    {"x_mm": 10.0, "y_mm": 5.0},
                ],
                "contour_mm": [
                    {"x_mm": 0.0, "y_mm": 0.0},
                    {"x_mm": 10.0, "y_mm": 0.0},
                    {"x_mm": 10.0, "y_mm": 5.0},
                ],
                "clearance_mm": 0.6,
                "depth_mm": 7.625,
                "trace_confidence": 0.8,
            }
        ],
    }
    with ZipFile(legacy_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"format": "tooldrawer-studio", "schema_version": 1}),
        )
        archive.writestr("project.json", json.dumps(payload))

    migrated = WorkflowController.open(legacy_path)
    tool = migrated.project.tools[0]
    assert tool.pocket_depth_override_mm == pytest.approx(7.625)
    assert tool.accepted_thickness_mm is None
    migrated.select_tool(tool.id)
    assert migrated.resolved_pocket_depth(tool.id) == pytest.approx(7.625)

    v4_path = tmp_path / "migrated-v4.tds"
    migrated.save(v4_path)
    with ZipFile(v4_path, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["schema_version"] == 4

    reopened = WorkflowController.open(v4_path)
    reopened.select_tool(tool.id)
    assert reopened.project.schema_version == 4
    assert reopened.project.tools[0].pocket_depth_override_mm == pytest.approx(7.625)
    assert reopened.resolved_pocket_depth(tool.id) == pytest.approx(7.625)
