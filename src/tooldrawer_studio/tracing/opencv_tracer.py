from __future__ import annotations

from dataclasses import dataclass
from math import hypot

import cv2
import numpy as np
from shapely import make_valid
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from tooldrawer_studio.calibration.service import PixelPoint, pixel_to_mm
from tooldrawer_studio.capture.image_loader import LoadedImage
from tooldrawer_studio.domain.models import CalibrationRecord, Point2D
from tooldrawer_studio.geometry.contour import validate_contour
from tooldrawer_studio.tracing.models import TraceCandidate, TraceConfig


_MAX_FOCUS_ROI_PIXELS = 2_000_000
_LOW_CHROMA_SATURATION = 8.0
_MIN_LOW_CHROMA_VALUE_CONTRAST = 12.0
_MIN_LOW_CHROMA_COLOR_DISTANCE = 20.0
_FOCUS_AMBIGUITY_FRACTION = 0.01
_MIN_FOCUS_AMBIGUITY_PX = 2.0


@dataclass(frozen=True, slots=True)
class _MaskCoordinates:
    origin_x_px: float
    origin_y_px: float
    source_per_mask_x: float
    source_per_mask_y: float
    source_width_px: int
    source_height_px: int


@dataclass(frozen=True, slots=True)
class _FocusedMask:
    mask: np.ndarray
    coordinates: _MaskCoordinates


@dataclass(frozen=True, slots=True)
class _FocusComponentEvidence:
    ranking_key: tuple[float, float, float, float, int]
    axis_overlap: float
    cross_distance: float
    mean_saturation: float


def _focus_evidence_is_ambiguous(
    selected: _FocusComponentEvidence,
    challenger: _FocusComponentEvidence,
    line_length: float,
) -> bool:
    if selected.ranking_key == challenger.ranking_key:
        return True
    if (
        selected.mean_saturation > _LOW_CHROMA_SATURATION
        or challenger.mean_saturation > _LOW_CHROMA_SATURATION
    ):
        return False
    tolerance = max(
        _MIN_FOCUS_AMBIGUITY_PX,
        _FOCUS_AMBIGUITY_FRACTION * line_length,
    )
    return (
        abs(selected.axis_overlap - challenger.axis_overlap) <= tolerance
        and abs(selected.cross_distance - challenger.cross_distance) <= tolerance
    )


def _distance_to_segment(point: Point2D, start: Point2D, end: Point2D) -> float:
    dx = end.x_mm - start.x_mm
    dy = end.y_mm - start.y_mm
    if dx == 0.0 and dy == 0.0:
        return hypot(point.x_mm - start.x_mm, point.y_mm - start.y_mm)
    t = (
        (point.x_mm - start.x_mm) * dx + (point.y_mm - start.y_mm) * dy
    ) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nearest_x = start.x_mm + t * dx
    nearest_y = start.y_mm + t * dy
    return hypot(point.x_mm - nearest_x, point.y_mm - nearest_y)


def _rdp_open(points: list[Point2D], epsilon: float) -> list[Point2D]:
    if len(points) <= 2:
        return list(points)
    start, end = points[0], points[-1]
    max_distance = -1.0
    index = -1
    for i, point in enumerate(points[1:-1], start=1):
        distance = _distance_to_segment(point, start, end)
        if distance > max_distance:
            max_distance = distance
            index = i
    if max_distance > epsilon and index > 0:
        left = _rdp_open(points[: index + 1], epsilon)
        right = _rdp_open(points[index:], epsilon)
        return left[:-1] + right
    return [start, end]


def _simplify_closed(points: list[Point2D], epsilon: float) -> list[Point2D]:
    if len(points) <= 4 or epsilon <= 0:
        return list(points)
    anchor = points[0]
    split = max(
        range(1, len(points)),
        key=lambda i: hypot(
            points[i].x_mm - anchor.x_mm, points[i].y_mm - anchor.y_mm
        ),
    )
    first_arc = _rdp_open(points[: split + 1], epsilon)
    second_arc = _rdp_open(points[split:] + [points[0]], epsilon)
    combined = first_arc[:-1] + second_arc[:-1]
    deduped: list[Point2D] = []
    for point in combined:
        if not deduped or point != deduped[-1]:
            deduped.append(point)
    return deduped if len(deduped) >= 3 else list(points)


