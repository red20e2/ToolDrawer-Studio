from pathlib import Path
import gc
import weakref

import cv2
import numpy as np
import pytest
from shapely.geometry import Point, Polygon

from tooldrawer_studio.calibration.service import PixelPoint, calibrate_known_distance
from tooldrawer_studio.capture.image_loader import load_image
from tooldrawer_studio.geometry.contour import validate_contour
from tooldrawer_studio.tracing.models import TraceConfig
from tooldrawer_studio.tracing import opencv_tracer
from tooldrawer_studio.tracing.opencv_tracer import (
    OpenCVTracer,
    _focus_color_mask,
    _focus_line_mask,
)


_FOCUSED_PEN_LINE = (PixelPoint(105.0, 170.0), PixelPoint(495.0, 170.0))


def _focused_pen_fixture(
    pen_bgr: tuple[int, int, int],
    *,
    saturated_marking: bool = False,
    full_axis_marking: bool = False,
    include_caliper: bool = True,
    include_shadow: bool = True,
    neutral_reference: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    pixels = np.full((360, 600, 3), 236, dtype=np.uint8)
    pen_mask = np.zeros((360, 600), dtype=np.uint8)
    metal = (78, 78, 78) if neutral_reference else (72, 78, 82)
    shadow = (202, 202, 202) if neutral_reference else (200, 202, 204)

    if include_caliper:
        cv2.rectangle(pixels, (25, 35), (575, 65), metal, -1)
        cv2.rectangle(pixels, (25, 35), (48, 295), metal, -1)
        cv2.rectangle(pixels, (552, 35), (575, 295), metal, -1)
        cv2.rectangle(pixels, (25, 275), (90, 315), metal, -1)
        cv2.rectangle(pixels, (510, 275), (575, 315), metal, -1)

    if include_shadow:
        cv2.rectangle(pixels, (80, 145), (520, 240), shadow, -1)
        cv2.circle(pixels, (80, 192), 47, shadow, -1)
        cv2.circle(pixels, (520, 192), 47, shadow, -1)
        cv2.ellipse(pixels, (300, 260), (205, 15), 0, 0, 360, shadow, -1)
    if saturated_marking:
        cv2.rectangle(pixels, (205, 155), (395, 183), (25, 25, 210), -1)
    if full_axis_marking:
        cv2.rectangle(pixels, (80, 155), (520, 183), (25, 25, 210), -1)

    for target, color in ((pixels, pen_bgr), (pen_mask, 255)):
        cv2.rectangle(target, (105, 200), (495, 230), color, -1)
        cv2.circle(target, (105, 215), 15, color, -1)
        cv2.ellipse(target, (495, 215), (25, 15), 0, -90, 90, color, -1)
        cv2.rectangle(target, (145, 188), (350, 202), color, -1)
    return pixels, pen_mask


def _trace_focused_pen(
    tmp_path: Path,
    pixels: np.ndarray,
    filename: str,
    focus_line: tuple[PixelPoint, PixelPoint] = _FOCUSED_PEN_LINE,
):
    path = tmp_path / filename
    assert cv2.imwrite(str(path), pixels)
    image = load_image(path, "capture-1")
    calibration = calibrate_known_distance(
        "capture-1", focus_line[0], focus_line[1], 390.0
    )
    candidates = OpenCVTracer().trace(
        image,
        calibration,
        TraceConfig(min_area_mm2=100.0, simplify_mm=0.5),
        focus_line_px=focus_line,
    )
    assert candidates
    return candidates[0]


def _candidate_polygon_and_mask(
    candidate,
    focus_line: tuple[PixelPoint, PixelPoint] = _FOCUSED_PEN_LINE,
    *,
    mask_shape: tuple[int, int] = (360, 600),
    pixels_per_mm: float = 1.0,
) -> tuple[Polygon, np.ndarray]:
    validate_contour(candidate.base_contour_mm)
    polygon = Polygon(
        [(point.x_mm, point.y_mm) for point in candidate.base_contour_mm]
    )
    candidate_mask = np.zeros(mask_shape, dtype=np.uint8)
    pixel_vertices = np.asarray(
        [
            [
                round(point.x_mm * pixels_per_mm + focus_line[0].x_px),
                round(point.y_mm * pixels_per_mm + focus_line[0].y_px),
            ]
            for point in candidate.base_contour_mm
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(candidate_mask, [pixel_vertices], 255)
    return polygon, candidate_mask


def _mask_iou(first: np.ndarray, second: np.ndarray) -> float:
    intersection = int(np.count_nonzero((first != 0) & (second != 0)))
    union = int(np.count_nonzero((first != 0) | (second != 0)))
    return float(intersection) / float(union)


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


def test_focus_line_prefers_tool_inside_caliper_fixture(tmp_path: Path):
    pixels = np.full((300, 500, 3), 240, dtype=np.uint8)
    metal = (65, 65, 65)
    blue = (170, 70, 20)

    # A large caliper-like reference fixture surrounds a smaller tool. The global
    # threshold naturally prefers the fixture because it owns far more dark area.
    cv2.rectangle(pixels, (20, 35), (480, 68), metal, -1)
    cv2.rectangle(pixels, (20, 35), (48, 255), metal, -1)
    cv2.rectangle(pixels, (452, 35), (480, 255), metal, -1)
    cv2.rectangle(pixels, (20, 235), (95, 270), metal, -1)
    cv2.rectangle(pixels, (405, 235), (480, 270), metal, -1)

    # The intended tool is a pen-like capsule centered on the known-distance line.
    cv2.rectangle(pixels, (95, 176), (405, 214), blue, -1)
    cv2.circle(pixels, (95, 195), 19, blue, -1)
    cv2.circle(pixels, (405, 195), 19, blue, -1)

    path = tmp_path / "tool-inside-caliper.png"
    assert cv2.imwrite(str(path), pixels)
    image = load_image(path, "capture-1")
    calibration = calibrate_known_distance(
        "capture-1", PixelPoint(95.0, 195.0), PixelPoint(405.0, 195.0), 310.0
    )

    candidates = OpenCVTracer().trace(
        image,
        calibration,
        TraceConfig(min_area_mm2=100.0, simplify_mm=0.5),
        focus_line_px=(PixelPoint(95.0, 195.0), PixelPoint(405.0, 195.0)),
    )

    assert candidates
    first = candidates[0]
    xs = [point.x_mm for point in first.base_contour_mm]
    ys = [point.y_mm for point in first.base_contour_mm]
    assert max(xs) - min(xs) >= 280.0
    assert max(ys) - min(ys) < 70.0


def test_focus_line_returns_colored_pen_not_calibration_corridor(tmp_path: Path):
    pixels, pen_mask = _focused_pen_fixture((168, 72, 24))
    first = _trace_focused_pen(tmp_path, pixels, "blue-pen-inside-caliper.png")
    polygon, candidate_mask = _candidate_polygon_and_mask(first)

    assert polygon.is_valid
    assert polygon.covers(Point(195.0, 45.0))  # blue pen center
    assert not polygon.covers(Point(195.0, 0.0))  # light calibration corridor
    assert not polygon.covers(Point(195.0, -120.0))  # caliper beam
    assert not polygon.covers(Point(195.0, 90.0))  # separate shadow
    min_x, min_y, max_x, max_y = polygon.bounds
    assert 420.0 <= max_x - min_x <= 440.0
    assert 38.0 <= max_y - min_y <= 46.0
    assert 14_000.0 <= polygon.area <= 16_500.0
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94


def test_focus_line_returns_washed_blue_pen_without_corridor_fallback(
    tmp_path: Path,
):
    pixels, pen_mask = _focused_pen_fixture((186, 168, 158))

    first = _trace_focused_pen(tmp_path, pixels, "washed-blue-pen.png")
    polygon, candidate_mask = _candidate_polygon_and_mask(first)

    assert polygon.is_valid
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94
    assert not polygon.covers(Point(195.0, 0.0))


def test_focus_line_returns_six_saturation_blue_pen_without_corridor_fallback(
    tmp_path: Path,
):
    pixels, pen_mask = _focused_pen_fixture(
        (186, 183, 182), neutral_reference=True
    )

    first = _trace_focused_pen(tmp_path, pixels, "six-saturation-blue-pen.png")
    polygon, candidate_mask = _candidate_polygon_and_mask(first)

    assert polygon.is_valid
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94
    assert not polygon.covers(Point(195.0, 0.0))


def test_focus_line_rejects_two_saturation_detached_shadow_cast(
    tmp_path: Path,
):
    focus_line = (PixelPoint(105.0, 255.0), PixelPoint(495.0, 255.0))
    pixels, pen_mask = _focused_pen_fixture(
        (186, 183, 182),
        include_caliper=False,
        include_shadow=False,
        neutral_reference=True,
    )
    # The weak paper cast is closer to the calibration segment than the pen, but
    # it has only an 8-level local value change and is not object foreground.
    cv2.rectangle(pixels, (95, 245), (505, 265), (226, 228, 228), -1)

    first = _trace_focused_pen(
        tmp_path,
        pixels,
        "six-saturation-pen-with-two-saturation-shadow.png",
        focus_line,
    )
    polygon, candidate_mask = _candidate_polygon_and_mask(first, focus_line)

    assert polygon.is_valid
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94
    assert not polygon.covers(Point(195.0, 0.0))  # detached cast midpoint


def test_focus_line_preserves_pen_silhouette_at_phone_photo_resolution(
    tmp_path: Path,
):
    scale = 10
    base_pixels, base_pen_mask = _focused_pen_fixture((168, 72, 24))
    pixels = cv2.resize(
        base_pixels,
        (base_pixels.shape[1] * scale, base_pixels.shape[0] * scale),
        interpolation=cv2.INTER_NEAREST,
    )
    pen_mask = cv2.resize(
        base_pen_mask,
        (base_pen_mask.shape[1] * scale, base_pen_mask.shape[0] * scale),
        interpolation=cv2.INTER_NEAREST,
    )
    focus_line = tuple(
        PixelPoint(point.x_px * scale, point.y_px * scale)
        for point in _FOCUSED_PEN_LINE
    )
    first = _trace_focused_pen(
        tmp_path,
        pixels,
        "phone-resolution-focused-pen.png",
        focus_line,
    )
    polygon, candidate_mask = _candidate_polygon_and_mask(
        first,
        focus_line,
        mask_shape=pen_mask.shape,
        pixels_per_mm=float(scale),
    )

    assert polygon.is_valid
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94
    assert polygon.bounds[3] == pytest.approx(61.0, abs=1.0)


def test_focus_color_mask_declines_tied_low_chroma_components():
    pixels = np.full((300, 600, 3), 236, dtype=np.uint8)
    low_chroma = (186, 183, 182)
    cv2.rectangle(pixels, (95, 105), (505, 125), low_chroma, -1)
    cv2.rectangle(pixels, (95, 175), (505, 195), low_chroma, -1)
    focus_line = (PixelPoint(105.0, 150.0), PixelPoint(495.0, 150.0))

    color_mask, color_attempted = _focus_color_mask(pixels, focus_line)

    assert color_attempted is True
    assert color_mask is None


def test_focus_color_mask_declines_near_tied_low_chroma_components():
    pixels = np.full((300, 600, 3), 236, dtype=np.uint8)
    low_chroma = (186, 183, 182)
    cv2.rectangle(pixels, (95, 105), (505, 125), low_chroma, -1)
    cv2.rectangle(pixels, (94, 175), (505, 195), low_chroma, -1)
    focus_line = (PixelPoint(105.0, 150.0), PixelPoint(495.0, 150.0))

    color_mask, color_attempted = _focus_color_mask(pixels, focus_line)

    assert color_attempted is True
    assert color_mask is None


def test_focus_color_mask_selects_materially_closer_low_chroma_component():
    pixels = np.full((300, 600, 3), 236, dtype=np.uint8)
    low_chroma = (186, 183, 182)
    cv2.rectangle(pixels, (95, 115), (505, 135), low_chroma, -1)
    cv2.rectangle(pixels, (95, 190), (505, 210), low_chroma, -1)
    focus_line = (PixelPoint(105.0, 150.0), PixelPoint(495.0, 150.0))

    color_mask, color_attempted = _focus_color_mask(pixels, focus_line)

    assert color_attempted is True
    assert color_mask is not None
    assert color_mask[125, 300] != 0
    assert color_mask[200, 300] == 0


def test_focus_line_ignores_saturated_fleck_inside_six_saturation_pen(
    tmp_path: Path,
):
    focus_line = (PixelPoint(105.0, 215.0), PixelPoint(495.0, 215.0))
    pixels, pen_mask = _focused_pen_fixture(
        (186, 183, 182), neutral_reference=True
    )
    cv2.rectangle(pixels, (298, 213), (302, 217), (25, 25, 210), -1)

    first = _trace_focused_pen(
        tmp_path,
        pixels,
        "six-saturation-pen-with-saturated-fleck.png",
        focus_line,
    )
    polygon, candidate_mask = _candidate_polygon_and_mask(first, focus_line)

    assert polygon.is_valid
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94
    assert polygon.covers(Point(195.0, 0.0))


def test_focus_line_ignores_saturated_caliper_marking(tmp_path: Path):
    pixels, pen_mask = _focused_pen_fixture(
        (168, 72, 24), saturated_marking=True
    )

    first = _trace_focused_pen(tmp_path, pixels, "marked-caliper-and-blue-pen.png")
    polygon, candidate_mask = _candidate_polygon_and_mask(first)

    assert polygon.is_valid
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94
    assert not polygon.covers(Point(195.0, 0.0))


def test_focus_line_prefers_closer_pen_over_full_axis_saturated_marking(
    tmp_path: Path,
):
    focus_line = (PixelPoint(105.0, 215.0), PixelPoint(495.0, 215.0))
    pixels, pen_mask = _focused_pen_fixture(
        (168, 72, 24), full_axis_marking=True
    )

    first = _trace_focused_pen(
        tmp_path,
        pixels,
        "full-axis-marking-and-blue-pen.png",
        focus_line,
    )
    polygon, candidate_mask = _candidate_polygon_and_mask(first, focus_line)

    assert polygon.is_valid
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94
    assert polygon.covers(Point(195.0, 0.0))


def test_focus_line_prefers_six_saturation_pen_over_full_axis_marking(
    tmp_path: Path,
):
    focus_line = (PixelPoint(105.0, 215.0), PixelPoint(495.0, 215.0))
    pixels, pen_mask = _focused_pen_fixture(
        (186, 183, 182),
        full_axis_marking=True,
        neutral_reference=True,
    )

    first = _trace_focused_pen(
        tmp_path,
        pixels,
        "full-axis-marking-and-six-saturation-pen.png",
        focus_line,
    )
    polygon, candidate_mask = _candidate_polygon_and_mask(first, focus_line)

    assert polygon.is_valid
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94
    assert polygon.covers(Point(195.0, 0.0))


def test_focus_color_component_analysis_scans_only_local_bounds(monkeypatch):
    pixels = np.full((720, 1280, 3), 236, dtype=np.uint8)
    for row in range(8):
        for column in range(16):
            x = 130 + column * 62
            y = 220 + row * 35
            cv2.rectangle(pixels, (x, y), (x + 5, y + 4), (30, 30, 220), -1)
    focus_line = (PixelPoint(100.0, 360.0), PixelPoint(1180.0, 360.0))
    original_nonzero = np.nonzero
    scanned_sizes: list[int] = []

    def record_nonzero(values):
        scanned_sizes.append(int(values.size))
        return original_nonzero(values)

    monkeypatch.setattr(np, "nonzero", record_nonzero)

    color_mask, color_attempted = _focus_color_mask(pixels, focus_line)

    assert color_mask is None
    assert color_attempted
    assert scanned_sizes
    assert max(scanned_sizes) <= 36
    assert sum(scanned_sizes) <= 128 * 36


def test_focused_mask_caps_expensive_processing_to_single_two_megapixel_roi(
    monkeypatch,
):
    pixels = np.full((2000, 3000, 3), 236, dtype=np.uint8)
    cv2.rectangle(pixels, (400, 960), (2600, 1040), (168, 72, 24), -1)
    focus_line = (PixelPoint(350.0, 1000.0), PixelPoint(2650.0, 1000.0))
    hsv_pixels: list[int] = []
    component_pixels: list[int] = []
    grabcut_pixels: list[int] = []
    original_cvt_color = cv2.cvtColor
    original_components = cv2.connectedComponentsWithStats

    def record_cvt_color(image, code, *args, **kwargs):
        if code == cv2.COLOR_BGR2HSV:
            hsv_pixels.append(int(image.shape[0] * image.shape[1]))
        return original_cvt_color(image, code, *args, **kwargs)

    def record_components(image, *args, **kwargs):
        component_pixels.append(int(image.shape[0] * image.shape[1]))
        return original_components(image, *args, **kwargs)

    def record_grabcut(image, mask, *_args, **_kwargs):
        grabcut_pixels.append(int(image.shape[0] * image.shape[1]))

    monkeypatch.setattr(cv2, "cvtColor", record_cvt_color)
    monkeypatch.setattr(cv2, "connectedComponentsWithStats", record_components)
    monkeypatch.setattr(cv2, "grabCut", record_grabcut)

    assert _focus_line_mask(pixels, focus_line) is not None

    assert len(hsv_pixels) == 1
    assert hsv_pixels[0] <= 2_000_000
    assert component_pixels and max(component_pixels) <= 2_000_000
    assert grabcut_pixels and max(grabcut_pixels) <= 2_000_000


def test_focused_trace_releases_global_mask_before_grabcut(
    tmp_path: Path,
    monkeypatch,
):
    pixels, _pen_mask = _focused_pen_fixture(
        (168, 72, 24), include_caliper=False, include_shadow=False
    )
    path = tmp_path / "focused-global-mask-lifetime.png"
    assert cv2.imwrite(str(path), pixels)
    image = load_image(path, "capture-1")
    calibration = calibrate_known_distance(
        "capture-1", _FOCUSED_PEN_LINE[0], _FOCUSED_PEN_LINE[1], 390.0
    )
    global_mask_ref: weakref.ReferenceType[np.ndarray] | None = None
    released_before_grabcut: list[bool] = []

    def tracked_global_mask(source_pixels):
        nonlocal global_mask_ref
        mask = np.zeros(source_pixels.shape[:2], dtype=np.uint8)
        global_mask_ref = weakref.ref(mask)
        return mask

    def observe_grabcut(*_args, **_kwargs):
        gc.collect()
        released_before_grabcut.append(
            global_mask_ref is not None and global_mask_ref() is None
        )

    monkeypatch.setattr(opencv_tracer, "_global_foreground_mask", tracked_global_mask)
    monkeypatch.setattr(cv2, "grabCut", observe_grabcut)

    OpenCVTracer().trace(
        image,
        calibration,
        TraceConfig(min_area_mm2=100.0, simplify_mm=0.5),
        focus_line_px=_FOCUSED_PEN_LINE,
    )

    assert released_before_grabcut == [True]


def test_failed_color_segmentation_does_not_retry_corridor_seed(
    tmp_path: Path,
    monkeypatch,
):
    pixels, pen_mask = _focused_pen_fixture(
        (168, 72, 24), include_caliper=False, include_shadow=False
    )
    original_grabcut = cv2.grabCut
    call_count = 0

    def fail_first_grabcut(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise cv2.error("forced color segmentation failure")
        return original_grabcut(*args, **kwargs)

    monkeypatch.setattr(cv2, "grabCut", fail_first_grabcut)

    first = _trace_focused_pen(tmp_path, pixels, "failed-color-segmentation.png")
    polygon, candidate_mask = _candidate_polygon_and_mask(first)

    assert polygon.is_valid
    assert _mask_iou(candidate_mask, pen_mask) >= 0.94
    assert not polygon.covers(Point(195.0, 0.0))


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
