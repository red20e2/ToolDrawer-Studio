import pytest

from tooldrawer_studio.calibration.presets import A4, LETTER
from tooldrawer_studio.calibration.service import (
    PixelPoint,
    calibrate_known_distance,
    calibrate_known_object,
    calibrate_paper,
    calibrate_rectangle,
    pixel_to_mm,
)


def test_known_distance_maps_100_pixels_to_50_mm():
    record = calibrate_known_distance(
        capture_id="capture-1",
        pixel_a=PixelPoint(10.0, 10.0),
        pixel_b=PixelPoint(110.0, 10.0),
        known_distance_mm=50.0,
    )

    mapped = pixel_to_mm(record, PixelPoint(110.0, 10.0))
    assert abs(mapped.x_mm - 50.0) < 1e-9
    assert abs(mapped.y_mm - 0.0) < 1e-9


def test_known_distance_rotates_reference_onto_positive_x_axis():
    record = calibrate_known_distance(
        capture_id="capture-1",
        pixel_a=PixelPoint(10.0, 10.0),
        pixel_b=PixelPoint(10.0, 110.0),
        known_distance_mm=50.0,
    )
    mapped = pixel_to_mm(record, PixelPoint(10.0, 110.0))
    assert abs(mapped.x_mm - 50.0) < 1e-9
    assert abs(mapped.y_mm) < 1e-9


def test_rectangle_calibration_maps_letter_width_and_height():
    record = calibrate_rectangle(
        capture_id="capture-1",
        corners_px=(
            PixelPoint(0.0, 0.0),
            PixelPoint(850.0, 0.0),
            PixelPoint(850.0, 1100.0),
            PixelPoint(0.0, 1100.0),
        ),
        width_mm=215.9,
        height_mm=279.4,
    )

    mapped = pixel_to_mm(record, PixelPoint(850.0, 1100.0))
    assert mapped.x_mm == pytest.approx(215.9, abs=1e-5)
    assert mapped.y_mm == pytest.approx(279.4, abs=1e-5)


def test_paper_presets_have_exact_dimensions():
    assert (A4.width_mm, A4.height_mm) == (210.0, 297.0)
    assert (LETTER.width_mm, LETTER.height_mm) == (215.9, 279.4)


def test_a4_calibration_records_named_method():
    corners = (
        PixelPoint(100, 100),
        PixelPoint(900, 120),
        PixelPoint(880, 1200),
        PixelPoint(120, 1180),
    )
    record = calibrate_paper("capture-1", corners, A4)

    assert record.method == "paper:a4"
    assert 0.0 <= record.confidence <= 1.0


def test_known_object_records_method_and_dimensions():
    corners = (
        PixelPoint(10, 10),
        PixelPoint(510, 20),
        PixelPoint(500, 210),
        PixelPoint(20, 200),
    )
    record = calibrate_known_object("capture-1", corners, 100.0, 40.0)

    assert record.method == "known_object"
    mapped = pixel_to_mm(record, corners[2])
    assert mapped.x_mm == pytest.approx(100.0, abs=1e-4)
    assert mapped.y_mm == pytest.approx(40.0, abs=1e-4)


def test_longer_known_distance_reference_has_higher_confidence():
    short = calibrate_known_distance(
        "capture-1", PixelPoint(0, 0), PixelPoint(20, 0), 10.0
    )
    long = calibrate_known_distance(
        "capture-1", PixelPoint(0, 0), PixelPoint(500, 0), 10.0
    )

    assert short.confidence < long.confidence
    assert short.confidence < 0.75
    assert long.confidence >= 0.95


def test_rectangle_rejects_nonconvex_points():
    with pytest.raises(ValueError, match="convex"):
        calibrate_rectangle(
            "capture-1",
            (
                PixelPoint(0, 0),
                PixelPoint(100, 0),
                PixelPoint(20, 20),
                PixelPoint(0, 100),
            ),
            50.0,
            50.0,
        )


def test_calibration_rejects_degenerate_inputs():
    with pytest.raises(ValueError):
        calibrate_known_distance(
            "capture-1", PixelPoint(1, 1), PixelPoint(1, 1), 10.0
        )
    with pytest.raises(ValueError):
        calibrate_known_distance(
            "capture-1", PixelPoint(1, 1), PixelPoint(2, 1), 0.0
        )
    with pytest.raises(ValueError):
        calibrate_rectangle(
            "capture-1",
            (PixelPoint(0, 0), PixelPoint(1, 0), PixelPoint(1, 1), PixelPoint(0, 1)),
            0.0,
            10.0,
        )
