from pathlib import Path

from tooldrawer_studio.calibration.service import PixelPoint, calibrate_known_distance
from tooldrawer_studio.capture.image_loader import load_image
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


def test_tracer_finds_tools_under_gradient_lighting(gradient_tools_image_path: Path):
    image = load_image(gradient_tools_image_path, "capture-1")
    calibration = calibrate_known_distance(
        "capture-1", PixelPoint(0.0, 0.0), PixelPoint(100.0, 0.0), 100.0
    )
    candidates = OpenCVTracer().trace(
        image, calibration, TraceConfig(min_area_mm2=100.0, simplify_mm=0.5)
    )
    assert len(candidates) == 2


def test_tracer_ignores_small_clutter(cluttered_tools_image_path: Path):
    image = load_image(cluttered_tools_image_path, "capture-1")
    calibration = calibrate_known_distance(
        "capture-1", PixelPoint(0.0, 0.0), PixelPoint(100.0, 0.0), 100.0
    )
    candidates = OpenCVTracer().trace(
        image, calibration, TraceConfig(min_area_mm2=100.0, simplify_mm=0.5)
    )
    assert len(candidates) == 2


def test_tracer_finds_low_contrast_tools(low_contrast_tools_image_path: Path):
    image = load_image(low_contrast_tools_image_path, "capture-1")
    calibration = calibrate_known_distance(
        "capture-1", PixelPoint(0.0, 0.0), PixelPoint(100.0, 0.0), 100.0
    )
    candidates = OpenCVTracer().trace(
        image, calibration, TraceConfig(min_area_mm2=100.0, simplify_mm=0.5)
    )
    assert len(candidates) == 2
    assert all(candidate.confidence <= 1.0 for candidate in candidates)


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
