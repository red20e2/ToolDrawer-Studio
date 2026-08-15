from __future__ import annotations

from dataclasses import replace
from math import hypot, isfinite
from pathlib import Path
from uuid import uuid4

from tooldrawer_studio.calibration.presets import PaperPreset
from tooldrawer_studio.calibration.service import (
    PixelPoint,
    calibrate_known_distance as solve_known_distance,
    calibrate_known_object as solve_known_object,
    calibrate_paper as solve_paper,
    pixel_to_mm,
)
from tooldrawer_studio.calibration.target import (
    CalibrationTargetSpec,
    calibrate_target as solve_target,
)
from tooldrawer_studio.capture.image_loader import (
    LoadedImage,
    load_image,
    load_image_bytes,
    load_new_image_bytes,
    normalized_png_bytes,
)
from tooldrawer_studio.domain.models import CalibrationRecord, Point2D, Project, ToolObject
from tooldrawer_studio.export.service import (
    ExportPaths,
    OrganizerExportPaths,
    export_organizer_package,
    export_tool_package,
)
from tooldrawer_studio.generation.builder import (
    GenerationResult,
    generate_organizer as build_organizer,
)
from tooldrawer_studio.generation.fingerprint import generation_fingerprint
from tooldrawer_studio.generation.models import (
    GenerationSettings,
    GenerationValidationResult,
)
from tooldrawer_studio.generation.validation import (
    validate_generation as validate_generation_state,
)
from tooldrawer_studio.geometry.contour import replace_tool_contour, reset_tool_contour
from tooldrawer_studio.geometry.pocket import PocketSpec, build_pocket_insert
from tooldrawer_studio.layout.geometry import oriented_cavity_polygon
from tooldrawer_studio.layout.models import LayoutState, ToolPlacement
from tooldrawer_studio.layout.packer import PackingResult, pack_layout
from tooldrawer_studio.layout.validation import LayoutValidationResult, validate_layout
from tooldrawer_studio.measurement.depth import (
    final_pocket_depth_mm,
    suggested_pocket_depth_mm,
)
from tooldrawer_studio.measurement.models import (
    MIN_AUTOMATIC_THICKNESS_CONFIDENCE,
    ImagePoint,
    ThicknessMeasurementResult,
)
from tooldrawer_studio.measurement.service import ThicknessMeasurementService
from tooldrawer_studio.persistence.project_archive import ProjectBundle, load_project, save_project
from tooldrawer_studio.tracing.models import TraceConfig
from tooldrawer_studio.tracing.opencv_tracer import OpenCVTracer


MIN_AUTOMATIC_TRACE_CALIBRATION_CONFIDENCE = 0.75
_UNSET = object()


def _validate_nonnegative(value: float, label: str) -> float:
    converted = float(value)
    if not isfinite(converted) or converted < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return converted


def _validate_positive(value: float, label: str) -> float:
    converted = float(value)
    if not isfinite(converted) or converted <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return converted


def _validate_finite(value: float, label: str) -> float:
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


