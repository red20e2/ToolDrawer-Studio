from __future__ import annotations

from math import hypot

import cv2
import numpy as np

from tooldrawer_studio.calibration.service import PixelPoint
from tooldrawer_studio.domain.models import CalibrationRecord, Point2D
from tooldrawer_studio.measurement.models import ImagePoint


def lighting_normalize(gray: np.ndarray) -> np.ndarray:
    """Reduce uneven illumination while preserving local tool/background contrast."""
    if gray.ndim != 2:
        raise ValueError("Lighting normalization requires a grayscale image")
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _border_foreground_count(mask: np.ndarray) -> int:
    border = np.concatenate((mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]))
    return int(np.count_nonzero(border))


def select_foreground_mask(binary: np.ndarray, inverse: np.ndarray) -> np.ndarray:
    binary_border = _border_foreground_count(binary)
    inverse_border = _border_foreground_count(inverse)
    if binary_border < inverse_border:
        return binary
    if inverse_border < binary_border:
        return inverse
    binary_coverage = float(np.count_nonzero(binary)) / float(binary.size)
    inverse_coverage = float(np.count_nonzero(inverse)) / float(inverse.size)
    if binary_coverage < 0.5 <= inverse_coverage:
        return binary
    if inverse_coverage < 0.5 <= binary_coverage:
        return inverse
    return binary if binary_coverage <= inverse_coverage else inverse


def foreground_mask(pixels_bgr: np.ndarray) -> np.ndarray:
    """Build a single foreground mask from CLAHE, Otsu, adaptive threshold, and Canny."""
    if pixels_bgr.ndim != 3 or pixels_bgr.shape[2] != 3 or pixels_bgr.size == 0:
        raise ValueError("Foreground extraction requires a non-empty BGR image")

    gray = cv2.cvtColor(pixels_bgr, cv2.COLOR_BGR2GRAY)
    normalized = lighting_normalize(gray)
    blurred = cv2.GaussianBlur(normalized, (5, 5), 0)

    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_mask = select_foreground_mask(otsu, cv2.bitwise_not(otsu))

    block = 31 if min(blurred.shape[:2]) >= 31 else 15
    if block % 2 == 0:
        block += 1
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block,
        5,
    )
    adaptive_mask = select_foreground_mask(adaptive, cv2.bitwise_not(adaptive))

    fused = cv2.bitwise_and(otsu_mask, adaptive_mask)
    fused_coverage = float(np.count_nonzero(fused)) / float(fused.size)
    otsu_coverage = float(np.count_nonzero(otsu_mask)) / float(otsu_mask.size)
    if fused_coverage < 0.002 or fused_coverage < 0.15 * max(otsu_coverage, 1e-9):
        fused = otsu_mask

    edges = cv2.Canny(blurred, 40, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    edge_band = cv2.dilate(edges, kernel, iterations=1)
    closed = cv2.morphologyEx(fused, cv2.MORPH_CLOSE, kernel, iterations=1)
    fused = cv2.bitwise_or(fused, cv2.bitwise_and(edge_band, closed))
    fused = cv2.morphologyEx(fused, cv2.MORPH_OPEN, kernel, iterations=1)
    fused = cv2.morphologyEx(fused, cv2.MORPH_CLOSE, kernel, iterations=1)
    return fused


def canny_edges(pixels_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(pixels_bgr, cv2.COLOR_BGR2GRAY)
    normalized = lighting_normalize(gray)
    blurred = cv2.GaussianBlur(normalized, (5, 5), 0)
    return cv2.Canny(blurred, 40, 120)


def refine_corner_subpixel(
    gray: np.ndarray, x_px: float, y_px: float, *, max_shift_px: float = 6.0
) -> tuple[float, float]:
    """Snap a clicked point to a nearby corner when local contrast supports it."""
    if gray.ndim != 2 or gray.size == 0:
        return float(x_px), float(y_px)
    height, width = gray.shape[:2]
    if not (2.0 <= x_px < width - 2.0 and 2.0 <= y_px < height - 2.0):
        return float(x_px), float(y_px)

    x0 = max(0, int(x_px) - 5)
    x1 = min(width, int(x_px) + 6)
    y0 = max(0, int(y_px) - 5)
    y1 = min(height, int(y_px) + 6)
    patch = gray[y0:y1, x0:x1]
    if patch.size == 0 or float(patch.std()) < 4.0:
        return float(x_px), float(y_px)

    corners = np.array([[[float(x_px), float(y_px)]]], dtype=np.float32)
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        40,
        0.01,
    )
    refined = cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1), criteria)
    rx = float(refined[0, 0, 0])
    ry = float(refined[0, 0, 1])
    if hypot(rx - x_px, ry - y_px) > max_shift_px:
        return float(x_px), float(y_px)
    rx = min(max(rx, 0.0), float(width - 1))
    ry = min(max(ry, 0.0), float(height - 1))
    return rx, ry


