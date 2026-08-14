from __future__ import annotations

from collections.abc import Callable

import qrcode
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tooldrawer_studio.capture.pending import CaptureSessionService


def qr_image(url: str, scale: int = 6) -> QImage:
    if not url:
        raise ValueError("QR URL must not be empty")
    if scale <= 0:
        raise ValueError("QR scale must be positive")

    qr = qrcode.QRCode(border=4)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    module_count = len(matrix)
    image = QImage(
        module_count * scale,
        module_count * scale,
        QImage.Format.Format_RGB32,
    )
    white = QColor("white").rgb()
    black = QColor("black").rgb()
    image.fill(white)
    for row_index, row in enumerate(matrix):
        for column_index, filled in enumerate(row):
            if not filled:
                continue
            x0 = column_index * scale
            y0 = row_index * scale
            for y in range(y0, y0 + scale):
                for x in range(x0, x0 + scale):
                    image.setPixel(x, y, black)
    return image


class CaptureTrayWidget(QWidget):
    def __init__(
        self,
        service: CaptureSessionService,
        parent: QWidget | None = None,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._promote_callback: Callable[[str], None] | None = None
        self.compact = bool(compact)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self.collapse_button: QToolButton | None = None
        if self.compact:
            self.collapse_button = QToolButton()
            self.collapse_button.setText("Pending captures")
            self.collapse_button.setCheckable(True)
            self.collapse_button.setChecked(True)
            self.collapse_button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            self.collapse_button.setArrowType(Qt.ArrowType.DownArrow)
            self.collapse_button.toggled.connect(
                lambda checked: self.set_collapsed(not checked)
            )
            root.addWidget(self.collapse_button)

        self.body_widget = QWidget()
        root.addWidget(self.body_widget)
        body_layout = QVBoxLayout(self.body_widget) if self.compact else QHBoxLayout(self.body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(4)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._selection_changed)
        if self.compact:
            self.list_widget.setMaximumHeight(110)
            self.list_widget.setMinimumWidth(0)
            body_layout.addWidget(self.list_widget)
        else:
            self.list_widget.setMinimumWidth(220)
            body_layout.addWidget(self.list_widget, 1)

        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(4)
        self.preview_label = QLabel("No pending captures")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setScaledContents(False)
        if self.compact:
            self.preview_label.setMinimumSize(0, 80)
            self.preview_label.setMaximumHeight(135)
        else:
            self.preview_label.setMinimumSize(240, 180)
        preview_layout.addWidget(self.preview_label, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        self.rotate_button = QPushButton("Rotate 90°")
        self.delete_button = QPushButton("Delete")
        self.promote_button = QPushButton("Add to Project")
        self.rotate_button.clicked.connect(self._rotate_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.promote_button.clicked.connect(self._promote_selected)
        actions.addWidget(self.rotate_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.promote_button)
        preview_layout.addLayout(actions)
        if self.compact:
            body_layout.addWidget(preview_widget)
        else:
            body_layout.addWidget(preview_widget, 2)

        self._set_actions_enabled(False)
        self.refresh()

    def set_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        self.body_widget.setVisible(not collapsed)
        if self.collapse_button is not None:
            self.collapse_button.blockSignals(True)
            self.collapse_button.setChecked(not collapsed)
            self.collapse_button.setArrowType(
                Qt.ArrowType.RightArrow if collapsed else Qt.ArrowType.DownArrow
            )
            self.collapse_button.blockSignals(False)

    def set_promote_callback(self, callback: Callable[[str], None]) -> None:
        self._promote_callback = callback

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.rotate_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.promote_button.setEnabled(enabled)

    def _current_id(self) -> str | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def refresh(self) -> None:
        selected_id: str | None = None
        try:
            selected_id = self._service.selected().id
        except ValueError:
            selected_id = None

        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        selected_row = -1
        for row, item in enumerate(self._service.items()):
            list_item = QListWidgetItem(f"{item.source.title()}: {item.filename}")
            list_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.list_widget.addItem(list_item)
            if item.id == selected_id:
                selected_row = row
        self.list_widget.blockSignals(False)

        if self.list_widget.count() == 0:
            self.preview_label.clear()
            self.preview_label.setText("No pending captures")
            self._set_actions_enabled(False)
            return

        if selected_row < 0:
            selected_row = 0
        self.list_widget.setCurrentRow(selected_row)
        self._selection_changed(self.list_widget.currentItem(), None)

    def _selection_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self._set_actions_enabled(False)
            return
        pending_id = str(current.data(Qt.ItemDataRole.UserRole))
        self._service.select(pending_id)
        pixmap = QPixmap()
        if not pixmap.loadFromData(self._service.preview_png(pending_id)):
            raise ValueError("Could not display pending capture")
        target = self.preview_label.size()
        if target.width() > 0 and target.height() > 0:
            pixmap = pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.preview_label.setPixmap(pixmap)
        self._set_actions_enabled(True)

    def _rotate_selected(self) -> None:
        pending_id = self._current_id()
        if pending_id is None:
            return
        self._service.rotate(pending_id)
        self._selection_changed(self.list_widget.currentItem(), None)

    def _delete_selected(self) -> None:
        pending_id = self._current_id()
        if pending_id is None:
            return
        self._service.delete(pending_id)
        self.refresh()

    def _promote_selected(self) -> None:
        pending_id = self._current_id()
        if pending_id is None or self._promote_callback is None:
            return
        self._promote_callback(pending_id)
        self.refresh()
