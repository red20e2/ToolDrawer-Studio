from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from PySide6.QtWidgets import QApplication, QWidget


@contextmanager
def busy_ui(window, message: str) -> Iterator[None]:
    controls: tuple[QWidget, ...] = (
        window.generate_panel.generate_button,
        window.export_step_button,
        window.export_stl_button,
        window.export_dxf_button,
        window.export_all_button,
    )
    enabled_states = tuple(widget.isEnabled() for widget in controls)
    progress = window.operation_progress
    old_minimum = progress.minimum()
    old_maximum = progress.maximum()
    old_format = progress.format()
    try:
        for widget in controls:
            widget.setEnabled(False)
        progress.setRange(0, 0)
        progress.setFormat(message)
        progress.show()
        QApplication.processEvents()
        yield
    finally:
        for widget, enabled in zip(controls, enabled_states, strict=True):
            widget.setEnabled(enabled)
        progress.hide()
        progress.setRange(old_minimum, old_maximum)
        progress.setFormat(old_format)
        QApplication.processEvents()