def _polygon_components(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        components: list[Polygon] = []
        for item in geometry.geoms:
            components.extend(_polygon_components(item))
        return components
    return []


def _valid_contour_components(points: list[Point2D]) -> list[tuple[list[Point2D], float]]:
    coordinates = [(float(point.x_mm), float(point.y_mm)) for point in points]
    if len(set(coordinates)) < 3:
        return []

    polygon = Polygon(coordinates)
    geometry: BaseGeometry = polygon if polygon.is_valid else make_valid(polygon)
    components = [
        component
        for component in _polygon_components(geometry)
        if not component.is_empty and component.area > 1e-6
    ]
    components.sort(
        key=lambda component: (
            component.area,
            component.bounds[0],
            component.bounds[1],
            component.bounds[2],
            component.bounds[3],
            component.wkb_hex,
        ),
        reverse=True,
    )

    repaired: list[tuple[list[Point2D], float]] = []
    for component in components:
        exterior = list(component.exterior.coords)
        contour = [
            Point2D(x_mm=float(x), y_mm=float(y))
            for x, y in exterior[:-1]
        ]
        try:
            validate_contour(contour)
        except ValueError:
            continue
        repaired.append((contour, float(component.area)))
    return repaired


def _border_foreground_count(mask: np.ndarray) -> int:
    border = np.concatenate((mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]))
    return int(np.count_nonzero(border))


def _select_foreground_mask(binary: np.ndarray, inverse: np.ndarray) -> np.ndarray:
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


