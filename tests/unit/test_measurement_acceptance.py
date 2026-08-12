import cv2
import numpy as np
import pytest

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.domain.models import Point2D, ToolObject
from tooldrawer_studio.measurement.models import ImagePoint, ThicknessMeasurementResult
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def _png_bytes(width: int = 420, height: int = 220) -> bytes:
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[20:-20, 20:-20] = (255, 255, 255)
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    return encoded.tobytes()


def _result(thickness_mm: float) -> ThicknessMeasurementResult:
    return ThicknessMeasurementResult(
        automatic_thickness_mm=thickness_mm,
        confidence=0.95,
        endpoint_a_px=ImagePoint(10.0, 10.0),
        endpoint_b_px=ImagePoint(10.0, 54.0),
        silhouette_px=(
            ImagePoint(5.0, 5.0),
            ImagePoint(25.0, 5.0),
            ImagePoint(25.0, 60.0),
            ImagePoint(5.0, 60.0),
        ),
    )


class FakeMeasurementService:
    def measure(self, _pixels, _calibration) -> ThicknessMeasurementResult:
        return _result(22.0)


def test_accepting_new_automatic_result_clears_preserved_endpoint_override():
    controller = WorkflowController(measurement_service=FakeMeasurementService())
    top_capture = controller.import_image_bytes(_png_bytes(), "top.png")
    contour = [
        Point2D(0, 0),
        Point2D(20, 0),
        Point2D(20, 10),
        Point2D(0, 10),
    ]
    tool = ToolObject(
        id="tool-1",
        name="Ratchet",
        source_capture_id=top_capture,
        base_contour_mm=list(contour),
        contour_mm=list(contour),
    )
    controller.project.tools.append(tool)
    controller.select_tool(tool.id)

    side_capture = controller.import_image_bytes(_png_bytes(), "side.png")
    controller.attach_side_view(tool.id, side_capture)
    controller.calibrate_known_distance(
        PixelPoint(10, 20), PixelPoint(410, 20), known_distance_mm=200.0
    )
    controller.set_thickness_endpoints(
        tool.id, ImagePoint(10.0, 20.0), ImagePoint(10.0, 60.0)
    )
    assert tool.accepted_thickness_mm == pytest.approx(20.0)
    assert tool.thickness_measurement_mode == "endpoints"

    controller.measure_tool_thickness(tool.id)
    assert tool.accepted_thickness_mm == pytest.approx(20.0)
    assert tool.corrected_thickness_endpoint_a_px == ImagePoint(10.0, 20.0)
    assert tool.corrected_thickness_endpoint_b_px == ImagePoint(10.0, 60.0)
    assert tool.thickness_review_required is True

    controller.accept_automatic_thickness(tool.id)

    assert tool.accepted_thickness_mm == pytest.approx(22.0)
    assert tool.thickness_measurement_mode == "automatic"
    assert tool.thickness_accepted is True
    assert tool.corrected_thickness_endpoint_a_px is None
    assert tool.corrected_thickness_endpoint_b_px is None
    assert tool.thickness_review_required is False
