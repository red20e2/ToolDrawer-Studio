from __future__ import annotations

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
from tooldrawer_studio.export.service import ExportPaths, export_tool_package
from tooldrawer_studio.geometry.contour import replace_tool_contour, reset_tool_contour
from tooldrawer_studio.geometry.pocket import PocketSpec, build_pocket_insert
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
        if created:
            self._selected_tool_id = created[0].id
        return created

    def _tool_index(self, tool_id: str) -> int:
        for index, tool in enumerate(self.project.tools):
            if tool.id == tool_id:
                return index
        raise KeyError(f"Unknown tool id: {tool_id}")

    def replace_contour(self, tool_id: str, points: list[Point2D]) -> ToolObject:
        index = self._tool_index(tool_id)
        updated = replace_tool_contour(self.project.tools[index], points)
        self.project.tools[index] = updated
        return updated

    def reset_contour(self, tool_id: str) -> ToolObject:
        index = self._tool_index(tool_id)
        updated = reset_tool_contour(self.project.tools[index])
        self.project.tools[index] = updated
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
            tool.clearance_mm = float(clearance_mm)
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

    def measure_tool_thickness(self, tool_id: str) -> ThicknessMeasurementResult:
        tool, image, calibration = self._side_view_context(tool_id)
        result = self._measurement_service.measure(image.pixels_bgr, calibration)

        tool.automatic_thickness_mm = result.automatic_thickness_mm
        tool.automatic_thickness_confidence = result.confidence
        tool.automatic_thickness_endpoint_a_px = result.endpoint_a_px
        tool.automatic_thickness_endpoint_b_px = result.endpoint_b_px
        tool.corrected_thickness_endpoint_a_px = None
        tool.corrected_thickness_endpoint_b_px = None
        tool.side_view_silhouette_px = list(result.silhouette_px)

        if tool.thickness_measurement_mode == "manual" and tool.thickness_accepted:
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
        return result

    def _require_automatic_thickness(self, tool: ToolObject) -> float:
        if tool.automatic_thickness_mm is None:
            raise ValueError("No automatic thickness measurement is available")
        return _validate_positive(tool.automatic_thickness_mm, "Automatic thickness")

    def accept_automatic_thickness(self, tool_id: str) -> ToolObject:
        tool = self.project.tools[self._tool_index(tool_id)]
        tool.accepted_thickness_mm = self._require_automatic_thickness(tool)
        tool.thickness_measurement_mode = "automatic"
        tool.thickness_accepted = True
        tool.thickness_review_required = False
        self._pocket_spec = None
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
        return tool

    def suggested_pocket_depth(self, tool_id: str) -> float | None:
        tool = self.project.tools[self._tool_index(tool_id)]
        return suggested_pocket_depth_mm(self.project, tool)

    def resolved_pocket_depth(self, tool_id: str) -> float | None:
        tool = self.project.tools[self._tool_index(tool_id)]
        return final_pocket_depth_mm(self.project, tool)

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