def _global_foreground_mask(pixels_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(pixels_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    _, inverse = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    mask = _select_foreground_mask(binary, inverse)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return mask


def _known_distance_focus_line(
    image: LoadedImage,
    calibration: CalibrationRecord,
) -> tuple[PixelPoint, PixelPoint] | None:
    if calibration.method != "known_distance":
        return None

    matrix = np.asarray(calibration.matrix_3x3, dtype=np.float64)
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return None

    def map_mm(x_mm: float, y_mm: float) -> tuple[float, float] | None:
        mapped = inverse @ np.array([x_mm, y_mm, 1.0], dtype=np.float64)
        if abs(float(mapped[2])) < 1e-12:
            return None
        mapped /= mapped[2]
        x_px = float(mapped[0])
        y_px = float(mapped[1])
        if not np.isfinite(x_px) or not np.isfinite(y_px):
            return None
        return x_px, y_px

    origin = map_mm(0.0, 0.0)
    one_mm = map_mm(1.0, 0.0)
    if origin is None or one_mm is None:
        return None
    dx = one_mm[0] - origin[0]
    dy = one_mm[1] - origin[1]
    magnitude = hypot(dx, dy)
    if magnitude <= 1e-12:
        return None
    dx /= magnitude
    dy /= magnitude

    height, width = image.pixels_bgr.shape[:2]
    max_x = float(max(0, width - 1))
    max_y = float(max(0, height - 1))
    ox, oy = origin
    intersections: list[tuple[float, float]] = []

    if abs(dx) > 1e-12:
        for x in (0.0, max_x):
            t = (x - ox) / dx
            y = oy + t * dy
            if -1e-6 <= y <= max_y + 1e-6:
                intersections.append((x, min(max(y, 0.0), max_y)))
    if abs(dy) > 1e-12:
        for y in (0.0, max_y):
            t = (y - oy) / dy
            x = ox + t * dx
            if -1e-6 <= x <= max_x + 1e-6:
                intersections.append((min(max(x, 0.0), max_x), y))

    unique: list[tuple[float, float]] = []
    for point in intersections:
        if not any(hypot(point[0] - prior[0], point[1] - prior[1]) < 1e-6 for prior in unique):
            unique.append(point)
    if len(unique) < 2:
        return None

    first, second = max(
        (
            (a, b)
            for index, a in enumerate(unique)
            for b in unique[index + 1 :]
        ),
        key=lambda pair: hypot(pair[1][0] - pair[0][0], pair[1][1] - pair[0][1]),
    )
    if hypot(second[0] - first[0], second[1] - first[1]) < 12.0:
        return None
    return PixelPoint(*first), PixelPoint(*second)


def _bounded_focus_region(
    pixels_bgr: np.ndarray,
    focus_line_px: tuple[PixelPoint, PixelPoint],
) -> tuple[
    np.ndarray,
    tuple[PixelPoint, PixelPoint],
    int,
    _MaskCoordinates,
] | None:
    first, second = focus_line_px
    line_length = hypot(
        float(second.x_px - first.x_px),
        float(second.y_px - first.y_px),
    )
    height, width = pixels_bgr.shape[:2]
    if line_length < 12.0 or width <= 0 or height <= 0:
        return None

    search_half_width = int(
        round(
            max(
                12.0,
                min(
                    0.24 * line_length,
                    0.35 * min(width, height),
                ),
            )
        )
    )
    padding = search_half_width + 4
    left = max(0, int(np.floor(min(first.x_px, second.x_px) - padding)))
    top = max(0, int(np.floor(min(first.y_px, second.y_px) - padding)))
    right = min(
        width,
        int(np.ceil(max(first.x_px, second.x_px) + padding)) + 1,
    )
    bottom = min(
        height,
        int(np.ceil(max(first.y_px, second.y_px) + padding)) + 1,
    )
    if left >= right or top >= bottom:
        return None

    source_roi = pixels_bgr[top:bottom, left:right]
    source_height, source_width = source_roi.shape[:2]
    resize_factor = min(
        1.0,
        (_MAX_FOCUS_ROI_PIXELS / float(source_width * source_height)) ** 0.5,
    )
    target_width = max(1, int(np.floor(source_width * resize_factor)))
    target_height = max(1, int(np.floor(source_height * resize_factor)))
    while target_width * target_height > _MAX_FOCUS_ROI_PIXELS:
        if target_width >= target_height and target_width > 1:
            target_width -= 1
        elif target_height > 1:
            target_height -= 1
        else:
            break

    if target_width != source_width or target_height != source_height:
        focus_pixels = cv2.resize(
            source_roi,
            (target_width, target_height),
            interpolation=cv2.INTER_AREA,
        )
    else:
        focus_pixels = source_roi.copy()

    source_per_mask_x = (
        float(source_width - 1) / float(target_width - 1)
        if source_width > 1 and target_width > 1
        else 1.0
    )
    source_per_mask_y = (
        float(source_height - 1) / float(target_height - 1)
        if source_height > 1 and target_height > 1
        else 1.0
    )
    local_focus = (
        PixelPoint(
            (float(first.x_px) - float(left)) / source_per_mask_x,
            (float(first.y_px) - float(top)) / source_per_mask_y,
        ),
        PixelPoint(
            (float(second.x_px) - float(left)) / source_per_mask_x,
            (float(second.y_px) - float(top)) / source_per_mask_y,
        ),
    )
    local_half_width = max(
        1,
        int(
            round(
                float(search_half_width)
                / max(source_per_mask_x, source_per_mask_y)
            )
        ),
    )
    coordinates = _MaskCoordinates(
        origin_x_px=float(left),
        origin_y_px=float(top),
        source_per_mask_x=source_per_mask_x,
        source_per_mask_y=source_per_mask_y,
        source_width_px=width,
        source_height_px=height,
    )
    return focus_pixels, local_focus, local_half_width, coordinates


def _component_local_contrast(
    pixels_bgr: np.ndarray,
    hsv: np.ndarray,
    labels: np.ndarray,
    label: int,
    left: int,
    top: int,
    component_width: int,
    component_height: int,
) -> tuple[float, float]:
    margin = 3
    height, width = labels.shape[:2]
    expanded_left = max(0, left - margin)
    expanded_top = max(0, top - margin)
    expanded_right = min(width, left + component_width + margin)
    expanded_bottom = min(height, top + component_height + margin)
    expanded_bounds = np.s_[
        expanded_top:expanded_bottom,
        expanded_left:expanded_right,
    ]
    expanded_component = labels[expanded_bounds] == label
    ring = cv2.dilate(
        expanded_component.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        iterations=1,
    ).astype(bool)
    ring &= ~expanded_component
    if int(np.count_nonzero(ring)) < 8:
        return 0.0, 0.0

    expanded_value = hsv[expanded_bounds][:, :, 2]
    component_values = expanded_value[expanded_component]
    surrounding_values = expanded_value[ring]
    component_colors = pixels_bgr[expanded_bounds][expanded_component]
    surrounding_colors = pixels_bgr[expanded_bounds][ring]
    if component_values.size == 0 or surrounding_values.size == 0:
        return 0.0, 0.0

    value_contrast = abs(
        float(np.median(component_values))
        - float(np.median(surrounding_values))
    )
    component_color = np.median(component_colors, axis=0).astype(np.float64)
    surrounding_color = np.median(surrounding_colors, axis=0).astype(np.float64)
    color_distance = float(np.linalg.norm(component_color - surrounding_color))
    return value_contrast, color_distance


def _focus_color_mask(
    pixels_bgr: np.ndarray,
    focus_line_px: tuple[PixelPoint, PixelPoint],
    *,
    corridor_half_width: int | None = None,
) -> tuple[np.ndarray | None, bool]:
    first, second = focus_line_px
    line_length = hypot(
        float(second.x_px - first.x_px),
        float(second.y_px - first.y_px),
    )
    height, width = pixels_bgr.shape[:2]
    half_width = (
        int(corridor_half_width)
        if corridor_half_width is not None
        else int(
            round(max(12.0, min(0.24 * line_length, 0.35 * min(width, height))))
        )
    )
    corridor = np.zeros((height, width), dtype=np.uint8)
    first_xy = (int(round(first.x_px)), int(round(first.y_px)))
    second_xy = (int(round(second.x_px)), int(round(second.y_px)))
    cv2.line(
        corridor,
        first_xy,
        second_xy,
        255,
        thickness=max(3, half_width * 2),
        lineType=cv2.LINE_AA,
    )
    cv2.circle(corridor, first_xy, half_width, 255, -1)
    cv2.circle(corridor, second_xy, half_width, 255, -1)

    hsv = cv2.cvtColor(pixels_bgr, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    corridor_saturation = saturation[corridor != 0]
    if corridor_saturation.size == 0:
        return None, False
    otsu_threshold, _ = cv2.threshold(
        corridor_saturation.reshape(-1, 1),
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    axis_x = float(second.x_px - first.x_px) / line_length
    axis_y = float(second.y_px - first.y_px) / line_length
    hue = hsv[:, :, 0]
    otsu_value = int(round(float(otsu_threshold)))
    thresholds = [max(8, otsu_value)]
    low_chroma_threshold = max(1, otsu_value)
    if low_chroma_threshold < thresholds[0]:
        thresholds.append(low_chroma_threshold)
    selected_mean_saturation = 0.0
    selected_bounds: tuple[int, int, int, int] | None = None
    selected_component_mask: np.ndarray | None = None
    selected_key: tuple[float, float, float, float, int] | None = None
    selected_evidence_index: int | None = None
    component_evidence: list[_FocusComponentEvidence] = []
    color_attempted = False
    previous_color_seed: np.ndarray | None = None
    viable_component_seed = np.zeros((height, width), dtype=np.uint8)
    minimum_overlap = max(12.0, 0.15 * line_length)
    for saturation_threshold in thresholds:
        color_seed = np.where(
            (corridor != 0) & (saturation >= saturation_threshold),
            255,
            0,
        ).astype(np.uint8)
        color_seed = cv2.morphologyEx(color_seed, cv2.MORPH_OPEN, kernel)
        color_pixel_count = int(np.count_nonzero(color_seed))
        color_attempted = color_attempted or color_pixel_count > 0
        if previous_color_seed is not None and np.array_equal(
            color_seed, previous_color_seed
        ):
            continue
        previous_color_seed = color_seed
        if color_pixel_count < 20:
            continue

        component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            color_seed
        )
        for label in range(1, component_count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < 20:
                continue
            left = int(stats[label, cv2.CC_STAT_LEFT])
            top = int(stats[label, cv2.CC_STAT_TOP])
            component_width = int(stats[label, cv2.CC_STAT_WIDTH])
            component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
            component_bounds = np.s_[
                top : top + component_height,
                left : left + component_width,
            ]
            component_mask = labels[component_bounds] == label
            if np.any(
                viable_component_seed[component_bounds][component_mask] != 0
            ):
                continue
            local_ys, local_xs = np.nonzero(component_mask)
            ys = local_ys + top
            xs = local_xs + left
            relative_x = xs.astype(np.float64) - float(first.x_px)
            relative_y = ys.astype(np.float64) - float(first.y_px)
            axis_positions = relative_x * axis_x + relative_y * axis_y
            cross_positions = -relative_x * axis_y + relative_y * axis_x
            axis_min = float(axis_positions.min())
            axis_max = float(axis_positions.max())
            axis_span = axis_max - axis_min
            cross_span = float(cross_positions.max() - cross_positions.min())
            axis_overlap = max(
                0.0,
                min(axis_max, line_length) - max(axis_min, 0.0),
            )
            elongation = axis_span / max(cross_span, 1.0)
            if axis_overlap < minimum_overlap or elongation < 2.0:
                continue
            component_saturation = float(
                saturation[component_bounds][component_mask].mean()
            )
            if component_saturation <= _LOW_CHROMA_SATURATION:
                value_contrast, color_distance = _component_local_contrast(
                    pixels_bgr,
                    hsv,
                    labels,
                    label,
                    left,
                    top,
                    component_width,
                    component_height,
                )
                if (
                    value_contrast < _MIN_LOW_CHROMA_VALUE_CONTRAST
                    and color_distance < _MIN_LOW_CHROMA_COLOR_DISTANCE
                ):
                    continue
            else:
                hue_angles = (
                    hue[component_bounds][component_mask].astype(np.float64)
                    * (np.pi / 90.0)
                )
                hue_coherence = hypot(
                    float(np.cos(hue_angles).mean()),
                    float(np.sin(hue_angles).mean()),
                )
                if hue_coherence < 0.75:
                    continue
            viable_view = viable_component_seed[component_bounds]
            viable_view[component_mask] = 255
            cross_distance = abs(float(cross_positions.mean()))
            key = (axis_overlap, -cross_distance, axis_span, elongation, area)
            evidence = _FocusComponentEvidence(
                ranking_key=key,
                axis_overlap=axis_overlap,
                cross_distance=cross_distance,
                mean_saturation=component_saturation,
            )
            component_evidence.append(evidence)
            if selected_key is None or key > selected_key:
                selected_key = key
                selected_evidence_index = len(component_evidence) - 1
                selected_bounds = (
                    top,
                    left,
                    component_height,
                    component_width,
                )
                selected_component_mask = component_mask.copy()
                selected_mean_saturation = component_saturation
    selected_ambiguous = (
        selected_evidence_index is not None
        and any(
            index != selected_evidence_index
            and _focus_evidence_is_ambiguous(
                component_evidence[selected_evidence_index],
                evidence,
                line_length,
            )
            for index, evidence in enumerate(component_evidence)
        )
    )
    if (
        selected_ambiguous
        or selected_bounds is None
        or selected_component_mask is None
    ):
        return None, color_attempted

    top, left, component_height, component_width = selected_bounds
    color_seed = np.zeros((height, width), dtype=np.uint8)
    selected_view = color_seed[
        top : top + component_height,
        left : left + component_width,
    ]
    selected_view[selected_component_mask] = 255
    if selected_mean_saturation <= _LOW_CHROMA_SATURATION:
        return color_seed, True

    grabcut_mask = np.full((height, width), cv2.GC_BGD, dtype=np.uint8)
    grabcut_mask[corridor != 0] = cv2.GC_PR_BGD
    probable_foreground = cv2.dilate(
        color_seed,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        iterations=1,
    )
    grabcut_mask[probable_foreground != 0] = cv2.GC_PR_FGD
    grabcut_mask[color_seed != 0] = cv2.GC_FGD

    try:
        cv2.grabCut(
            pixels_bgr,
            grabcut_mask,
            None,
            np.zeros((1, 65), np.float64),
            np.zeros((1, 65), np.float64),
            5,
            cv2.GC_INIT_WITH_MASK,
        )
    except cv2.error:
        return None, True

    foreground = np.where(
        (grabcut_mask == cv2.GC_FGD) | (grabcut_mask == cv2.GC_PR_FGD),
        255,
        0,
    ).astype(np.uint8)
    if int(np.count_nonzero(foreground)) < 20:
        return None, True
    foreground = cv2.morphologyEx(
        foreground, cv2.MORPH_CLOSE, kernel, iterations=1
    )
    foreground = cv2.morphologyEx(
        foreground, cv2.MORPH_OPEN, kernel, iterations=1
    )
    return foreground, True


def _focus_line_mask(
    pixels_bgr: np.ndarray,
    focus_line_px: tuple[PixelPoint, PixelPoint],
) -> _FocusedMask | None:
    first, second = focus_line_px
    dx = float(second.x_px - first.x_px)
    dy = float(second.y_px - first.y_px)
    line_length = hypot(dx, dy)
    if line_length < 12.0:
        return None

    height, width = pixels_bgr.shape[:2]
    if width <= 0 or height <= 0:
        return None

    ax = int(round(first.x_px))
    ay = int(round(first.y_px))
    bx = int(round(second.x_px))
    by = int(round(second.y_px))
    if (
        max(ax, bx) < 0
        or max(ay, by) < 0
        or min(ax, bx) >= width
        or min(ay, by) >= height
    ):
        return None

    region = _bounded_focus_region(pixels_bgr, focus_line_px)
    if region is None:
        return None
    focus_pixels, local_focus, color_half_width, coordinates = region
    local_first, local_second = local_focus
    local_dx = float(local_second.x_px - local_first.x_px)
    local_dy = float(local_second.y_px - local_first.y_px)
    local_line_length = hypot(local_dx, local_dy)
    if local_line_length < 12.0:
        return None

    color_mask, color_attempted = _focus_color_mask(
        focus_pixels,
        local_focus,
        corridor_half_width=color_half_width,
    )
    if color_mask is not None:
        return _FocusedMask(color_mask, coordinates)
    if color_attempted:
        return None

    local_height, local_width = focus_pixels.shape[:2]
    local_ax = int(round(local_first.x_px))
    local_ay = int(round(local_first.y_px))
    local_bx = int(round(local_second.x_px))
    local_by = int(round(local_second.y_px))
    source_half_width = max(
        8.0,
        min(
            0.09 * line_length,
            0.22 * min(width, height),
        ),
    )
    half_width = int(
        round(
            source_half_width
            / max(
                coordinates.source_per_mask_x,
                coordinates.source_per_mask_y,
            )
        )
    )
    half_width = max(1, half_width)
    grabcut_mask = np.full(
        (local_height, local_width), cv2.GC_BGD, dtype=np.uint8
    )
    thickness = max(3, half_width * 2)
    cv2.line(
        grabcut_mask,
        (local_ax, local_ay),
        (local_bx, local_by),
        cv2.GC_PR_FGD,
        thickness=thickness,
        lineType=cv2.LINE_AA,
    )
    cv2.circle(
        grabcut_mask, (local_ax, local_ay), half_width, cv2.GC_PR_FGD, -1
    )
    cv2.circle(
        grabcut_mask, (local_bx, local_by), half_width, cv2.GC_PR_FGD, -1
    )

    midpoint = (
        int(round((local_ax + local_bx) / 2.0)),
        int(round((local_ay + local_by) / 2.0)),
    )
    seed_radius = max(3, min(half_width // 4, 12))
    cv2.circle(grabcut_mask, midpoint, seed_radius, cv2.GC_FGD, -1)

    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(
            focus_pixels,
            grabcut_mask,
            None,
            background_model,
            foreground_model,
            5,
            cv2.GC_INIT_WITH_MASK,
        )
    except cv2.error:
        return None

    foreground = np.where(
        (grabcut_mask == cv2.GC_FGD) | (grabcut_mask == cv2.GC_PR_FGD),
        255,
        0,
    ).astype(np.uint8)
    foreground_count = int(np.count_nonzero(foreground))
    if foreground_count < 20:
        return None

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    foreground = cv2.morphologyEx(
        foreground, cv2.MORPH_CLOSE, kernel, iterations=1
    )
    foreground = cv2.morphologyEx(
        foreground, cv2.MORPH_OPEN, kernel, iterations=1
    )
    return _FocusedMask(foreground, coordinates)


def _candidates_from_mask(
    mask: np.ndarray,
    calibration: CalibrationRecord,
    config: TraceConfig,
    *,
    coordinates: _MaskCoordinates | None = None,
) -> list[TraceCandidate]:
    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    height, width = mask.shape[:2]
    if coordinates is None:
        coordinates = _MaskCoordinates(
            origin_x_px=0.0,
            origin_y_px=0.0,
            source_per_mask_x=1.0,
            source_per_mask_y=1.0,
            source_width_px=width,
            source_height_px=height,
        )
    candidates: list[TraceCandidate] = []
    for contour in contours:
        pixel_vertices = contour.reshape(-1, 2)
        if len(pixel_vertices) < 3:
            continue
        source_vertices = np.empty(pixel_vertices.shape, dtype=np.float64)
        source_vertices[:, 0] = (
            coordinates.origin_x_px
            + pixel_vertices[:, 0].astype(np.float64)
            * coordinates.source_per_mask_x
        )
        source_vertices[:, 1] = (
            coordinates.origin_y_px
            + pixel_vertices[:, 1].astype(np.float64)
            * coordinates.source_per_mask_y
        )
        mm_points = [
            pixel_to_mm(
                calibration,
                PixelPoint(float(vertex[0]), float(vertex[1])),
            )
            for vertex in source_vertices
        ]
        simplified = _simplify_closed(mm_points, config.simplify_mm)
        components = _valid_contour_components(simplified)
        if not components:
            components = _valid_contour_components(mm_points)
        touches_border = any(
            float(vertex[0]) <= 0.0
            or float(vertex[1]) <= 0.0
            or float(vertex[0]) >= coordinates.source_width_px - 1
            or float(vertex[1]) >= coordinates.source_height_px - 1
            for vertex in source_vertices
        )
        for repaired_contour, area_mm2 in components:
            if area_mm2 < config.min_area_mm2:
                continue
            confidence = 1.0
            if touches_border:
                confidence -= 0.35
            if len(repaired_contour) < 4:
                confidence -= 0.15
            confidence = max(0.0, min(1.0, confidence))
            candidates.append(
                TraceCandidate(
                    base_contour_mm=repaired_contour,
                    confidence=confidence,
                    area_mm2=area_mm2,
                )
            )
    candidates.sort(key=lambda candidate: candidate.area_mm2, reverse=True)
    return candidates


def _candidate_polygon(candidate: TraceCandidate) -> Polygon | None:
    polygon = Polygon(
        [(point.x_mm, point.y_mm) for point in candidate.base_contour_mm]
    )
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 1e-9:
        return None
    return polygon


def _focus_sort_key(
    candidate: TraceCandidate,
    calibration: CalibrationRecord,
    focus_line_px: tuple[PixelPoint, PixelPoint],
) -> tuple[float, float, float, float]:
    first_mm = pixel_to_mm(calibration, focus_line_px[0])
    second_mm = pixel_to_mm(calibration, focus_line_px[1])
    midpoint = Point(
        (first_mm.x_mm + second_mm.x_mm) / 2.0,
        (first_mm.y_mm + second_mm.y_mm) / 2.0,
    )
    line = LineString(
        [
            (first_mm.x_mm, first_mm.y_mm),
            (second_mm.x_mm, second_mm.y_mm),
        ]
    )
    polygon = _candidate_polygon(candidate)
    if polygon is None:
        return (1.0, 0.0, float("inf"), candidate.area_mm2)
    midpoint_distance = float(polygon.distance(midpoint))
    overlap_length = float(polygon.intersection(line).length)
    contains_midpoint = 0.0 if polygon.buffer(1e-9).covers(midpoint) else 1.0
    return (
        contains_midpoint,
        -overlap_length,
        midpoint_distance,
        candidate.area_mm2,
    )


def _overlap_fraction(first: TraceCandidate, second: TraceCandidate) -> float:
    first_polygon = _candidate_polygon(first)
    second_polygon = _candidate_polygon(second)
    if first_polygon is None or second_polygon is None:
        return 0.0
    smaller = min(float(first_polygon.area), float(second_polygon.area))
    if smaller <= 1e-9:
        return 0.0
    return float(first_polygon.intersection(second_polygon).area) / smaller


class OpenCVTracer:
    def trace(
        self,
        image: LoadedImage,
        calibration: CalibrationRecord,
        config: TraceConfig = TraceConfig(),
        *,
        focus_line_px: tuple[PixelPoint, PixelPoint] | None = None,
    ) -> list[TraceCandidate]:
        if config.min_area_mm2 <= 0:
            raise ValueError("min_area_mm2 must be positive")
        if config.simplify_mm < 0:
            raise ValueError("simplify_mm must be non-negative")
        if calibration.capture_id != image.asset.id:
            raise ValueError("Calibration does not belong to this capture")

        global_mask = _global_foreground_mask(image.pixels_bgr)
        global_candidates = _candidates_from_mask(global_mask, calibration, config)
        del global_mask

        effective_focus = focus_line_px
        if effective_focus is None:
            effective_focus = _known_distance_focus_line(image, calibration)
        if effective_focus is None:
            return global_candidates

        focused_mask = _focus_line_mask(image.pixels_bgr, effective_focus)
        if focused_mask is None:
            global_candidates.sort(
                key=lambda candidate: _focus_sort_key(
                    candidate, calibration, effective_focus
                )
            )
            return global_candidates
        focused_candidates = _candidates_from_mask(
            focused_mask.mask,
            calibration,
            config,
            coordinates=focused_mask.coordinates,
        )
        if not focused_candidates:
            global_candidates.sort(
                key=lambda candidate: _focus_sort_key(
                    candidate, calibration, effective_focus
                )
            )
            return global_candidates

        focused_candidates.sort(
            key=lambda candidate: _focus_sort_key(
                candidate, calibration, effective_focus
            )
        )
        primary = focused_candidates[0]
        ordered: list[TraceCandidate] = [primary]

        for candidate in global_candidates:
            if _overlap_fraction(primary, candidate) >= 0.75:
                continue
            ordered.append(candidate)
        return ordered
