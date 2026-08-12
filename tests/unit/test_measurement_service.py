import cv2
import numpy as np
import pytest

from tooldrawer_studio.calibration.service import PixelPoint, calibrate_known_distance
from tooldrawer_studio.measurement.models import MIN_AUTOMATIC_THICKNESS_CONFIDENCE
from tooldrawer_studio.measurement.service import ThicknessMeasurementService


def _calibration():
    # 400 px over 200 mm preserves the intended 0.5 mm/px scale while
    # meeting the existing calibration service's high-confidence threshold.
    return calibrate_known_distance(
        "side",
        PixelPoint(10, 20),
        PixelPoint(410, 20),
        200.0,
    )


def _rotated_rectangle() -> np.ndarray:
    image = np.full((220, 420, 3), 245, dtype=np.uint8)
    box = cv2.boxPoints(((210, 110), (260, 40), 12.0)).astype(np.int32)
    cv2.fillConvexPoly(image, box, (20, 20, 20))
    return image


def test_clean_rotated_profile_measures_about_20_mm():
    result = ThicknessMeasurementService().measure(
        _rotated_rectangle(), _calibration()
    )

    assert result.automatic_thickness_mm == pytest.approx(20.0, abs=1.0)
    assert result.confidence >= MIN_AUTOMATIC_THICKNESS_CONFIDENCE
    assert len(result.silhouette_px) >= 4
    assert result.endpoint_a_px != result.endpoint_b_px


def test_tapered_profile_uses_maximum_cross_section():
    image = np.full((220, 420, 3), 245, dtype=np.uint8)
    polygon = np.array(
        [[80, 85], [340, 100], [340, 120], [80, 135]], dtype=np.int32
    )
    cv2.fillConvexPoly(image, polygon, (20, 20, 20))

    result = ThicknessMeasurementService().measure(image, _calibration())

    assert result.automatic_thickness_mm == pytest.approx(25.0, abs=1.0)


def test_boundary_touching_profile_lowers_confidence_and_warns():
    image = np.full((220, 420, 3), 245, dtype=np.uint8)
    cv2.rectangle(image, (0, 90), (300, 130), (20, 20, 20), -1)

    result = ThicknessMeasurementService().measure(image, _calibration())

    assert result.confidence < MIN_AUTOMATIC_THICKNESS_CONFIDENCE
    assert "silhouette touches image boundary" in result.warnings


def test_multiple_similar_profiles_lower_confidence_and_warn():
    image = np.full((220, 420, 3), 245, dtype=np.uint8)
    cv2.rectangle(image, (60, 90), (180, 130), (20, 20, 20), -1)
    cv2.rectangle(image, (240, 90), (360, 130), (20, 20, 20), -1)

    result = ThicknessMeasurementService().measure(image, _calibration())

    assert result.confidence < MIN_AUTOMATIC_THICKNESS_CONFIDENCE
    assert "multiple plausible silhouettes" in result.warnings


def test_low_contrast_profile_is_not_auto_accept_quality():
    image = np.full((220, 420, 3), 130, dtype=np.uint8)
    cv2.rectangle(image, (80, 90), (340, 130), (110, 110, 110), -1)

    result = ThicknessMeasurementService().measure(image, _calibration())

    assert result.confidence < MIN_AUTOMATIC_THICKNESS_CONFIDENCE
    assert "low foreground/background contrast" in result.warnings


def test_uniform_image_has_no_usable_silhouette():
    image = np.full((220, 420, 3), 128, dtype=np.uint8)

    with pytest.raises(ValueError, match="No usable side-profile silhouette"):
        ThicknessMeasurementService().measure(image, _calibration())