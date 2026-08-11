import pytest

from tooldrawer_studio.calibration.service import (
    PixelPoint,
    calibrate_known_distance,
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
    assert abs(mapped.x_mm - 215.9) < 1e-6
    assert abs(mapped.y_mm - 279.4) < 1e-6


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