class WorkflowController:
    def __init__(
        self, measurement_service: ThicknessMeasurementService | None = None
    ) -> None:
        project = Project(id=str(uuid4()), name="Untitled Project")
        self.bundle = ProjectBundle(project=project, image_bytes={})
        self._loaded_images: dict[str, LoadedImage] = {}
        self._active_capture_id: str | None = None
        self._active_calibration: CalibrationRecord | None = None
        self._selected_tool_id: str | None = None
        self._pocket_spec: PocketSpec | None = None
        self._generation_result: GenerationResult | None = None
        self._measurement_service = measurement_service or ThicknessMeasurementService()

    @property
    def project(self) -> Project:
        return self.bundle.project

    @property
    def active_calibration(self) -> CalibrationRecord | None:
        return self._active_calibration

    @property
    def active_capture_id(self) -> str | None:
        return self._active_capture_id

    @property
    def generated_result(self) -> GenerationResult | None:
        return self._generation_result

    def _mark_generation_stale(self) -> None:
        self._generation_result = None
        self.project.generation_state.review_required = True

    def active_image_display_bytes(self) -> bytes:
        return normalized_png_bytes(self._require_active_image())

    def calibration_for_capture(self, capture_id: str) -> CalibrationRecord | None:
        records = [
            record
            for record in self.project.calibrations
            if record.capture_id == capture_id
        ]
        return records[-1] if records else None

    def activate_capture(self, capture_id: str) -> None:
        if capture_id not in self._loaded_images:
            raise KeyError(f"Unknown capture id: {capture_id}")
        self._active_capture_id = capture_id
        self._active_calibration = self.calibration_for_capture(capture_id)

    def capture_display_bytes(self, capture_id: str) -> bytes:
        image = self._loaded_images.get(capture_id)
        if image is None:
            raise KeyError(f"Unknown capture id: {capture_id}")
        return normalized_png_bytes(image)

    def loaded_image(self, capture_id: str) -> LoadedImage:
        image = self._loaded_images.get(capture_id)
        if image is None:
            raise KeyError(f"Unknown capture id: {capture_id}")
        return image

    def _store_loaded_image(self, loaded: LoadedImage) -> str:
        capture_id = loaded.asset.id
        self.project.captures.append(loaded.asset)
        self.bundle.image_bytes[capture_id] = loaded.original_bytes
        self._loaded_images[capture_id] = loaded
        self._active_capture_id = capture_id
        self._active_calibration = None
        return capture_id

    def import_image(self, path: Path) -> str:
        capture_id = str(uuid4())
        return self._store_loaded_image(load_image(path, capture_id))

    def import_image_bytes(self, raw: bytes, filename: str) -> str:
        capture_id = str(uuid4())
        return self._store_loaded_image(
            load_new_image_bytes(raw, filename, capture_id)
        )

    def _require_active_capture_id(self) -> str:
        if self._active_capture_id is None:
            raise ValueError("Import an image before calibrating")
        return self._active_capture_id

    def _require_active_image(self) -> LoadedImage:
        capture_id = self._require_active_capture_id()
        image = self._loaded_images.get(capture_id)
        if image is None:
            raise ValueError("The active source image is not decoded")
        return image

    def _invalidate_image_derived_thickness(self, tool: ToolObject) -> None:
        tool.automatic_thickness_mm = None
        tool.automatic_thickness_confidence = None
        tool.automatic_thickness_endpoint_a_px = None
        tool.automatic_thickness_endpoint_b_px = None
        tool.corrected_thickness_endpoint_a_px = None
        tool.corrected_thickness_endpoint_b_px = None
        tool.side_view_silhouette_px.clear()
        if tool.thickness_measurement_mode in {"automatic", "endpoints"}:
            tool.accepted_thickness_mm = None
            tool.thickness_measurement_mode = "none"
            tool.thickness_accepted = False
        if (
            tool.thickness_measurement_mode == "manual"
            or tool.pocket_depth_override_mm is not None
        ):
            tool.thickness_review_required = True
        self._pocket_spec = None
        self._mark_generation_stale()

    def _store_active_calibration(self, record: CalibrationRecord) -> CalibrationRecord:
        capture_id = self._require_active_capture_id()
        if capture_id != record.capture_id:
            raise ValueError("Calibration does not belong to the active capture")

        replacing_existing = self.calibration_for_capture(capture_id) is not None
        if replacing_existing:
            for tool in self.project.tools:
                if tool.side_view_capture_id == capture_id:
                    self._invalidate_image_derived_thickness(tool)

        self.project.calibrations = [
            existing
            for existing in self.project.calibrations
            if existing.capture_id != record.capture_id
        ]
        self.project.calibrations.append(record)
        self._active_calibration = record
        return record

    def calibrate_known_distance(
        self,
        pixel_a: PixelPoint,
        pixel_b: PixelPoint,
        known_distance_mm: float,
    ) -> CalibrationRecord:
        capture_id = self._require_active_capture_id()
        return self._store_active_calibration(
            solve_known_distance(capture_id, pixel_a, pixel_b, known_distance_mm)
        )

    def calibrate_paper(
        self,
        corners_px: tuple[PixelPoint, PixelPoint, PixelPoint, PixelPoint],
        preset: PaperPreset,
    ) -> CalibrationRecord:
        capture_id = self._require_active_capture_id()
        return self._store_active_calibration(
            solve_paper(capture_id, corners_px, preset)
        )

    def calibrate_known_object(
        self,
        corners_px: tuple[PixelPoint, PixelPoint, PixelPoint, PixelPoint],
        width_mm: float,
        height_mm: float,
    ) -> CalibrationRecord:
        capture_id = self._require_active_capture_id()
        return self._store_active_calibration(
            solve_known_object(capture_id, corners_px, width_mm, height_mm)
        )

    def calibrate_target(self, spec: CalibrationTargetSpec) -> CalibrationRecord:
        capture_id = self._require_active_capture_id()
        image = self._require_active_image()
        return self._store_active_calibration(solve_target(capture_id, image, spec))

    def trace_tools(
        self, *, allow_low_confidence: bool = False
    ) -> list[ToolObject]:
        if self._active_capture_id is None:
            raise ValueError("Import an image before tracing")
        if self._active_calibration is None:
            raise ValueError("Calibrate the active image before tracing")
        if (
            self._active_calibration.confidence
            < MIN_AUTOMATIC_TRACE_CALIBRATION_CONFIDENCE
            and not allow_low_confidence
        ):
            raise ValueError("Calibration confidence is too low for automatic tracing")
        image = self._loaded_images.get(self._active_capture_id)
        if image is None:
            raise ValueError("The active source image is not decoded")
        candidates = OpenCVTracer().trace(
            image, self._active_calibration, TraceConfig()
        )
        retained = [
            tool
            for tool in self.project.tools
            if tool.source_capture_id != self._active_capture_id
        ]
        created: list[ToolObject] = []
        for index, candidate in enumerate(candidates, start=1):
            raw = list(candidate.base_contour_mm)
            created.append(
                ToolObject(
                    id=str(uuid4()),
                    name=f"Tool {index}",
                    source_capture_id=self._active_capture_id,
                    base_contour_mm=list(raw),
                    contour_mm=list(raw),
                    clearance_mm=0.6,
                    trace_confidence=candidate.confidence,
                )
            )
        self.project.tools = retained + created
        self._reconcile_layout_tools()
        if created:
            self._selected_tool_id = created[0].id
        return created

    def _tool_index(self, tool_id: str) -> int:
        for index, tool in enumerate(self.project.tools):
            if tool.id == tool_id:
                return index
        raise KeyError(f"Unknown tool id: {tool_id}")

    def _mark_layout_review_required(self) -> None:
        if self.project.layout is not None:
            self.project.layout.review_required = True
        self._mark_generation_stale()

    def _reconcile_layout_tools(self) -> None:
        layout = self.project.layout
        if layout is None:
            return
        existing = {placement.tool_id: placement for placement in layout.placements}
        reconciled: list[ToolPlacement] = []
        for tool in self.project.tools:
            prior = existing.get(tool.id)
            reconciled.append(
                replace(prior) if prior is not None else ToolPlacement(tool_id=tool.id)
            )
        layout.placements = reconciled
        layout.unplaced_tool_ids = [
            placement.tool_id for placement in reconciled if not placement.is_placed
        ]
        layout.review_required = True
        self._mark_generation_stale()

    def _require_layout(self) -> LayoutState:
        if self.project.layout is None:
            raise ValueError("Configure an Arrange layout first")
        return self.project.layout

    def _placement_for(self, tool_id: str) -> ToolPlacement:
        self._tool_index(tool_id)
        layout = self._require_layout()
        placement = layout.placement_for(tool_id)
        if placement is None:
            placement = ToolPlacement(tool_id=tool_id)
            layout.placements.append(placement)
            layout.unplaced_tool_ids.append(tool_id)
        return placement

    def _preserved_layout_placements(self) -> list[ToolPlacement]:
        prior = self.project.layout
        by_id = (
            {placement.tool_id: placement for placement in prior.placements}
            if prior is not None
            else {}
        )
        return [
            replace(by_id[tool.id]) if tool.id in by_id else ToolPlacement(tool_id=tool.id)
            for tool in self.project.tools
        ]

    def configure_foam_layout(self, width_mm: float, height_mm: float) -> LayoutState:
        placements = self._preserved_layout_placements()
        prior_had_placed = any(placement.is_placed for placement in placements)
        self.project.layout = LayoutState(
            mode="foam",
            foam_width_mm=_validate_positive(width_mm, "Layout width"),
            foam_height_mm=_validate_positive(height_mm, "Layout height"),
            spacing_mm=self.project.default_layout_spacing_mm,
            border_mm=self.project.default_layout_border_mm,
            grab_clearance_mm=self.project.default_grab_clearance_mm,
            snap_enabled=(self.project.layout.snap_enabled if self.project.layout else False),
            snap_increment_mm=self.project.default_snap_increment_mm,
            placements=placements,
            unplaced_tool_ids=[
                placement.tool_id for placement in placements if not placement.is_placed
            ],
            review_required=prior_had_placed,
        )
        self._mark_generation_stale()
        return self.project.layout

    def configure_gridfinity_layout(
        self,
        columns: int,
        rows: int,
        pitch_mm: float | None = None,
    ) -> LayoutState:
        placements = self._preserved_layout_placements()
        prior_had_placed = any(placement.is_placed for placement in placements)
        pitch = (
            self.project.gridfinity_pitch_mm
            if pitch_mm is None
            else _validate_positive(pitch_mm, "Gridfinity pitch")
        )
        self.project.gridfinity_pitch_mm = pitch
        self.project.layout = LayoutState(
            mode="gridfinity",
            grid_columns=int(columns),
            grid_rows=int(rows),
            grid_pitch_mm=pitch,
            spacing_mm=self.project.default_layout_spacing_mm,
            border_mm=self.project.default_layout_border_mm,
            grab_clearance_mm=self.project.default_grab_clearance_mm,
            snap_enabled=(self.project.layout.snap_enabled if self.project.layout else False),
            snap_increment_mm=self.project.default_snap_increment_mm,
            placements=placements,
            unplaced_tool_ids=[
                placement.tool_id for placement in placements if not placement.is_placed
            ],
            review_required=prior_had_placed,
        )
        self._mark_generation_stale()
        return self.project.layout

    def set_layout_defaults(
        self,
        *,
        spacing_mm: float | None = None,
        border_mm: float | None = None,
        grab_clearance_mm: float | None = None,
        snap_increment_mm: float | None = None,
    ) -> LayoutState | None:
        layout = self.project.layout
        geometry_changed = False
        if spacing_mm is not None:
            value = _validate_nonnegative(spacing_mm, "Layout spacing")
            self.project.default_layout_spacing_mm = value
            if layout is not None and layout.spacing_mm != value:
                layout.spacing_mm = value
                geometry_changed = True
        if border_mm is not None:
            value = _validate_nonnegative(border_mm, "Layout border")
            self.project.default_layout_border_mm = value
            if layout is not None and layout.border_mm != value:
                layout.border_mm = value
                geometry_changed = True
        if grab_clearance_mm is not None:
            value = _validate_nonnegative(grab_clearance_mm, "Grab clearance")
            self.project.default_grab_clearance_mm = value
            if layout is not None and layout.grab_clearance_mm != value:
                layout.grab_clearance_mm = value
                geometry_changed = True
        if snap_increment_mm is not None:
            value = _validate_positive(snap_increment_mm, "Snap increment")
            self.project.default_snap_increment_mm = value
            if layout is not None:
                layout.snap_increment_mm = value
        if layout is not None and geometry_changed:
            self._mark_layout_review_required()
        return layout

    def set_layout_snap(self, enabled: bool) -> LayoutState:
        layout = self._require_layout()
        layout.snap_enabled = bool(enabled)
        return layout

    def set_tool_layout_options(
        self,
        tool_id: str,
        *,
        rotation_policy: str | None = None,
        grab_side: str | None = None,
        grab_clearance_override_mm: object = _UNSET,
    ) -> ToolPlacement:
        placement = self._placement_for(tool_id)
        changed_geometry = False
        if rotation_policy is not None and rotation_policy != placement.rotation_policy:
            probe = ToolPlacement(tool_id=tool_id, rotation_policy=rotation_policy)
            placement.rotation_policy = probe.rotation_policy
            if placement.rotation_policy == "orthogonal":
                normalized = placement.rotation_deg % 360.0
                placement.rotation_deg = float(int((normalized + 45.0) // 90.0) * 90 % 360)
            changed_geometry = placement.is_placed
        if grab_side is not None and grab_side != placement.grab_side:
            probe = ToolPlacement(tool_id=tool_id, grab_side=grab_side)
            placement.grab_side = probe.grab_side
            changed_geometry = changed_geometry or placement.is_placed
        if grab_clearance_override_mm is not _UNSET:
            value = (
                None
                if grab_clearance_override_mm is None
                else _validate_nonnegative(
                    float(grab_clearance_override_mm), "Grab clearance override"
                )
            )
            if value != placement.grab_clearance_override_mm:
                placement.grab_clearance_override_mm = value
                changed_geometry = changed_geometry or placement.is_placed
        if changed_geometry:
            self._mark_layout_review_required()
        return placement

    def move_tool(self, tool_id: str, x_mm: float, y_mm: float) -> ToolPlacement:
        placement = self._placement_for(tool_id)
        if placement.locked:
            raise ValueError("Unlock the tool before moving it")
        placement.x_mm = _validate_finite(x_mm, "Tool X")
        placement.y_mm = _validate_finite(y_mm, "Tool Y")
        placement.is_placed = True
        layout = self._require_layout()
        layout.unplaced_tool_ids = [
            value for value in layout.unplaced_tool_ids if value != tool_id
        ]
        layout.review_required = True
        self._mark_generation_stale()
        return placement

    def rotate_tool(self, tool_id: str, rotation_deg: float) -> ToolPlacement:
        placement = self._placement_for(tool_id)
        if placement.locked:
            raise ValueError("Unlock the tool before rotating it")
        if placement.rotation_policy == "fixed":
            raise ValueError("Tool rotation is fixed")
        requested = _validate_finite(rotation_deg, "Tool rotation") % 360.0
        if placement.rotation_policy == "orthogonal":
            requested = float(int((requested + 45.0) // 90.0) * 90 % 360)
        placement.rotation_deg = requested
        placement.is_placed = True
        layout = self._require_layout()
        layout.unplaced_tool_ids = [
            value for value in layout.unplaced_tool_ids if value != tool_id
        ]
        layout.review_required = True
        self._mark_generation_stale()
        return placement

    def set_tool_locked(self, tool_id: str, locked: bool) -> ToolPlacement:
        placement = self._placement_for(tool_id)
        placement.locked = bool(locked)
        return placement

    def validate_arrangement(self) -> LayoutValidationResult:
        layout = self._require_layout()
        return validate_layout(self.project, layout)

    def _apply_packing_result(self, result: PackingResult) -> PackingResult:
        layout = self._require_layout()
        layout.placements = [replace(placement) for placement in result.placements]
        layout.unplaced_tool_ids = list(result.unplaced_tool_ids)
        layout.review_required = not result.validation.valid
        self._mark_generation_stale()
        return result

    def auto_arrange(self) -> PackingResult:
        layout = self._require_layout()
        return self._apply_packing_result(pack_layout(self.project, layout))

    def repack_unlocked(self) -> PackingResult:
        layout = self._require_layout()
        return self._apply_packing_result(
            pack_layout(self.project, layout, repack_unlocked_only=True)
        )

    def _selected_placed_layout_items(
        self, tool_ids: list[str]
    ) -> list[tuple[ToolObject, ToolPlacement]]:
        if len(tool_ids) < 2:
            raise ValueError("Select at least two tools")
        items: list[tuple[ToolObject, ToolPlacement]] = []
        for tool_id in tool_ids:
            tool = self.project.tools[self._tool_index(tool_id)]
            placement = self._placement_for(tool_id)
            if not placement.is_placed:
                raise ValueError("All selected tools must be placed")
            if placement.locked:
                raise ValueError("Unlock selected tools before aligning or distributing")
            items.append((tool, placement))
        return items

    def align_tools(self, tool_ids: list[str], mode: str) -> None:
        items = self._selected_placed_layout_items(tool_ids)
        geometries = [oriented_cavity_polygon(tool, placement) for tool, placement in items]
        bounds = [geometry.bounds for geometry in geometries]
        centers = [geometry.centroid for geometry in geometries]
        if mode == "left":
            target = min(value[0] for value in bounds)
            deltas = [(target - value[0], 0.0) for value in bounds]
        elif mode == "right":
            target = max(value[2] for value in bounds)
            deltas = [(target - value[2], 0.0) for value in bounds]
        elif mode == "bottom":
            target = min(value[1] for value in bounds)
            deltas = [(0.0, target - value[1]) for value in bounds]
        elif mode == "top":
            target = max(value[3] for value in bounds)
            deltas = [(0.0, target - value[3]) for value in bounds]
        elif mode == "center_x":
            target = sum(center.x for center in centers) / len(centers)
            deltas = [(target - center.x, 0.0) for center in centers]
        elif mode == "center_y":
            target = sum(center.y for center in centers) / len(centers)
            deltas = [(0.0, target - center.y) for center in centers]
        else:
            raise ValueError(f"Unknown alignment mode: {mode}")
        for (_, placement), (dx, dy) in zip(items, deltas, strict=True):
            placement.x_mm += dx
            placement.y_mm += dy
        self._mark_layout_review_required()

    def distribute_tools(self, tool_ids: list[str], axis: str) -> None:
        items = self._selected_placed_layout_items(tool_ids)
        if axis == "horizontal":
            ordered = sorted(items, key=lambda item: item[1].x_mm)
            low = ordered[0][1].x_mm
            high = ordered[-1][1].x_mm
            step = (high - low) / (len(ordered) - 1)
            for index, (_, placement) in enumerate(ordered):
                placement.x_mm = low + step * index
        elif axis == "vertical":
            ordered = sorted(items, key=lambda item: item[1].y_mm)
            low = ordered[0][1].y_mm
            high = ordered[-1][1].y_mm
            step = (high - low) / (len(ordered) - 1)
            for index, (_, placement) in enumerate(ordered):
                placement.y_mm = low + step * index
        else:
            raise ValueError(f"Unknown distribution axis: {axis}")
        self._mark_layout_review_required()

    def replace_contour(self, tool_id: str, points: list[Point2D]) -> ToolObject:
        index = self._tool_index(tool_id)
        updated = replace_tool_contour(self.project.tools[index], points)
        self.project.tools[index] = updated
        self._mark_layout_review_required()
        return updated

    def reset_contour(self, tool_id: str) -> ToolObject:
        index = self._tool_index(tool_id)
        updated = reset_tool_contour(self.project.tools[index])
        self.project.tools[index] = updated
        self._mark_layout_review_required()
        return updated

    def rename_tool(self, tool_id: str, name: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Tool name cannot be blank")
        self.project.tools[self._tool_index(tool_id)].name = cleaned

    def update_tool_settings(
        self,
        tool_id: str,
        *,
        clearance_mm: float | None = None,
    ) -> ToolObject:
        tool = self.project.tools[self._tool_index(tool_id)]
        if clearance_mm is not None:
            if clearance_mm < 0:
                raise ValueError("Tool clearance must be non-negative")
            new_clearance = float(clearance_mm)
            if new_clearance != tool.clearance_mm:
                tool.clearance_mm = new_clearance
                self._mark_layout_review_required()
        return tool

    def attach_side_view(self, tool_id: str, capture_id: str) -> ToolObject:
        if capture_id not in self._loaded_images:
            raise KeyError(f"Unknown capture id: {capture_id}")
        tool = self.project.tools[self._tool_index(tool_id)]
        if tool.side_view_capture_id != capture_id:
            if tool.side_view_capture_id is not None:
                self._invalidate_image_derived_thickness(tool)
            tool.side_view_capture_id = capture_id
            self._pocket_spec = None
        self._mark_generation_stale()
        return tool

    def _side_view_context(
        self, tool_id: str
    ) -> tuple[ToolObject, LoadedImage, CalibrationRecord]:
        tool = self.project.tools[self._tool_index(tool_id)]
        capture_id = tool.side_view_capture_id
        if capture_id is None:
            raise ValueError("Attach a side-view capture before measuring thickness")
        image = self._loaded_images.get(capture_id)
        if image is None:
            raise ValueError("The side-view capture is not decoded")
        calibration = self.calibration_for_capture(capture_id)
        if calibration is None:
            raise ValueError("Calibrate the side-view capture before measuring thickness")
        return tool, image, calibration

    def measure_tool_thickness(
        self, tool_id: str, hint_px: ImagePoint | None = None
    ) -> ThicknessMeasurementResult:
        tool, image, calibration = self._side_view_context(tool_id)
        if hint_px is None:
            result = self._measurement_service.measure(image.pixels_bgr, calibration)
        else:
            result = self._measurement_service.measure(
                image.pixels_bgr, calibration, hint_px=hint_px
            )
        preserve_accepted = (
            tool.thickness_measurement_mode in {"manual", "endpoints"}
            and tool.thickness_accepted
            and tool.accepted_thickness_mm is not None
        )

        tool.automatic_thickness_mm = result.automatic_thickness_mm
        tool.automatic_thickness_confidence = result.confidence
        tool.automatic_thickness_endpoint_a_px = result.endpoint_a_px
        tool.automatic_thickness_endpoint_b_px = result.endpoint_b_px
        if not preserve_accepted:
            tool.corrected_thickness_endpoint_a_px = None
            tool.corrected_thickness_endpoint_b_px = None
        tool.side_view_silhouette_px = list(result.silhouette_px)

        if preserve_accepted:
            tool.thickness_review_required = True
        elif result.confidence >= MIN_AUTOMATIC_THICKNESS_CONFIDENCE:
            tool.accepted_thickness_mm = result.automatic_thickness_mm
            tool.thickness_measurement_mode = "automatic"
            tool.thickness_accepted = True
            tool.thickness_review_required = False
        else:
            tool.accepted_thickness_mm = None
            tool.thickness_measurement_mode = "none"
            tool.thickness_accepted = False

        self._pocket_spec = None
        self._mark_generation_stale()
        return result

    def _require_automatic_thickness(self, tool: ToolObject) -> float:
        if tool.automatic_thickness_mm is None:
            raise ValueError("No automatic thickness measurement is available")
        return _validate_positive(tool.automatic_thickness_mm, "Automatic thickness")

    def accept_automatic_thickness(self, tool_id: str) -> ToolObject:
        tool = self.project.tools[self._tool_index(tool_id)]
        tool.accepted_thickness_mm = self._require_automatic_thickness(tool)
        tool.corrected_thickness_endpoint_a_px = None
        tool.corrected_thickness_endpoint_b_px = None
        tool.thickness_measurement_mode = "automatic"
        tool.thickness_accepted = True
        tool.thickness_review_required = False
        self._pocket_spec = None
        self._mark_generation_stale()
        return tool

    def _validate_image_endpoint(self, image: LoadedImage, point: ImagePoint) -> None:
        x_px = float(point.x_px)
        y_px = float(point.y_px)
        if not isfinite(x_px) or not isfinite(y_px):
            raise ValueError("Thickness endpoints must be finite")
        height, width = image.pixels_bgr.shape[:2]
        if x_px < 0 or y_px < 0 or x_px >= width or y_px >= height:
            raise ValueError("Thickness endpoints must lie inside the side-view image")

    def set_thickness_endpoints(
        self, tool_id: str, endpoint_a: ImagePoint, endpoint_b: ImagePoint
    ) -> ToolObject:
        tool, image, calibration = self._side_view_context(tool_id)
        self._validate_image_endpoint(image, endpoint_a)
        self._validate_image_endpoint(image, endpoint_b)
        mm_a = pixel_to_mm(
            calibration, PixelPoint(float(endpoint_a.x_px), float(endpoint_a.y_px))
        )
        mm_b = pixel_to_mm(
            calibration, PixelPoint(float(endpoint_b.x_px), float(endpoint_b.y_px))
        )
        thickness = hypot(mm_b.x_mm - mm_a.x_mm, mm_b.y_mm - mm_a.y_mm)
        tool.accepted_thickness_mm = _validate_positive(thickness, "Endpoint thickness")
        tool.corrected_thickness_endpoint_a_px = endpoint_a
        tool.corrected_thickness_endpoint_b_px = endpoint_b
        tool.thickness_measurement_mode = "endpoints"
        tool.thickness_accepted = True
        tool.thickness_review_required = False
        self._pocket_spec = None
        self._mark_generation_stale()
        return tool

    def set_manual_thickness(self, tool_id: str, thickness_mm: float) -> ToolObject:
        tool = self.project.tools[self._tool_index(tool_id)]
        tool.accepted_thickness_mm = _validate_positive(
            thickness_mm, "Manual thickness"
        )
        tool.thickness_measurement_mode = "manual"
        tool.thickness_accepted = True
        tool.thickness_review_required = False
        self._pocket_spec = None
        self._mark_generation_stale()
        return tool

    def reset_to_automatic_thickness(self, tool_id: str) -> ToolObject:
        tool = self.project.tools[self._tool_index(tool_id)]
        tool.accepted_thickness_mm = self._require_automatic_thickness(tool)
        tool.corrected_thickness_endpoint_a_px = None
        tool.corrected_thickness_endpoint_b_px = None
        tool.thickness_measurement_mode = "automatic"
        tool.thickness_accepted = True
        tool.thickness_review_required = False
        self._pocket_spec = None
        self._mark_generation_stale()
        return tool

    def set_project_measure_defaults(
        self,
        *,
        exposed_height_mm: float | None = None,
        bottom_clearance_mm: float | None = None,
    ) -> Project:
        if exposed_height_mm is not None:
            self.project.default_exposed_height_mm = _validate_nonnegative(
                exposed_height_mm, "Exposed height"
            )
        if bottom_clearance_mm is not None:
            self.project.default_bottom_clearance_mm = _validate_nonnegative(
                bottom_clearance_mm, "Bottom clearance"
            )
        self._pocket_spec = None
        self._mark_generation_stale()
        return self.project

    def set_exposed_height_override(
        self, tool_id: str, value_mm: float | None
    ) -> ToolObject:
        tool = self.project.tools[self._tool_index(tool_id)]
        tool.exposed_height_override_mm = (
            None
            if value_mm is None
            else _validate_nonnegative(value_mm, "Exposed height override")
        )
        self._pocket_spec = None
        self._mark_generation_stale()
        return tool

    def set_bottom_clearance_override(
        self, tool_id: str, value_mm: float | None
    ) -> ToolObject:
        tool = self.project.tools[self._tool_index(tool_id)]
        tool.bottom_clearance_override_mm = (
            None
            if value_mm is None
            else _validate_nonnegative(value_mm, "Bottom clearance override")
        )
        self._pocket_spec = None
        self._mark_generation_stale()
        return tool

    def set_pocket_depth_override(
        self, tool_id: str, value_mm: float | None
    ) -> ToolObject:
        tool = self.project.tools[self._tool_index(tool_id)]
        tool.pocket_depth_override_mm = (
            None
            if value_mm is None
            else _validate_positive(value_mm, "Pocket depth override")
        )
        self._pocket_spec = None
        self._mark_generation_stale()
        return tool

    def suggested_pocket_depth(self, tool_id: str) -> float | None:
        tool = self.project.tools[self._tool_index(tool_id)]
        return suggested_pocket_depth_mm(self.project, tool)

    def resolved_pocket_depth(self, tool_id: str) -> float | None:
        tool = self.project.tools[self._tool_index(tool_id)]
        return final_pocket_depth_mm(self.project, tool)

    def set_generation_settings(self, **changes: object) -> GenerationSettings:
        allowed = set(GenerationSettings.__dataclass_fields__)
        unknown = set(changes).difference(allowed)
        if unknown:
            raise ValueError(
                f"Unknown generation setting(s): {', '.join(sorted(unknown))}"
            )
        updated = replace(self.project.generation_settings, **changes)
        if updated != self.project.generation_settings:
            self.project.generation_settings = updated
            self._mark_generation_stale()
        return self.project.generation_settings

    def set_tool_scoop_mode(self, tool_id: str, mode: str) -> GenerationSettings:
        self._tool_index(tool_id)
        if mode not in {"auto", "off"}:
            raise ValueError("Scoop mode must be 'auto' or 'off'")
        modes = dict(self.project.generation_settings.tool_scoop_modes)
        if mode == "auto":
            modes.pop(tool_id, None)
        else:
            modes[tool_id] = "off"
        return self.set_generation_settings(tool_scoop_modes=modes)

    def generation_validation(self) -> GenerationValidationResult:
        height = (
            None
            if self._generation_result is None
            else self._generation_result.body_height_mm
        )
        return validate_generation_state(self.project, height)

    def generate_organizer(self) -> GenerationResult:
        result = build_organizer(self.project)
        self._generation_result = result
        state = self.project.generation_state
        state.last_generated_fingerprint = result.fingerprint
        state.last_generated_height_mm = result.body_height_mm
        state.review_required = False
        return result

    def generation_is_current(self) -> bool:
        result = self._generation_result
        state = self.project.generation_state
        if result is None:
            return False
        try:
            current_fingerprint = generation_fingerprint(self.project)
        except (ValueError, TypeError):
            self._mark_generation_stale()
            return False
        current = (
            not state.review_required
            and result.fingerprint == current_fingerprint
            and state.last_generated_fingerprint == current_fingerprint
        )
        if not current:
            self._mark_generation_stale()
        return current

    def export_organizer(
        self,
        directory: Path,
        formats: set[str] | frozenset[str] | None = None,
    ) -> OrganizerExportPaths:
        if not self.generation_is_current() or self._generation_result is None:
            raise ValueError("Generate the current organizer before exporting")
        requested = (
            frozenset({"step", "stl", "dxf"})
            if formats is None
            else frozenset(formats)
        )
        return export_organizer_package(
            self._generation_result,
            self.project,
            directory,
            requested,
        )

    def save(self, path: Path) -> None:
        save_project(self.bundle, path)

    @classmethod
    def open(
        cls,
        path: Path,
        measurement_service: ThicknessMeasurementService | None = None,
    ) -> "WorkflowController":
        controller = cls(measurement_service=measurement_service)
        controller.bundle = load_project(path)
        controller._loaded_images = {
            capture.id: load_image_bytes(
                capture, controller.bundle.image_bytes[capture.id]
            )
            for capture in controller.project.captures
        }
        if controller.project.captures:
            controller._active_capture_id = controller.project.captures[-1].id
            controller._active_calibration = controller.calibration_for_capture(
                controller._active_capture_id
            )
        if controller.project.tools:
            controller._selected_tool_id = controller.project.tools[0].id
        controller._generation_result = None
        controller.project.generation_state.review_required = True
        return controller

    def select_tool(self, tool_id: str) -> None:
        self._tool_index(tool_id)
        self._selected_tool_id = tool_id

    def selected_tool(self) -> ToolObject:
        if self._selected_tool_id is None:
            raise ValueError("No tool is selected")
        return self.project.tools[self._tool_index(self._selected_tool_id)]

    def configure_pocket(
        self,
        base_width_mm: float,
        base_height_mm: float,
        base_thickness_mm: float,
        pocket_depth_mm: float | None = None,
    ) -> None:
        if pocket_depth_mm is None:
            tool = self.selected_tool()
            pocket_depth_mm = self.resolved_pocket_depth(tool.id)
            if pocket_depth_mm is None:
                raise ValueError("Selected tool has no resolved pocket depth")
        self._pocket_spec = PocketSpec(
            base_width_mm=base_width_mm,
            base_height_mm=base_height_mm,
            base_thickness_mm=base_thickness_mm,
            pocket_depth_mm=float(pocket_depth_mm),
        )

    def export_selected_tool(self, directory: Path) -> ExportPaths:
        if self._pocket_spec is None:
            raise ValueError("Configure pocket dimensions before exporting")
        tool = self.selected_tool()
        model = build_pocket_insert(tool, self._pocket_spec)
        return export_tool_package(model, tool, directory)
