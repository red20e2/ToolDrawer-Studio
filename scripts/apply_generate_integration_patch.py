from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "src/tooldrawer_studio/ui/workflow_controller.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_controller() -> bool:
    text = CONTROLLER.read_text(encoding="utf-8")
    if "def generation_is_current(self) -> bool:" in text:
        return False

    text = replace_once(
        text,
        "from tooldrawer_studio.export.service import ExportPaths, export_tool_package\n",
        "from tooldrawer_studio.export.service import (\n"
        "    ExportPaths,\n"
        "    OrganizerExportPaths,\n"
        "    export_organizer_package,\n"
        "    export_tool_package,\n"
        ")\n"
        "from tooldrawer_studio.generation.builder import (\n"
        "    GenerationResult,\n"
        "    generate_organizer as build_organizer,\n"
        ")\n"
        "from tooldrawer_studio.generation.fingerprint import generation_fingerprint\n"
        "from tooldrawer_studio.generation.models import (\n"
        "    GenerationSettings,\n"
        "    GenerationValidationResult,\n"
        ")\n"
        "from tooldrawer_studio.generation.validation import (\n"
        "    validate_generation as validate_generation_state,\n"
        ")\n",
        "generation imports",
    )

    text = replace_once(
        text,
        "        self._pocket_spec: PocketSpec | None = None\n        self._measurement_service = measurement_service or ThicknessMeasurementService()\n",
        "        self._pocket_spec: PocketSpec | None = None\n"
        "        self._generation_result: GenerationResult | None = None\n"
        "        self._measurement_service = measurement_service or ThicknessMeasurementService()\n",
        "generation runtime state",
    )

    text = replace_once(
        text,
        "    @property\n    def active_capture_id(self) -> str | None:\n        return self._active_capture_id\n\n",
        "    @property\n    def active_capture_id(self) -> str | None:\n        return self._active_capture_id\n\n"
        "    @property\n    def generated_result(self) -> GenerationResult | None:\n"
        "        return self._generation_result\n\n"
        "    def _mark_generation_stale(self) -> None:\n"
        "        self._generation_result = None\n"
        "        self.project.generation_state.review_required = True\n\n",
        "generation stale helper",
    )

    text = replace_once(
        text,
        "    def _mark_layout_review_required(self) -> None:\n        if self.project.layout is not None:\n            self.project.layout.review_required = True\n",
        "    def _mark_layout_review_required(self) -> None:\n"
        "        if self.project.layout is not None:\n"
        "            self.project.layout.review_required = True\n"
        "        self._mark_generation_stale()\n",
        "layout invalidation",
    )

    marker = "    def _invalidate_image_derived_thickness(self, tool: ToolObject) -> None:\n"
    before, tail = text.split(marker, 1)
    tail = marker + tail
    tail = tail.replace(
        "        self._pocket_spec = None\n",
        "        self._pocket_spec = None\n        self._mark_generation_stale()\n",
    )
    text = before + tail

    text = replace_once(
        text,
        "        layout.review_required = True\n\n    def _require_layout",
        "        layout.review_required = True\n"
        "        self._mark_generation_stale()\n\n"
        "    def _require_layout",
        "layout tool reconciliation",
    )

    layout_return = (
        "            review_required=prior_had_placed,\n"
        "        )\n"
        "        return self.project.layout\n"
    )
    if text.count(layout_return) != 2:
        raise RuntimeError(
            f"layout configuration: expected two matches, found {text.count(layout_return)}"
        )
    text = text.replace(
        layout_return,
        "            review_required=prior_had_placed,\n"
        "        )\n"
        "        self._mark_generation_stale()\n"
        "        return self.project.layout\n",
    )

    text = replace_once(
        text,
        "        if layout is not None and geometry_changed:\n            layout.review_required = True\n",
        "        if layout is not None and geometry_changed:\n"
        "            self._mark_layout_review_required()\n",
        "layout defaults invalidation",
    )

    move_return = "        layout.review_required = True\n        return placement\n"
    if text.count(move_return) != 2:
        raise RuntimeError(
            f"move/rotate invalidation: expected two matches, found {text.count(move_return)}"
        )
    text = text.replace(
        move_return,
        "        layout.review_required = True\n"
        "        self._mark_generation_stale()\n"
        "        return placement\n",
    )

    text = replace_once(
        text,
        "        layout.review_required = not result.validation.valid\n        return result\n",
        "        layout.review_required = not result.validation.valid\n"
        "        self._mark_generation_stale()\n"
        "        return result\n",
        "packing invalidation",
    )

    methods = '''    def set_generation_settings(self, **changes: object) -> GenerationSettings:
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

'''
    text = replace_once(
        text,
        "    def save(self, path: Path) -> None:\n",
        methods + "    def save(self, path: Path) -> None:\n",
        "generation controller methods",
    )

    text = replace_once(
        text,
        "        if controller.project.tools:\n            controller._selected_tool_id = controller.project.tools[0].id\n        return controller\n",
        "        if controller.project.tools:\n"
        "            controller._selected_tool_id = controller.project.tools[0].id\n"
        "        controller._generation_result = None\n"
        "        controller.project.generation_state.review_required = True\n"
        "        return controller\n",
        "reopen generation invalidation",
    )

    CONTROLLER.write_text(text, encoding="utf-8")
    return True


if __name__ == "__main__":
    changed = patch_controller()
    print("controller-patched" if changed else "controller-already-patched")
