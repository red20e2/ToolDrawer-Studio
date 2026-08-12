import cv2
import numpy as np
import pytest

from tooldrawer_studio.calibration.presets import A4
from tooldrawer_studio.calibration.target import (
    CalibrationTargetSpec,
    calibrate_target,
    detect_target,
    target_svg,
)
from tooldrawer_studio.capture.image_loader import LoadedImage
from tooldrawer_studio.domain.models import CaptureAsset


def _loaded_image(pixels: np.ndarray) -> LoadedImage:
    ok, encoded = cv2.imencode(".png", pixels)
    assert ok
    height, width = pixels.shape[:2]
    asset = CaptureAsset(
        id="capture-target",
        filename="target.png",
        width_px=width,
        height_px=height,
        archive_path="images/capture-target.png",
    )
    return LoadedImage(asset=asset, pixels_bgr=pixels, original_bytes=encoded.tobytes())


def _perspective_target_image() -> LoadedImage:
    source = np.full((1400, 1000, 3), 255, dtype=np.uint8)
    centers = ((100, 100), (900, 100), (900, 1300), (100, 1300))
    half = 35
    for x, y in centers:
        cv2.rectangle(source, (x - half, y - half), (x + half, y + half), (0, 0, 0), -1)

    src = np.float32([[0, 0], [999, 0], [999, 1399], [0, 1399]])
    dst = np.float32([[70, 40], [930, 90], [880, 1360], [120, 1310]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(source, matrix, (1000, 1400), borderValue=(255, 255, 255))
    return _loaded_image(warped)


def test_a4_target_svg_has_physical_page_size_and_four_fiducials():
    svg = target_svg(CalibrationTargetSpec(A4))

    assert 'width="210mm"' in svg
    assert 'height="297mm"' in svg
    assert svg.count("<rect") == 4
    assert "100 mm" in svg


def test_detect_target_orders_four_fiducials_under_perspective():
    detected = detect_target(_perspective_target_image(), CalibrationTargetSpec(A4))

    assert len(detected.corners_px) == 4
    assert detected.confidence >= 0.75
    top_left, top_right, bottom_right, bottom_left = detected.corners_px
    assert top_left.x_px < top_right.x_px
    assert top_left.y_px < bottom_left.y_px
    assert bottom_right.x_px > bottom_left.x_px


def test_calibrate_target_maps_fiducial_span_into_millimetres():
    image = _perspective_target_image()
    spec = CalibrationTargetSpec(A4)
    record = calibrate_target(image.asset.id, image, spec)

    assert record.method == "target:a4"
    assert record.confidence >= 0.75
    width_span = A4.width_mm - 2.0 * spec.inset_mm
    height_span = A4.height_mm - 2.0 * spec.inset_mm

    detected = detect_target(image, spec)
    from tooldrawer_studio.calibration.service import pixel_to_mm

    mapped = pixel_to_mm(record, detected.corners_px[2])
    assert mapped.x_mm == pytest.approx(width_span, abs=0.1)
    assert mapped.y_mm == pytest.approx(height_span, abs=0.1)
