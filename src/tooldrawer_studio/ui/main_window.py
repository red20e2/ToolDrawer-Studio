from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.calibration.presets import A4, LETTER
from tooldrawer_studio.calibration.target import CalibrationTargetSpec, write_target_svg
from tooldrawer_studio.capture.pending import CaptureSessionService
from tooldrawer_studio.capture.phone_server import PhoneUploadServer
from tooldrawer_studio.capture.phone_session import PhoneSession
from tooldrawer_studio.capture.webcam import WebcamCaptureService
from tooldrawer_studio.domain.models import CalibrationRecord, Point2D, ToolObject
from tooldrawer_studio.ui.arrange_panel import ArrangePanel
from tooldrawer_studio.ui.arrangement_view import ArrangementView
from tooldrawer_studio.ui.calibration_view import CalibrationImageView
from tooldrawer_studio.ui.capture_tray import CaptureTrayWidget, qr_image
from tooldrawer_studio.ui.contour_editor import ContourEditor
from tooldrawer_studio.ui.generate_panel import GeneratePanel
from tooldrawer_studio.ui.measure_panel import MeasurePanel
from tooldrawer_studio.ui.model_preview import ModelPreview
from tooldrawer_studio.ui.webcam_panel import WebcamPanel
from tooldrawer_studio.ui.workflow_controller import (
    MIN_AUTOMATIC_TRACE_CALIBRATION_CONFIDENCE,
    WorkflowController,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ToolDrawer Studio")
        self.resize(1100, 760)
        self.controller = WorkflowController()

        self.capture_session = CaptureSessionService()
        self.phone_session = PhoneSession(self.capture_session)
        self.phone_server = PhoneUploadServer(self.phone_session)
        self.webcam_service = WebcamCaptureService(self.capture_session)
        self.webcam_panel: WebcamPanel | None = None
        self._last_pending_count = 0
        self._phone_ui_active = False
        self._measure_calibration_tool_id: str | None = None
        self._measurement_warnings: dict[str, tuple[str, ...]] = {}

        self.tabs = QTabWidget(self)
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._capture_stage(), "1. Import & Calibrate")
        self.tabs.addTab(self._edit_stage(), "2. Detect & Edit")
        self.measure_panel = MeasurePanel()
        self._connect_measure_panel()
        self.tabs.addTab(self.measure_panel, "3. Measure")
        self.arrange_panel = ArrangePanel()
        self.arrangement_view = ArrangementView()
        self._connect_arrange()
        self.tabs.addTab(self._arrange_stage(), "4. Arrange")
        self.generate_panel = GeneratePanel()
        self.model_preview = ModelPreview()
        self._connect_generate()
        self.tabs.addTab(self._generate_stage(), "5. Generate")
        self.tabs.addTab(self._export_stage(), "6. Save & Export")
        for index in (1, 2, 3, 4, 5):
            self.tabs.setTabEnabled(index, False)

        self.capture_poll_timer = QTimer(self)
        self.capture_poll_timer.setInterval(250)
        self.capture_poll_timer.timeout.connect(self._poll_capture_state)
        self.capture_poll_timer.start()

    @staticmethod
    def _number(
        minimum: float,
        maximum: float,
        value: float,
        decimals: int = 3,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setValue(value)
        widget.setSuffix(" mm")
        return widget

    def _capture_stage(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.capture_layout = layout

        controls = QHBoxLayout()
        import_button = QPushButton("Import Photo")
        open_button = QPushButton("Open .tds Project")
        self.webcam_button = QPushButton("Webcam…")
        self.start_phone_button = QPushButton("Start Phone Session")
        self.stop_phone_button = QPushButton("Stop Phone Session")
        self.stop_phone_button.setEnabled(False)
        import_button.clicked.connect(self._import_photo)
        open_button.clicked.connect(self._open_project)
        self.webcam_button.clicked.connect(self._toggle_webcam_panel)
        self.start_phone_button.clicked.connect(self._start_phone_session)
        self.stop_phone_button.clicked.connect(self._stop_phone_session)
        controls.addWidget(import_button)
        controls.addWidget(open_button)
        controls.addWidget(self.webcam_button)
        controls.addWidget(self.start_phone_button)
        controls.addWidget(self.stop_phone_button)
        controls.addStretch()
        layout.addLayout(controls)

        phone_row = QHBoxLayout()
        self.phone_qr_label = QLabel()
        self.phone_qr_label.setMinimumSize(140, 140)
        self.phone_qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phone_qr_label.setVisible(False)
        phone_text = QVBoxLayout()
        self.phone_status = QLabel("Phone capture: stopped")
        self.phone_url_label = QLabel()
        self.phone_url_label.setWordWrap(True)
        self.phone_url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.phone_url_label.setVisible(False)
        phone_text.addWidget(self.phone_status)
        phone_text.addWidget(self.phone_url_label)
        phone_text.addStretch()
        phone_row.addWidget(self.phone_qr_label)
        phone_row.addLayout(phone_text, 1)
        layout.addLayout(phone_row)

        self.capture_tray = CaptureTrayWidget(self.capture_session)
        self.capture_tray.set_promote_callback(self._promote_pending_capture)
        layout.addWidget(self.capture_tray)

        self.calibration_view = CalibrationImageView()
        self.calibration_view.setMinimumHeight(300)
        layout.addWidget(self.calibration_view, 1)

        form = QFormLayout()
        self.calibration_mode = QComboBox()
        self.calibration_mode.addItem("Known distance", "known_distance")
        self.calibration_mode.addItem("A4 sheet", "paper_a4")
        self.calibration_mode.addItem("US Letter", "paper_letter")
        self.calibration_mode.addItem("Known-size object", "known_object")
        self.calibration_mode.addItem("Printable target", "target")
        form.addRow("Calibration method", self.calibration_mode)

        self.known_distance_label = QLabel("Known distance")
        self.known_distance = self._number(0.001, 100000, 100)
        form.addRow(self.known_distance_label, self.known_distance)

        self.object_width_label = QLabel("Object width")
        self.object_width = self._number(0.001, 100000, 100)
        self.object_height_label = QLabel("Object height")
        self.object_height = self._number(0.001, 100000, 50)
        form.addRow(self.object_width_label, self.object_width)
        form.addRow(self.object_height_label, self.object_height)

        self.target_paper_label = QLabel("Target paper")
        self.target_paper = QComboBox()
        self.target_paper.addItem("A4", "a4")
        self.target_paper.addItem("US Letter", "letter")
        form.addRow(self.target_paper_label, self.target_paper)
        layout.addLayout(form)

        self.calibration_instruction = QLabel()
        self.calibration_instruction.setWordWrap(True)
        layout.addWidget(self.calibration_instruction)

        calibration_actions = QHBoxLayout()
        clear_points_button = QPushButton("Clear Points")
        clear_points_button.clicked.connect(self.calibration_view.clear_points)
        self.calibrate_button = QPushButton("Calibrate")
        self.calibrate_button.clicked.connect(self._calibrate)
        self.save_target_button = QPushButton("Save Printable Target…")
        self.save_target_button.clicked.connect(self._save_target)
        self.detect_target_button = QPushButton("Detect Target")
        self.detect_target_button.clicked.connect(self._detect_target_calibration)
        calibration_actions.addWidget(clear_points_button)
        calibration_actions.addWidget(self.calibrate_button)
        calibration_actions.addWidget(self.save_target_button)
        calibration_actions.addWidget(self.detect_target_button)
        calibration_actions.addStretch()
        layout.addLayout(calibration_actions)

        self.calibration_status = QLabel("Calibration: not set")
        layout.addWidget(self.calibration_status)
        self.low_confidence_override = QCheckBox(
            "Allow low-confidence automatic tracing"
        )
        self.low_confidence_override.setVisible(False)
        layout.addWidget(self.low_confidence_override)

        disclaimer = QLabel(
            "Photo-derived dimensions are manufacturing aids, not metrology-grade measurements."
        )
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        self.calibration_mode.currentIndexChanged.connect(
            self._calibration_mode_changed
        )
        self._calibration_mode_changed()
        return page

    def _edit_stage(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        left = QVBoxLayout()
        detect_button = QPushButton("Detect Tools")
        detect_button.clicked.connect(self._detect_tools)
        left.addWidget(detect_button)
        self.tool_list = QListWidget()
        self.tool_list.currentItemChanged.connect(self._tool_selected)
        left.addWidget(self.tool_list)
        form = QFormLayout()
        self.tool_name = QLineEdit()
        self.tool_clearance = self._number(0.0, 25.0, 0.6)
        form.addRow("Tool name", self.tool_name)
        form.addRow("Clearance", self.tool_clearance)
        left.addLayout(form)
        apply_button = QPushButton("Apply Tool Settings")
        apply_button.clicked.connect(self._apply_tool_settings)
        left.addWidget(apply_button)
        self.segment_index = QSpinBox()
        self.vertex_index = QSpinBox()
        left.addWidget(QLabel("Segment index for midpoint insert"))
        left.addWidget(self.segment_index)
        insert_button = QPushButton("Insert Midpoint")
        insert_button.clicked.connect(self._insert_midpoint)
        left.addWidget(insert_button)
        left.addWidget(QLabel("Vertex index to delete"))
        left.addWidget(self.vertex_index)
        delete_button = QPushButton("Delete Vertex")
        delete_button.clicked.connect(self._delete_vertex)
        left.addWidget(delete_button)
        actions = QHBoxLayout()
        undo_button = QPushButton("Undo")
        redo_button = QPushButton("Redo")
        reset_button = QPushButton("Reset Trace")
        actions.addWidget(undo_button)
        actions.addWidget(redo_button)
        actions.addWidget(reset_button)
        left.addLayout(actions)
        layout.addLayout(left, 1)
        right = QVBoxLayout()
        self.contour_editor = ContourEditor()
        self.contour_editor.contourChanged.connect(self._contour_changed)
        undo_button.clicked.connect(self.contour_editor.undo_stack.undo)
        redo_button.clicked.connect(self.contour_editor.undo_stack.redo)
        reset_button.clicked.connect(self._reset_trace)
        right.addWidget(self.contour_editor)
        self.coordinate_label = QLabel("Vertex: --")
        self.contour_editor.coordinateChanged.connect(
            lambda x, y: self.coordinate_label.setText(
                f"Vertex: {x:.3f}, {y:.3f} mm"
            )
        )
        right.addWidget(self.coordinate_label)
        layout.addLayout(right, 3)
        return page

    def _arrange_stage(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.addWidget(self.arrange_panel, 1)
        right = QVBoxLayout()
        right.addWidget(self.arrangement_view, 1)
        actions = QHBoxLayout()
        undo_button = QPushButton("Undo Arrange")
        redo_button = QPushButton("Redo Arrange")
        undo_button.clicked.connect(self.arrangement_view.undo_stack.undo)
        redo_button.clicked.connect(self.arrangement_view.undo_stack.redo)
        actions.addWidget(undo_button)
        actions.addWidget(redo_button)
        actions.addStretch()
        right.addLayout(actions)
        layout.addLayout(right, 3)
        return page

    def _generate_stage(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.addWidget(self.generate_panel, 1)
        preview_column = QVBoxLayout()
        preview_title = QLabel("3D Manufacturing Preview")
        preview_column.addWidget(preview_title)
        preview_column.addWidget(self.model_preview, 1)
        reset_view = QPushButton("Reset 3D View")
        reset_view.clicked.connect(self.model_preview.reset_view)
        preview_column.addWidget(reset_view)
        layout.addLayout(preview_column, 3)
        return page

    def _export_stage(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        save_button = QPushButton("Save Editable .tds Project")
        save_button.clicked.connect(self._save_project)
        layout.addWidget(save_button)

        self.export_step_button = QPushButton("Export STEP")
        self.export_stl_button = QPushButton("Export STL")
        self.export_dxf_button = QPushButton("Export DXF")
        self.export_all_button = QPushButton("Export All")
        for button in (
            self.export_step_button,
            self.export_stl_button,
            self.export_dxf_button,
            self.export_all_button,
        ):
            button.setEnabled(False)
        self.export_step_button.clicked.connect(
            lambda: self._export_generated_files({"step"})
        )
        self.export_stl_button.clicked.connect(
            lambda: self._export_generated_files({"stl"})
        )
        self.export_dxf_button.clicked.connect(
            lambda: self._export_generated_files({"dxf"})
        )
        self.export_all_button.clicked.connect(
            lambda: self._export_generated_files({"step", "stl", "dxf"})
        )
        layout.addWidget(self.export_step_button)
        layout.addWidget(self.export_stl_button)
        layout.addWidget(self.export_dxf_button)
        layout.addWidget(self.export_all_button)
        self.export_status = QLabel("No manufacturing export yet")
        self.export_status.setWordWrap(True)
        layout.addWidget(self.export_status)
        layout.addStretch()
        return page

    def _connect_measure_panel(self) -> None:
        self.measure_panel.attachRequested.connect(self._measure_attach_side_view)
        self.measure_panel.calibrateRequested.connect(self._measure_calibrate_side_view)
        self.measure_panel.measureRequested.connect(self._measure_automatically)
        self.measure_panel.acceptRequested.connect(self._measure_accept_automatic)
        self.measure_panel.manualEndpointsRequested.connect(
            self._measure_enable_manual_points
        )
        self.measure_panel.resetAutomaticRequested.connect(
            self._measure_reset_automatic
        )
        self.measure_panel.manualThicknessRequested.connect(
            self._measure_set_manual_thickness
        )
        self.measure_panel.exposedHeightChanged.connect(
            self._measure_exposed_height_changed
        )
        self.measure_panel.bottomClearanceChanged.connect(
            self._measure_bottom_clearance_changed
        )
        self.measure_panel.pocketOverrideChanged.connect(
            self._measure_pocket_override_changed
        )
        self.measure_panel.endpointsChanged.connect(self._measure_endpoints_changed)

    def _connect_arrange(self) -> None:
        self.arrange_panel.layoutRequested.connect(self._arrange_layout_requested)
        self.arrange_panel.defaultsChanged.connect(self._arrange_defaults_changed)
        self.arrange_panel.snapChanged.connect(self._arrange_snap_changed)
        self.arrange_panel.autoArrangeRequested.connect(self._arrange_auto)
        self.arrange_panel.repackRequested.connect(self._arrange_repack)
        self.arrange_panel.rotationPolicyChanged.connect(self._arrange_rotation_policy)
        self.arrange_panel.grabSideChanged.connect(self._arrange_grab_side)
        self.arrange_panel.grabOverrideChanged.connect(self._arrange_grab_override)
        self.arrange_panel.lockChanged.connect(self._arrange_lock)
        self.arrange_panel.rotateRequested.connect(self._arrange_rotate)
        self.arrange_panel.alignRequested.connect(self._arrange_align)
        self.arrange_panel.distributeRequested.connect(self._arrange_distribute)
        self.arrangement_view.placementsCommitted.connect(
            self._arrange_placements_committed
        )
        self.arrangement_view.selectionChanged.connect(
            self._arrange_selection_changed
        )

    def _connect_generate(self) -> None:
        self.generate_panel.settingsChanged.connect(self._generate_settings_changed)
        self.generate_panel.toolScoopModeChanged.connect(self._generate_tool_scoop_mode)
        self.generate_panel.generateRequested.connect(self._generate_model)

    def _refresh_generate_state(self) -> None:
        project = self.controller.project
        self.generate_panel.set_project(project)
        layout = project.layout
        self.tabs.setTabEnabled(4, layout is not None and bool(project.tools))
        self.tabs.setTabEnabled(5, bool(project.tools))
        export_buttons = (
            self.export_step_button,
            self.export_stl_button,
            self.export_dxf_button,
            self.export_all_button,
        )
        if layout is None:
            self.model_preview.clear_model()
            self.generate_panel.set_currentness(False)
            for button in export_buttons:
                button.setEnabled(False)
            return
        try:
            validation = self.controller.generation_validation()
        except Exception as exc:
            self.generate_panel.validation_label.setText(f"Validation: {exc}")
        else:
            self.generate_panel.set_validation(validation)
        current = self.controller.generation_is_current()
        self.generate_panel.set_currentness(current)
        for button in export_buttons:
            button.setEnabled(current)
        result = self.controller.generated_result
        if current and result is not None:
            self.model_preview.set_model(result.model)
        else:
            self.model_preview.clear_model()

    def _generate_settings_changed(self, changes: object) -> None:
        try:
            if not isinstance(changes, dict):
                raise ValueError("Invalid Generate settings payload")
            self.controller.set_generation_settings(**changes)
            self._refresh_generate_state()
        except Exception as exc:
            self._show_error(exc)

    def _generate_tool_scoop_mode(self, tool_id: str, mode: str) -> None:
        try:
            self.controller.set_tool_scoop_mode(tool_id, mode)
            self._refresh_generate_state()
        except Exception as exc:
            self._show_error(exc)

    def _generate_model(self) -> None:
        try:
            result = self.controller.generate_organizer()
            self.model_preview.set_model(result.model)
            self._refresh_generate_state()
        except Exception as exc:
            self._refresh_generate_state()
            self._show_error(exc)

    def _show_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, "ToolDrawer Studio", str(exc))

    def _calibration_mode_changed(self, _index: int | None = None) -> None:
        mode = str(self.calibration_mode.currentData())
        required = {
            "known_distance": 2,
            "paper_a4": 4,
            "paper_letter": 4,
            "known_object": 4,
            "target": 0,
        }[mode]
        self.calibration_view.set_required_points(required)

        known_distance = mode == "known_distance"
        known_object = mode == "known_object"
        target = mode == "target"
        self.known_distance_label.setVisible(known_distance)
        self.known_distance.setVisible(known_distance)
        self.object_width_label.setVisible(known_object)
        self.object_width.setVisible(known_object)
        self.object_height_label.setVisible(known_object)
        self.object_height.setVisible(known_object)
        self.target_paper_label.setVisible(target)
        self.target_paper.setVisible(target)
        self.save_target_button.setVisible(target)
        self.detect_target_button.setVisible(target)
        self.calibrate_button.setVisible(not target)

        instructions = {
            "known_distance": "Click two points with a known real-world distance between them.",
            "paper_a4": "Click A4 corners in order: top-left, top-right, bottom-right, bottom-left.",
            "paper_letter": "Click Letter corners in order: top-left, top-right, bottom-right, bottom-left.",
            "known_object": "Click object corners in order: top-left, top-right, bottom-right, bottom-left, then enter its real dimensions.",
            "target": "Print the ToolDrawer target at 100% scale, photograph it with the tools, then use Detect Target.",
        }
        self.calibration_instruction.setText(instructions[mode])

    @staticmethod
    def _require_point_count(points: tuple, expected: int) -> None:
        if len(points) != expected:
            raise ValueError(f"Select exactly {expected} calibration points")

    def _target_spec(self) -> CalibrationTargetSpec:
        paper = A4 if self.target_paper.currentData() == "a4" else LETTER
        return CalibrationTargetSpec(paper)

    def _update_calibration_status(self, record: CalibrationRecord) -> None:
        if self._measure_calibration_tool_id is not None:
            self.calibration_status.setText(
                f"Side-view calibration: {record.method}, confidence {record.confidence:.0%}"
            )
            self.low_confidence_override.setChecked(False)
            self.low_confidence_override.setVisible(False)
            return
        self.calibration_status.setText(
            f"Calibration: {record.method}, confidence {record.confidence:.0%}"
        )
        low = record.confidence < MIN_AUTOMATIC_TRACE_CALIBRATION_CONFIDENCE
        self.low_confidence_override.setVisible(low)
        if not low:
            self.low_confidence_override.setChecked(False)
        self.tabs.setTabEnabled(1, True)

    def _advance_after_calibration(self, record: CalibrationRecord) -> None:
        if self._measure_calibration_tool_id is not None:
            tool_id = self._measure_calibration_tool_id
            self._measure_calibration_tool_id = None
            self.controller.select_tool(tool_id)
            self.controller.activate_capture(
                self.controller.selected_tool().source_capture_id
            )
            self._refresh_measure_state()
            self.tabs.setTabEnabled(2, True)
            self.tabs.setCurrentIndex(2)
            return
        if record.confidence >= MIN_AUTOMATIC_TRACE_CALIBRATION_CONFIDENCE:
            self.tabs.setCurrentIndex(1)
        else:
            self.tabs.setCurrentIndex(0)

    def _reset_for_uncalibrated_active_image(self) -> None:
        self._measure_calibration_tool_id = None
        self.calibration_view.set_image_bytes(
            self.controller.active_image_display_bytes()
        )
        self.calibration_view.clear_points()
        self.calibration_status.setText("Calibration: not set")
        self.low_confidence_override.setChecked(False)
        self.low_confidence_override.setVisible(False)
        self.tool_list.clear()
        for index in (1, 2, 3, 4, 5):
            self.tabs.setTabEnabled(index, False)
        self.arrangement_view.scene.clear()
        self.arrangement_view.undo_stack.clear()
        self.model_preview.clear_model()
        self.tabs.setCurrentIndex(0)

    def _import_photo(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import Tool Photo",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not filename:
            return
        try:
            path = Path(filename)
            self.controller = WorkflowController()
            self._measurement_warnings.clear()
            self.controller.import_image(path)
            self._reset_for_uncalibrated_active_image()
        except Exception as exc:
            self._show_error(exc)

    def _toggle_webcam_panel(self) -> None:
        try:
            if self.webcam_panel is None:
                self.webcam_panel = WebcamPanel(
                    self.webcam_service,
                    on_capture=self._capture_source_changed,
                    parent=self,
                )
                self.capture_layout.insertWidget(2, self.webcam_panel)
                self.webcam_panel.refresh_cameras()
                self.webcam_panel.show()
                return
            if self.webcam_panel.isHidden():
                self.webcam_panel.refresh_cameras()
                self.webcam_panel.show()
            else:
                self.webcam_panel.close_camera()
                self.webcam_panel.hide()
        except Exception as exc:
            self._show_error(exc)

    def _start_phone_session(self) -> None:
        try:
            endpoint = self.phone_server.start()
            pixmap = QPixmap.fromImage(qr_image(endpoint.upload_url))
            self.phone_qr_label.setPixmap(pixmap)
            self.phone_qr_label.setVisible(True)
            self.phone_url_label.setText(endpoint.upload_url)
            self.phone_url_label.setVisible(True)
            self.phone_status.setText("Phone capture: active")
            self.start_phone_button.setEnabled(False)
            self.stop_phone_button.setEnabled(True)
            self._phone_ui_active = True
        except Exception as exc:
            try:
                self.phone_server.stop()
            finally:
                self._set_phone_stopped("Phone capture: could not start")
            self._show_error(exc)

    def _set_phone_stopped(self, status: str) -> None:
        self._phone_ui_active = False
        self.phone_status.setText(status)
        self.phone_qr_label.clear()
        self.phone_qr_label.setVisible(False)
        self.phone_url_label.clear()
        self.phone_url_label.setVisible(False)
        self.start_phone_button.setEnabled(True)
        self.stop_phone_button.setEnabled(False)

    def _stop_phone_session(self) -> None:
        try:
            self.phone_server.stop()
        finally:
            self._set_phone_stopped("Phone capture: stopped")

    def _capture_source_changed(self) -> None:
        self.capture_tray.refresh()
        self._last_pending_count = len(self.capture_session.items())
        self._refresh_measure_sources_if_possible()

    def _poll_capture_state(self) -> None:
        count = len(self.capture_session.items())
        if count != self._last_pending_count:
            self.capture_tray.refresh()
            self._last_pending_count = count
            self._refresh_measure_sources_if_possible()
        if self._phone_ui_active and not self.phone_server.is_running:
            self._set_phone_stopped("Phone capture: stopped or expired")

    def _promote_pending_capture(self, pending_id: str) -> None:
        try:
            payload = self.capture_session.promotion_bytes(pending_id)
            self.controller.import_image_bytes(payload.raw, payload.filename)
            self._reset_for_uncalibrated_active_image()
            self.capture_tray.refresh()
            self._last_pending_count = len(self.capture_session.items())
        except Exception as exc:
            self._show_error(exc)

    def _calibrate(self) -> None:
        try:
            mode = str(self.calibration_mode.currentData())
            points = self.calibration_view.points_px()
            if mode == "known_distance":
                self._require_point_count(points, 2)
                record = self.controller.calibrate_known_distance(
                    points[0], points[1], self.known_distance.value()
                )
            elif mode == "paper_a4":
                self._require_point_count(points, 4)
                record = self.controller.calibrate_paper(points, A4)  # type: ignore[arg-type]
            elif mode == "paper_letter":
                self._require_point_count(points, 4)
                record = self.controller.calibrate_paper(points, LETTER)  # type: ignore[arg-type]
            elif mode == "known_object":
                self._require_point_count(points, 4)
                record = self.controller.calibrate_known_object(  # type: ignore[arg-type]
                    points, self.object_width.value(), self.object_height.value()
                )
            else:
                raise ValueError("Use Detect Target for printable-target calibration")
            self._update_calibration_status(record)
            self._advance_after_calibration(record)
        except Exception as exc:
            self._show_error(exc)

    def _save_target(self) -> None:
        try:
            spec = self._target_spec()
            default_name = f"ToolDrawer_Calibration_{spec.paper.label.replace(' ', '_')}.svg"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Save Printable Calibration Target",
                default_name,
                "SVG (*.svg)",
            )
            if not filename:
                return
            path = Path(filename)
            if path.suffix.lower() != ".svg":
                path = path.with_suffix(".svg")
            write_target_svg(path, spec)
        except Exception as exc:
            self._show_error(exc)

    def _detect_target_calibration(self) -> None:
        try:
            record = self.controller.calibrate_target(self._target_spec())
            self._update_calibration_status(record)
            self._advance_after_calibration(record)
        except Exception as exc:
            self._show_error(exc)

    def _detect_tools(self) -> None:
        try:
            tools = self.controller.trace_tools(
                allow_low_confidence=self.low_confidence_override.isChecked()
            )
            self._populate_tools(tools)
            if tools:
                self.tabs.setTabEnabled(2, True)
                self.tabs.setTabEnabled(3, True)
        except Exception as exc:
            self._show_error(exc)

    def _populate_tools(self, tools: list[ToolObject] | None = None) -> None:
        self.tool_list.clear()
        for tool in tools if tools is not None else self.controller.project.tools:
            item = QListWidgetItem(tool.name)
            item.setData(Qt.ItemDataRole.UserRole, tool.id)
            self.tool_list.addItem(item)
        if self.tool_list.count():
            self.tool_list.setCurrentRow(0)

    def _tool_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        try:
            self.controller.select_tool(str(current.data(Qt.ItemDataRole.UserRole)))
            tool = self.controller.selected_tool()
            self.tool_name.setText(tool.name)
            self.tool_clearance.setValue(tool.clearance_mm)
            self.segment_index.setMaximum(max(0, len(tool.contour_mm) - 1))
            self.vertex_index.setMaximum(max(0, len(tool.contour_mm) - 1))
            self.contour_editor.set_tool(tool)
            self.tabs.setTabEnabled(2, True)
            self.tabs.setTabEnabled(3, True)
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _contour_changed(self, points: list[Point2D]) -> None:
        try:
            self.controller.replace_contour(self.controller.selected_tool().id, points)
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _apply_tool_settings(self) -> None:
        try:
            tool = self.controller.selected_tool()
            self.controller.rename_tool(tool.id, self.tool_name.text())
            self.controller.update_tool_settings(
                tool.id,
                clearance_mm=self.tool_clearance.value(),
            )
            current = self.tool_list.currentItem()
            if current is not None:
                current.setText(self.controller.selected_tool().name)
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _insert_midpoint(self) -> None:
        try:
            points = self.contour_editor.contour()
            if not points:
                return
            index = self.segment_index.value()
            following = (index + 1) % len(points)
            midpoint = Point2D(
                (points[index].x_mm + points[following].x_mm) / 2.0,
                (points[index].y_mm + points[following].y_mm) / 2.0,
            )
            self.contour_editor.insert_vertex(index, midpoint)
        except Exception as exc:
            self._show_error(exc)

    def _delete_vertex(self) -> None:
        try:
            self.contour_editor.delete_vertex(self.vertex_index.value())
        except Exception as exc:
            self._show_error(exc)

    def _reset_trace(self) -> None:
        try:
            self.contour_editor.reset_to_base()
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _refresh_measure_sources_if_possible(self) -> None:
        if not self.controller.project.tools:
            return
        try:
            tool = self.controller.selected_tool()
        except ValueError:
            return
        self.measure_panel.set_sources(
            [
                (capture.id, capture.filename)
                for capture in self.controller.project.captures
                if capture.id != tool.source_capture_id
            ],
            [(item.id, item.filename) for item in self.capture_session.items()],
            selected_capture_id=tool.side_view_capture_id,
        )

    def _refresh_measure_state(self) -> None:
        tool = self.controller.selected_tool()
        self._refresh_measure_sources_if_possible()

        warnings = list(self._measurement_warnings.get(tool.id, ()))
        try:
            suggested = self.controller.suggested_pocket_depth(tool.id)
            final = self.controller.resolved_pocket_depth(tool.id)
        except ValueError as exc:
            suggested = None
            final = tool.pocket_depth_override_mm
            warnings.append(str(exc))

        calibration = (
            None
            if tool.side_view_capture_id is None
            else self.controller.calibration_for_capture(tool.side_view_capture_id)
        )
        calibration_text = (
            "Side-view calibration: not set"
            if calibration is None
            else f"Side-view calibration: {calibration.method}, confidence {calibration.confidence:.0%}"
        )
        self.measure_panel.set_tool_state(
            self.controller.project,
            tool,
            suggested_depth=suggested,
            final_depth=final,
            calibration_text=calibration_text,
            warnings=warnings,
        )

        if tool.side_view_capture_id is not None:
            self.measure_panel.measurement_view.set_image_bytes(
                self.controller.capture_display_bytes(tool.side_view_capture_id)
            )
            endpoint_a = (
                tool.corrected_thickness_endpoint_a_px
                or tool.automatic_thickness_endpoint_a_px
            )
            endpoint_b = (
                tool.corrected_thickness_endpoint_b_px
                or tool.automatic_thickness_endpoint_b_px
            )
            if endpoint_a is None or endpoint_b is None:
                endpoint_a = None
                endpoint_b = None
            self.measure_panel.measurement_view.set_overlay(
                tool.side_view_silhouette_px,
                endpoint_a,
                endpoint_b,
            )

        self.tabs.setTabEnabled(3, bool(self.controller.project.tools))
        self._refresh_arrange_state()

    def _refresh_arrange_state(self, *, sync_view: bool = True) -> None:
        project = self.controller.project
        layout = project.layout
        if layout is None:
            if sync_view:
                self.arrangement_view.scene.clear()
                self.arrangement_view.undo_stack.clear()
            self.arrange_panel.set_state(
                project,
                None,
                None,
                placed_count=0,
                total_count=len(project.tools),
                validation_messages=(),
            )
            self._refresh_generate_state()
            return

        validation = self.controller.validate_arrangement()
        if sync_view:
            self.arrangement_view.set_project_layout(project, layout, validation)
        try:
            selected_tool = self.controller.selected_tool()
            selected_placement = layout.placement_for(selected_tool.id)
        except ValueError:
            selected_placement = None
        placed_count = sum(1 for placement in layout.placements if placement.is_placed)
        self.arrange_panel.set_state(
            project,
            layout,
            selected_placement,
            placed_count=placed_count,
            total_count=len(project.tools),
            validation_messages=[issue.message for issue in validation.issues],
        )
        self._refresh_generate_state()

    def _arrange_selection_changed(self, selected: object) -> None:
        try:
            if not isinstance(selected, set) or len(selected) != 1:
                return
            tool_id = str(next(iter(selected)))
            self.controller.select_tool(tool_id)
            self._refresh_arrange_state(sync_view=False)
        except Exception as exc:
            self._show_error(exc)

    def _arrange_layout_requested(self, payload: object) -> None:
        try:
            if not isinstance(payload, tuple) or not payload:
                raise ValueError("Invalid layout request")
            mode = payload[0]
            if mode == "foam" and len(payload) == 3:
                self.controller.configure_foam_layout(payload[1], payload[2])
            elif mode == "gridfinity" and len(payload) == 4:
                self.controller.configure_gridfinity_layout(
                    int(payload[1]), int(payload[2]), float(payload[3])
                )
            else:
                raise ValueError("Invalid layout request")
            self.tabs.setTabEnabled(3, bool(self.controller.project.tools))
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_defaults_changed(self, change: object) -> None:
        try:
            name, value = change  # type: ignore[misc]
            allowed = {
                "spacing_mm",
                "border_mm",
                "grab_clearance_mm",
                "snap_increment_mm",
            }
            if name not in allowed:
                raise ValueError("Unknown Arrange default")
            self.controller.set_layout_defaults(**{str(name): float(value)})
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_snap_changed(self, enabled: bool) -> None:
        try:
            self.controller.set_layout_snap(enabled)
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_auto(self) -> None:
        try:
            self.controller.auto_arrange()
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_repack(self) -> None:
        try:
            self.controller.repack_unlocked()
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_rotation_policy(self, policy: str) -> None:
        try:
            tool = self.controller.selected_tool()
            self.controller.set_tool_layout_options(tool.id, rotation_policy=policy)
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_grab_side(self, grab_side: str) -> None:
        try:
            tool = self.controller.selected_tool()
            self.controller.set_tool_layout_options(tool.id, grab_side=grab_side)
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_grab_override(self, value: object) -> None:
        try:
            tool = self.controller.selected_tool()
            self.controller.set_tool_layout_options(
                tool.id,
                grab_clearance_override_mm=value,
            )
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_lock(self, locked: bool) -> None:
        try:
            tool = self.controller.selected_tool()
            self.controller.set_tool_locked(tool.id, locked)
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_rotate(self, rotation_deg: float) -> None:
        try:
            selected = sorted(self.arrangement_view.selected_tool_ids())
            if selected:
                self.arrangement_view.commit_rotation(selected, rotation_deg)
            else:
                tool = self.controller.selected_tool()
                self.controller.rotate_tool(tool.id, rotation_deg)
                self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_align(self, mode: str) -> None:
        try:
            selected = sorted(self.arrangement_view.selected_tool_ids())
            self.controller.align_tools(selected, mode)
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_distribute(self, axis: str) -> None:
        try:
            selected = sorted(self.arrangement_view.selected_tool_ids())
            self.controller.distribute_tools(selected, axis)
            self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _arrange_placements_committed(self, payload: object) -> None:
        try:
            if not isinstance(payload, list):
                raise ValueError("Invalid Arrange placement payload")
            layout = self.controller.project.layout
            if layout is None:
                raise ValueError("Configure an Arrange layout first")
            for record in payload:
                if not isinstance(record, tuple) or len(record) != 4:
                    raise ValueError("Invalid Arrange placement payload")
                tool_id, x_mm, y_mm, rotation_deg = record
                placement = layout.placement_for(str(tool_id))
                if placement is None:
                    raise KeyError(f"Unknown layout placement: {tool_id}")
                prior_rotation = placement.rotation_deg
                self.controller.move_tool(str(tool_id), float(x_mm), float(y_mm))
                if abs((float(rotation_deg) - prior_rotation) % 360.0) > 1e-9:
                    self.controller.rotate_tool(str(tool_id), float(rotation_deg))
            self._refresh_arrange_state(sync_view=False)
        except Exception as exc:
            self._show_error(exc)

    def _measure_attach_side_view(self) -> None:
        try:
            source = self.measure_panel.selected_source()
            if source is None:
                raise ValueError("Select a side-view source")
            source_kind, source_id = source
            if source_kind == "project":
                capture_id = source_id
            elif source_kind == "pending":
                payload = self.capture_session.promotion_bytes(source_id)
                capture_id = self.controller.import_image_bytes(
                    payload.raw, payload.filename
                )
                self.capture_tray.refresh()
                self._last_pending_count = len(self.capture_session.items())
            else:
                raise ValueError("Unknown side-view source")

            tool = self.controller.selected_tool()
            self.controller.attach_side_view(tool.id, capture_id)
            self.controller.activate_capture(tool.source_capture_id)
            self._measurement_warnings.pop(tool.id, None)
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _measure_calibrate_side_view(self) -> None:
        try:
            tool = self.controller.selected_tool()
            if tool.side_view_capture_id is None:
                raise ValueError("Attach a side-view capture before calibrating")
            self._measure_calibration_tool_id = tool.id
            self.controller.activate_capture(tool.side_view_capture_id)
            self.calibration_view.set_image_bytes(
                self.controller.active_image_display_bytes()
            )
            self.calibration_view.clear_points()
            record = self.controller.active_calibration
            if record is None:
                self.calibration_status.setText("Side-view calibration: not set")
            else:
                self._set_mode_from_calibration(record)
                self._update_calibration_status(record)
            self.low_confidence_override.setVisible(False)
            self.tabs.setCurrentIndex(0)
        except Exception as exc:
            self._measure_calibration_tool_id = None
            self._show_error(exc)

    def _measure_automatically(self) -> None:
        try:
            tool = self.controller.selected_tool()
            result = self.controller.measure_tool_thickness(tool.id)
            self._measurement_warnings[tool.id] = result.warnings
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _measure_accept_automatic(self) -> None:
        try:
            tool = self.controller.selected_tool()
            self.controller.accept_automatic_thickness(tool.id)
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _measure_enable_manual_points(self) -> None:
        try:
            tool = self.controller.selected_tool()
            if tool.side_view_capture_id is None:
                raise ValueError("Attach a side-view capture before measuring")
            if self.controller.calibration_for_capture(tool.side_view_capture_id) is None:
                raise ValueError("Calibrate the side-view capture before measuring")
            self.measure_panel.measurement_view.set_manual_point_mode(True)
        except Exception as exc:
            self._show_error(exc)

    def _measure_reset_automatic(self) -> None:
        try:
            tool = self.controller.selected_tool()
            self.controller.reset_to_automatic_thickness(tool.id)
            self.measure_panel.measurement_view.set_manual_point_mode(False)
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _measure_set_manual_thickness(self, thickness_mm: float) -> None:
        try:
            tool = self.controller.selected_tool()
            self.controller.set_manual_thickness(tool.id, thickness_mm)
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _measure_endpoints_changed(self, endpoints: object) -> None:
        try:
            if not isinstance(endpoints, tuple) or len(endpoints) != 2:
                return
            tool = self.controller.selected_tool()
            self.controller.set_thickness_endpoints(
                tool.id, endpoints[0], endpoints[1]
            )
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _measure_exposed_height_changed(self, change: object) -> None:
        try:
            scope, value = change  # type: ignore[misc]
            tool = self.controller.selected_tool()
            if scope == "project":
                self.controller.set_project_measure_defaults(exposed_height_mm=value)
            elif scope == "tool":
                self.controller.set_exposed_height_override(tool.id, value)
            else:
                raise ValueError("Unknown exposed-height setting scope")
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _measure_bottom_clearance_changed(self, change: object) -> None:
        try:
            scope, value = change  # type: ignore[misc]
            tool = self.controller.selected_tool()
            if scope == "project":
                self.controller.set_project_measure_defaults(bottom_clearance_mm=value)
            elif scope == "tool":
                self.controller.set_bottom_clearance_override(tool.id, value)
            else:
                raise ValueError("Unknown bottom-clearance setting scope")
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _measure_pocket_override_changed(self, value: object) -> None:
        try:
            tool = self.controller.selected_tool()
            self.controller.set_pocket_depth_override(tool.id, value)  # type: ignore[arg-type]
            self._refresh_measure_state()
        except Exception as exc:
            self._show_error(exc)

    def _save_project(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save ToolDrawer Project",
            "",
            "ToolDrawer Studio (*.tds)",
        )
        if not filename:
            return
        try:
            path = Path(filename)
            if path.suffix.lower() != ".tds":
                path = path.with_suffix(".tds")
            self.controller.save(path)
            self.export_status.setText(f"Saved {path}")
        except Exception as exc:
            self._show_error(exc)

    def _set_mode_from_calibration(self, record: CalibrationRecord) -> None:
        if record.method == "paper:a4":
            index = 1
        elif record.method == "paper:letter":
            index = 2
        elif record.method == "known_object":
            index = 3
        elif record.method.startswith("target:"):
            index = 4
            target_key = record.method.split(":", 1)[1]
            target_index = self.target_paper.findData(target_key)
            if target_index >= 0:
                self.target_paper.setCurrentIndex(target_index)
        else:
            index = 0
        self.calibration_mode.setCurrentIndex(index)

    def _open_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open ToolDrawer Project",
            "",
            "ToolDrawer Studio (*.tds)",
        )
        if not filename:
            return
        try:
            self.controller = WorkflowController.open(Path(filename))
            self._measurement_warnings.clear()
            if self.controller.project.tools:
                self.controller.activate_capture(
                    self.controller.project.tools[0].source_capture_id
                )
            if self.controller.project.captures:
                self.calibration_view.set_image_bytes(
                    self.controller.active_image_display_bytes()
                )
            calibration = self.controller.active_calibration
            if calibration is not None:
                self._set_mode_from_calibration(calibration)
                self._update_calibration_status(calibration)
            else:
                self.calibration_status.setText("Calibration: not set")
                self.low_confidence_override.setChecked(False)
                self.low_confidence_override.setVisible(False)
                self.tabs.setTabEnabled(1, bool(self.controller.project.tools))
            self._populate_tools()
            has_tools = bool(self.controller.project.tools)
            self.tabs.setTabEnabled(2, has_tools)
            self.tabs.setTabEnabled(3, has_tools)
            self.tabs.setTabEnabled(4, has_tools and self.controller.project.layout is not None)
            self.tabs.setTabEnabled(5, has_tools)
            if has_tools:
                self._refresh_measure_state()
            else:
                self._refresh_arrange_state()
        except Exception as exc:
            self._show_error(exc)

    def _export_generated_files(self, formats: set[str]) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Export Manufacturing Files"
        )
        if not directory:
            return
        try:
            paths = self.controller.export_organizer(Path(directory), formats)
            exported = [
                str(path)
                for path in (paths.step, paths.stl, paths.dxf)
                if path is not None
            ]
            self.export_status.setText("Exported:\n" + "\n".join(exported))
        except Exception as exc:
            self._show_error(exc)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if hasattr(self, "capture_poll_timer"):
            self.capture_poll_timer.stop()
        try:
            self.phone_server.stop()
        finally:
            if self.webcam_panel is not None:
                self.webcam_panel.close_camera()
            self.webcam_service.close()
        super().closeEvent(event)
