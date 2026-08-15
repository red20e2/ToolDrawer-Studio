from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.capture.pending import CaptureSessionService
from tooldrawer_studio.ui.calibration_sidebar import CalibrationSidebar
from tooldrawer_studio.ui.calibration_view import CalibrationImageView


class CalibrationWorkspace(QWidget):
    def __init__(
        self,
        capture_service: CaptureSessionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sidebar_collapsed = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.view = CalibrationImageView()
        self.view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.view, 1)

        self.collapse_rail = QWidget()
        self.collapse_rail.setFixedWidth(28)
        rail_layout = QVBoxLayout(self.collapse_rail)
        rail_layout.setContentsMargins(1, 4, 1, 4)
        rail_layout.setSpacing(0)
        self.collapse_button = QToolButton()
        self.collapse_button.setText(">")
        self.collapse_button.setToolTip("Hide calibration controls")
        self.collapse_button.clicked.connect(self.toggle_sidebar)
        rail_layout.addWidget(self.collapse_button)
        rail_layout.addStretch()
        layout.addWidget(self.collapse_rail)

        self.sidebar = CalibrationSidebar(capture_service)
        self.sidebar.setFixedWidth(320)
        layout.addWidget(self.sidebar)

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        self._sidebar_collapsed = bool(collapsed)
        self.sidebar.setVisible(not self._sidebar_collapsed)
        self.collapse_button.setText("<" if self._sidebar_collapsed else ">")
        self.collapse_button.setToolTip(
            "Show calibration controls"
            if self._sidebar_collapsed
            else "Hide calibration controls"
        )

    def sidebar_is_collapsed(self) -> bool:
        return self._sidebar_collapsed

    def toggle_sidebar(self) -> None:
        self.set_sidebar_collapsed(not self._sidebar_collapsed)
