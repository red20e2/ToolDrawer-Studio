from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = ROOT / "src/tooldrawer_studio/ui/main_window.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_main_window() -> bool:
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    if 'self.tabs.addTab(self._generate_stage(), "5. Generate")' in text:
        return False

    text = replace_once(
        text,
        "from tooldrawer_studio.ui.contour_editor import ContourEditor\nfrom tooldrawer_studio.ui.measure_panel import MeasurePanel\n",
        "from tooldrawer_studio.ui.contour_editor import ContourEditor\n"
        "from tooldrawer_studio.ui.generate_panel import GeneratePanel\n"
        "from tooldrawer_studio.ui.measure_panel import MeasurePanel\n"
        "from tooldrawer_studio.ui.model_preview import ModelPreview\n",
        "generate ui imports",
    )

    text = replace_once(
        text,
        "        self.tabs.addTab(self._arrange_stage(), \"4. Arrange\")\n"
        "        self.tabs.addTab(self._pocket_stage(), \"5. Pocket Settings\")\n"
        "        self.tabs.addTab(self._export_stage(), \"6. Save & Export\")\n",
        "        self.tabs.addTab(self._arrange_stage(), \"4. Arrange\")\n"
        "        self.generate_panel = GeneratePanel()\n"
        "        self.model_preview = ModelPreview()\n"
        "        self._connect_generate()\n"
        "        self.tabs.addTab(self._generate_stage(), \"5. Generate\")\n"
        "        self.tabs.addTab(self._export_stage(), \"6. Save & Export\")\n",
        "Generate tab construction",
    )

    old_stage = '''    def _pocket_stage(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.base_width = self._number(1, 2000, 300)
        self.base_height = self._number(1, 2000, 200)
        self.base_thickness = self._number(0.1, 200, 10)
        self.pocket_depth_label = QLabel("No resolved pocket depth")
        form.addRow("Base width", self.base_width)
        form.addRow("Base height", self.base_height)
        form.addRow("Base thickness", self.base_thickness)
        form.addRow("Pocket depth", self.pocket_depth_label)
        layout.addLayout(form)
        button = QPushButton("Apply Pocket Settings")
        button.clicked.connect(self._configure_pocket)
        layout.addWidget(button)
        self.pocket_status = QLabel("Pocket settings not applied")
        layout.addWidget(self.pocket_status)
        layout.addStretch()
        return page

'''
    new_stage = '''    def _generate_stage(self) -> QWidget:
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

'''
    text = replace_once(text, old_stage, new_stage, "replace Pocket Settings stage")

    old_export = '''    def _export_stage(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        save_button = QPushButton("Save Editable .tds Project")
        export_button = QPushButton("Export STEP + STL + DXF")
        save_button.clicked.connect(self._save_project)
        export_button.clicked.connect(self._export_files)
        layout.addWidget(save_button)
        layout.addWidget(export_button)
        self.export_status = QLabel("No export yet")
        self.export_status.setWordWrap(True)
        layout.addWidget(self.export_status)
        layout.addStretch()
        return page

'''
    new_export = '''    def _export_stage(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        save_button = QPushButton("Save Editable .tds Project")
        save_button.clicked.connect(self._save_project)
        layout.addWidget(save_button)

        self.export_step_button = QPushButton("Export STEP")
        self.export_stl_button = QPushButton("Export STL")
        self.export_dxf_button = QPushButton("Export DXF")
        self.export_all_button = QPushButton("Export All")
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

'''
    text = replace_once(text, old_export, new_export, "replace manufacturing export stage")

    connect_marker = '''    def _show_error(self, exc: Exception) -> None:
'''
    generate_handlers = '''    def _connect_generate(self) -> None:
        self.generate_panel.settingsChanged.connect(self._generate_settings_changed)
        self.generate_panel.toolScoopModeChanged.connect(self._generate_tool_scoop_mode)
        self.generate_panel.generateRequested.connect(self._generate_model)

    def _refresh_generate_state(self) -> None:
        project = self.controller.project
        self.generate_panel.set_project(project)
        layout = project.layout
        self.tabs.setTabEnabled(4, layout is not None and bool(project.tools))
        self.tabs.setTabEnabled(5, bool(project.tools))
        if layout is None:
            self.model_preview.clear_model()
            self.generate_panel.set_currentness(False)
            return
        try:
            validation = self.controller.generation_validation()
        except Exception as exc:
            self.generate_panel.validation_label.setText(f"Validation: {exc}")
        else:
            self.generate_panel.set_validation(validation)
        current = self.controller.generation_is_current()
        self.generate_panel.set_currentness(current)
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

'''
    text = replace_once(
        text,
        connect_marker,
        generate_handlers + connect_marker,
        "Generate signal/controller handlers",
    )

    text = replace_once(
        text,
        "        self.arrangement_view.scene.clear()\n"
        "        self.arrangement_view.undo_stack.clear()\n"
        "        self.tabs.setCurrentIndex(0)\n",
        "        self.arrangement_view.scene.clear()\n"
        "        self.arrangement_view.undo_stack.clear()\n"
        "        self.model_preview.clear_model()\n"
        "        self.tabs.setCurrentIndex(0)\n",
        "reset generated preview",
    )

    old_measure_gate = '''        if final is None:
            self.pocket_depth_label.setText("No resolved pocket depth")
        else:
            self.pocket_depth_label.setText(f"{final:.3f} mm (from Measure)")

'''
    text = replace_once(text, old_measure_gate, "", "remove Pocket Settings depth label")

    text = replace_once(
        text,
        "        self.tabs.setTabEnabled(3, bool(self.controller.project.tools))\n"
        "        self.tabs.setTabEnabled(4, final is not None)\n"
        "        if final is None:\n"
        "            self.tabs.setTabEnabled(5, False)\n"
        "        self._refresh_arrange_state()\n",
        "        self.tabs.setTabEnabled(3, bool(self.controller.project.tools))\n"
        "        self._refresh_arrange_state()\n",
        "Measure to Arrange/Generate navigation",
    )

    text = replace_once(
        text,
        "            self.arrange_panel.set_state(\n"
        "                project,\n"
        "                None,\n"
        "                None,\n"
        "                placed_count=0,\n"
        "                total_count=len(project.tools),\n"
        "                validation_messages=(),\n"
        "            )\n"
        "            return\n",
        "            self.arrange_panel.set_state(\n"
        "                project,\n"
        "                None,\n"
        "                None,\n"
        "                placed_count=0,\n"
        "                total_count=len(project.tools),\n"
        "                validation_messages=(),\n"
        "            )\n"
        "            self._refresh_generate_state()\n"
        "            return\n",
        "no-layout Generate refresh",
    )

    text = replace_once(
        text,
        "        self.arrange_panel.set_state(\n"
        "            project,\n"
        "            layout,\n"
        "            selected_placement,\n"
        "            placed_count=placed_count,\n"
        "            total_count=len(project.tools),\n"
        "            validation_messages=[issue.message for issue in validation.issues],\n"
        "        )\n",
        "        self.arrange_panel.set_state(\n"
        "            project,\n"
        "            layout,\n"
        "            selected_placement,\n"
        "            placed_count=placed_count,\n"
        "            total_count=len(project.tools),\n"
        "            validation_messages=[issue.message for issue in validation.issues],\n"
        "        )\n"
        "        self._refresh_generate_state()\n",
        "configured-layout Generate refresh",
    )

    text = replace_once(
        text,
        "            self.tabs.setTabEnabled(4, False)\n"
        "            self.tabs.setTabEnabled(5, False)\n",
        "            self.tabs.setTabEnabled(4, has_tools and self.controller.project.layout is not None)\n"
        "            self.tabs.setTabEnabled(5, has_tools)\n",
        "open project Generate navigation",
    )

    old_export_method = '''    def _export_files(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Export Manufacturing Files"
        )
        if not directory:
            return
        try:
            self.controller.configure_pocket(
                self.base_width.value(),
                self.base_height.value(),
                self.base_thickness.value(),
                pocket_depth_mm=None,
            )
            paths = self.controller.export_selected_tool(Path(directory))
            self.export_status.setText(
                f"Exported:\n{paths.step}\n{paths.stl}\n{paths.dxf}"
            )
        except Exception as exc:
            self._show_error(exc)

'''
    new_export_method = '''    def _export_generated_files(self, formats: set[str]) -> None:
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

'''
    text = replace_once(
        text,
        old_export_method,
        new_export_method,
        "organizer export handler",
    )

    MAIN_WINDOW.write_text(text, encoding="utf-8")
    return True


if __name__ == "__main__":
    changed = patch_main_window()
    print("main-window-patched" if changed else "main-window-already-patched")
