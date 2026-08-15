from pathlib import Path

import cv2
import numpy as np

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.ui.workflow_controller import WorkflowController


def test_known_distance_calibration_guides_normal_controller_tracing(
    tmp_path: Path,
):
    pixels = np.full((300, 500, 3), 240, dtype=np.uint8)
    metal = (65, 65, 65)
    blue = (170, 70, 20)

    cv2.rectangle(pixels, (20, 35), (480, 68), metal, -1)
    cv2.rectangle(pixels, (20, 35), (48, 255), metal, -1)
    cv2.rectangle(pixels, (452, 35), (480, 255), metal, -1)
    cv2.rectangle(pixels, (20, 235), (95, 270), metal, -1)
    cv2.rectangle(pixels, (405, 235), (480, 270), metal, -1)

    cv2.rectangle(pixels, (95, 176), (405, 214), blue, -1)
    cv2.circle(pixels, (95, 195), 19, blue, -1)
    cv2.circle(pixels, (405, 195), 19, blue, -1)

    path = tmp_path / "tool-inside-caliper.png"
    assert cv2.imwrite(str(path), pixels)

    controller = WorkflowController()
    controller.import_image(path)
    controller.calibrate_known_distance(
        PixelPoint(95.0, 195.0), PixelPoint(405.0, 195.0), known_distance_mm=310.0
    )

    tools = controller.trace_tools(allow_low_confidence=True)

    assert tools
    first = tools[0]
    xs = [point.x_mm for point in first.base_contour_mm]
    ys = [point.y_mm for point in first.base_contour_mm]
    assert max(xs) - min(xs) >= 280.0
    assert max(ys) - min(ys) < 70.0


def test_live_known_distance_segment_beats_other_object_on_same_axis(
    tmp_path: Path,
):
    pixels = np.full((300, 500, 3), 240, dtype=np.uint8)
    blue = (170, 70, 20)
    dark = (55, 55, 55)

    # Intended tool sits inside the exact calibration segment, away from image center.
    cv2.rectangle(pixels, (40, 160), (200, 200), blue, -1)
    cv2.circle(pixels, (40, 180), 20, blue, -1)
    cv2.circle(pixels, (200, 180), 20, blue, -1)

    # A larger distractor shares the same infinite calibration axis and covers
    # the image-axis midpoint. Full-axis recovery must not let this object win
    # while the exact live calibration segment is still available.
    cv2.rectangle(pixels, (230, 150), (460, 210), dark, -1)

    path = tmp_path / "two-tools-same-axis.png"
    assert cv2.imwrite(str(path), pixels)

    controller = WorkflowController()
    controller.import_image(path)
    controller.calibrate_known_distance(
        PixelPoint(40.0, 180.0), PixelPoint(200.0, 180.0), known_distance_mm=160.0
    )

    tools = controller.trace_tools(allow_low_confidence=True)

    assert tools
    first = tools[0]
    xs = [point.x_mm for point in first.base_contour_mm]
    ys = [point.y_mm for point in first.base_contour_mm]
    assert min(xs) <= 2.0
    assert 170.0 <= max(xs) <= 190.0
    assert max(ys) - min(ys) < 60.0
