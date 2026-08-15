from pathlib import Path

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.tracing.opencv_tracer import OpenCVTracer
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def test_known_distance_calibration_forwards_focus_line_to_tracer(
    monkeypatch, simple_tools_image_path: Path
):
    controller = WorkflowController()
    controller.import_image(simple_tools_image_path)
    first = PixelPoint(12.0, 18.0)
    second = PixelPoint(112.0, 18.0)
    controller.calibrate_known_distance(first, second, known_distance_mm=100.0)

    observed: dict[str, object] = {}

    def fake_trace(
        self,
        image,
        calibration,
        config,
        *,
        focus_line_px=None,
    ):
        observed["focus_line_px"] = focus_line_px
        return []

    monkeypatch.setattr(OpenCVTracer, "trace", fake_trace)

    controller.trace_tools(allow_low_confidence=True)

    assert observed["focus_line_px"] == (first, second)
