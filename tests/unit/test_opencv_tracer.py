from pathlib import Path

import cv2
import numpy as np

from tooldrawer_studio.calibration.service import PixelPoint, calibrate_known_distance
from tooldrawer_studio.capture.image_loader import load_image
from tooldrawer_studio.geometry.contour import validate_contour
from tooldrawer_studio.tracing.models import TraceConfig
from tooldrawer_studio.tracing.opencv_tracer import OpenCVTracer


def test_tracer_returns_two_separate_candidates(simple_tools_image_path: Path):
    image = load_image(simple_tools_image_path, "capture-1")
    calibration = calibrate_known_distance(
        "capture-1", PixelPoint(0.0, 0.0), PixelPoint(100.0, 0.0), 100.0
    )

    candidates = OpenCVTracer().trace(
        image,
        calibration,
        TraceConfig(min_area_mm2=100.0, simplify_mm=0.5),
    )

    assert len(candidates) == 2
    assert all(candidate.area_mm2 > 100.0 for candidate in candidates)
    assert all(len(candidate.base_contour_mm) >= 4 for candidate in candidates)
    assert candidates[0].area_mm2 >= candidates[1].area_mm2


def test_tracer_never_returns_self_intersecting_candidates(tmp_path: Path):
    pixels = np.full((128, 128, 3), 255, dtype=np.uint8)
    black = (0, 0, 0)
    cv2.line(pixels, (17, 23), (59, 70), black, 4)
    cv2.rectangle(pixels, (8, 25), (23, 38), black, -1)
    cv2.line(pixels, (55, 80), (77, 15), black, 4)
    cv2.ellipse(pixels, (16, 72), (9, 12), 108.0, 0.0, 360.0, black, -1)
    cv2.ellipse(pixels, (23, 83), (29, 21), 149.0, 0.0, 360.0, black, -1)
    cv2.rectangle(pixels, (8, 66), (26, 89), black, -1)
    path = tmp_path / "self-touching-foreground.png"
    assert cv2.imwrite(str(path), pixels)

    image = load_image(path, "capture-1")
    calibration = calibrate_known_distance(
        "capture-1", PixelPoint(0.0, 0.0), PixelPoint(100.0, 0.0), 100.0
    )

    candidates = OpenCVTracer().trace(
        image,
        calibration,
        TraceConfig(min_area_mm2=25.0, simplify_mm=0.25),
    )

    assert candidates
    for candidate in candidates:
        validate_contour(candidate.base_contour_mm)


def test_tracer_rejects_nonpositive_configuration(simple_tools_image_path: Path):
    image = load_image(simple_tools_image_path, "capture-1")
    calibration = calibrate_known_distance(
        "capture-1", PixelPoint(0.0, 0.0), PixelPoint(100.0, 0.0), 100.0
    )

    import pytest

    with pytest.raises(ValueError, match="min_area_mm2"):
        OpenCVTracer().trace(image, calibration, TraceConfig(min_area_mm2=0.0))
    with pytest.raises(ValueError, match="simplify_mm"):
        OpenCVTracer().trace(image, calibration, TraceConfig(simplify_mm=-1.0))
