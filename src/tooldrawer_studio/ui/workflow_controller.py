from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from tooldrawer_studio.calibration.presets import PaperPreset
from tooldrawer_studio.calibration.service import (
    PixelPoint,
    calibrate_known_distance as solve_known_distance,
    calibrate_known_object as solve_known_object,
    calibrate_paper as solve_paper,
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
from tooldrawer_studio.persistence.project_archive import ProjectBundle, load_project, save_project
from tooldrawer_studio.tracing.models import TraceConfig
from tooldrawer_studio.tracing.opencv_tracer import OpenCVTracer


MIN_AUTOMATIC_TRACE_CALIBRATION_CONFIDENCE = 0.75


class WorkflowController:
    def __init__(self) -> None:
        project = Project(id=str(uuid4()), name="Untitled Project")
        self.bundle = ProjectBundle(project=project, image_bytes={})
        self._loaded_images: dict[str, LoadedImage] = {}
        self._active_capture_id: str | None = None
        self._active_calibration: CalibrationRecord | None = None
        self._selected_tool_id: str | None = None
        self._pocket_spec: PocketSpec | None = None

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

    def _store_active_calibration(self, record: CalibrationRecord) -> CalibrationRecord:
        capture_id = self._require_active_capture_id()
        if capture_id != record.capture_id:
            raise ValueError("Calibration does not belong to the active capture")
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
                    depth_mm=5.0,
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
        depth_mm: float | None = None,
    ) -> ToolObject:
        tool = self.project.tools[self._tool_index(tool_id)]
        if clearance_mm is not None:
            if clearance_mm < 0:
                raise ValueError("Tool clearance must be non-negative")
            tool.clearance_mm = float(clearance_mm)
        if depth_mm is not None:
            if depth_mm <= 0:
                raise ValueError("Tool depth must be positive")
            tool.depth_mm = float(depth_mm)
        return tool

    def save(self, path: Path) -> None:
        save_project(self.bundle, path)

    @classmethod
    def open(cls, path: Path) -> "WorkflowController":
        controller = cls()
        controller.bundle = load_project(path)
        controller._loaded_images = {
            capture.id: load_image_bytes(
                capture, controller.bundle.image_bytes[capture.id]
            )
            for capture in controller.project.captures
        }
        if controller.project.captures:
            controller._active_capture_id = controller.project.captures[-1].id
            matching = [
                calibration
                for calibration in controller.project.calibrations
                if calibration.capture_id == controller._active_capture_id
            ]
            controller._active_calibration = matching[-1] if matching else None
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
        pocket_depth_mm: float,
    ) -> None:
        self._pocket_spec = PocketSpec(
            base_width_mm=base_width_mm,
            base_height_mm=base_height_mm,
            base_thickness_mm=base_thickness_mm,
            pocket_depth_mm=pocket_depth_mm,
        )

    def export_selected_tool(self, directory: Path) -> ExportPaths:
        if self._pocket_spec is None:
            raise ValueError("Configure pocket dimensions before exporting")
        tool = self.selected_tool()
        model = build_pocket_insert(tool, self._pocket_spec)
        return export_tool_package(model, tool, directory)