def snap_to_polyline(
    point: ImagePoint, polyline: list[ImagePoint]
) -> ImagePoint:
    if len(polyline) < 2:
        return point
    best = polyline[0]
    best_distance = hypot(point.x_px - best.x_px, point.y_px - best.y_px)
    closed = list(polyline) + [polyline[0]]
    for start, end in zip(closed, closed[1:]):
        dx = end.x_px - start.x_px
        dy = end.y_px - start.y_px
        length2 = dx * dx + dy * dy
        if length2 <= 1e-12:
            candidate = start
        else:
            t = (
                (point.x_px - start.x_px) * dx + (point.y_px - start.y_px) * dy
            ) / length2
            t = max(0.0, min(1.0, t))
            candidate = ImagePoint(start.x_px + t * dx, start.y_px + t * dy)
        distance = hypot(point.x_px - candidate.x_px, point.y_px - candidate.y_px)
        if distance < best_distance:
            best = candidate
            best_distance = distance
    return best


def contour_contrast(gray: np.ndarray, contour: np.ndarray) -> float:
    selected = np.zeros(gray.shape, dtype=np.uint8)
    cv2.drawContours(selected, [contour], -1, 255, thickness=cv2.FILLED)
    foreground = gray[selected > 0]
    background = gray[selected == 0]
    if foreground.size == 0 or background.size == 0:
        return 0.0
    return abs(float(foreground.mean()) - float(background.mean()))


def min_area_rect_elongation(contour: np.ndarray) -> float:
    if len(contour) < 5:
        return 1.0
    _center, (width, height), _angle = cv2.minAreaRect(contour)
    short = min(float(width), float(height))
    long = max(float(width), float(height))
    if short <= 1e-6:
        return 1.0
    return long / short


def warp_pixels_to_mm(
    pixels_bgr: np.ndarray,
    calibration: CalibrationRecord,
    *,
    pixels_per_mm: float = 4.0,
) -> tuple[np.ndarray, float, float, float]:
    """Warp a photo into millimetre scene space.

    Returns (warped BGR image, origin_x_mm, origin_y_mm, pixels_per_mm).
    Place the pixmap at (origin_x_mm, origin_y_mm) and scale by 1/pixels_per_mm.
    """
    if pixels_per_mm <= 0:
        raise ValueError("pixels_per_mm must be positive")
    height, width = pixels_bgr.shape[:2]
    matrix = np.asarray(calibration.matrix_3x3, dtype=np.float64)
    corners = np.array(
        [[0.0, 0.0, 1.0], [width, 0.0, 1.0], [width, height, 1.0], [0.0, height, 1.0]],
        dtype=np.float64,
    )
    mapped = (matrix @ corners.T).T
    if np.any(np.abs(mapped[:, 2]) < 1e-12):
        raise ValueError("Calibration transform maps the photo to infinity")
    mapped = mapped[:, :2] / mapped[:, 2:3]
    if not np.isfinite(mapped).all():
        raise ValueError("Calibration produced non-finite photo bounds")
    xmin = float(mapped[:, 0].min())
    ymin = float(mapped[:, 1].min())
    xmax = float(mapped[:, 0].max())
    ymax = float(mapped[:, 1].max())
    dest_width = max(1, int(np.ceil((xmax - xmin) * pixels_per_mm)))
    dest_height = max(1, int(np.ceil((ymax - ymin) * pixels_per_mm)))
    translate = np.array(
        [
            [pixels_per_mm, 0.0, -xmin * pixels_per_mm],
            [0.0, pixels_per_mm, -ymin * pixels_per_mm],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    warped = cv2.warpPerspective(
        pixels_bgr, translate @ matrix, (dest_width, dest_height)
    )
    return warped, xmin, ymin, float(pixels_per_mm)


def canny_edge_points_mm(
    pixels_bgr: np.ndarray,
    calibration: CalibrationRecord,
    *,
    max_points: int = 8000,
) -> np.ndarray:
    """Return Canny edge pixels converted into millimetres, subsampled if needed."""
    from tooldrawer_studio.calibration.service import pixel_to_mm

    edges = canny_edges(pixels_bgr)
    ys, xs = np.nonzero(edges)
    if len(xs) == 0:
        return np.empty((0, 2), dtype=np.float64)
    if len(xs) > max_points:
        step = int(np.ceil(len(xs) / max_points))
        xs = xs[::step]
        ys = ys[::step]
    points = np.empty((len(xs), 2), dtype=np.float64)
    for index, (x_px, y_px) in enumerate(zip(xs, ys)):
        mapped = pixel_to_mm(calibration, PixelPoint(float(x_px), float(y_px)))
        points[index, 0] = mapped.x_mm
        points[index, 1] = mapped.y_mm
    return points


def snap_point_to_edges_mm(
    point: Point2D,
    edge_points_mm: np.ndarray,
    *,
    radius_mm: float = 1.5,
) -> Point2D:
    if edge_points_mm.size == 0:
        return point
    delta = edge_points_mm - np.array([point.x_mm, point.y_mm], dtype=np.float64)
    distances = np.hypot(delta[:, 0], delta[:, 1])
    nearest = int(np.argmin(distances))
    if float(distances[nearest]) > radius_mm:
        return point
    return Point2D(float(edge_points_mm[nearest, 0]), float(edge_points_mm[nearest, 1]))
