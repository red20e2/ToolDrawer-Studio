from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QStyleFactory,
    QVBoxLayout,
    QWidget,
)

ACCENT = "#e0a04a"
ACCENT_HOVER = "#ebb05c"
BACKGROUND = "#1b1e24"
SURFACE = "#242830"
SURFACE_RAISED = "#2c323c"
BORDER = "#3d4450"
TEXT = "#e8eaed"
MUTED = "#9aa3b2"
DANGER = "#c75b5b"

STYLESHEET = f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}}
QMainWindow, QDialog, QStatusBar, QMenuBar, QMenu, QMessageBox {{
    background-color: {BACKGROUND};
    color: {TEXT};
}}
QStatusBar {{
    border-top: 1px solid {BORDER};
    color: {MUTED};
}}
QLabel, QCheckBox, QRadioButton, QWidget#stageHeader {{
    background: transparent;
}}
QSplitter {{
    background: transparent;
}}
QTabWidget {{
    background: transparent;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    top: -1px;
    background: {SURFACE};
}}
QTabBar::tab {{
    background: {BACKGROUND};
    color: {MUTED};
    padding: 9px 16px;
    margin-right: 3px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border: 1px solid transparent;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}
QTabBar::tab:disabled {{
    color: #5c6370;
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
    background: {SURFACE_RAISED};
}}
QPushButton {{
    background: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 28px;
}}
QPushButton:hover {{
    background: #353c48;
}}
QPushButton:pressed {{
    background: #1f242c;
}}
QPushButton:disabled {{
    color: #6b7280;
    background: #22262e;
    border-color: #323844;
}}
QPushButton[role="primary"] {{
    background: {ACCENT};
    color: #1b1e24;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton[role="primary"]:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton[role="primary"]:disabled {{
    background: #8a6a3a;
    color: #2a2418;
    border-color: #8a6a3a;
}}
QPushButton[role="danger"] {{
    color: #f3d4d4;
    border-color: {DANGER};
}}
QPushButton[role="danger"]:hover {{
    background: #3a2428;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QPlainTextEdit {{
    background: #1a1d23;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 26px;
    selection-background-color: {ACCENT};
    selection-color: #1b1e24;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QAbstractItemView {{
    background: #1a1d23;
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: #1b1e24;
    border: 1px solid {BORDER};
}}
QCheckBox, QRadioButton {{
    spacing: 8px;
}}
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {ACCENT};
}}
QLabel#stageTitle {{
    font-size: 16pt;
    font-weight: 600;
    color: {TEXT};
    background: transparent;
}}
QLabel#stageSubtitle {{
    color: {MUTED};
    background: transparent;
}}
QLabel#mutedLabel, QLabel#stageSubtitle {{
    color: {MUTED};
}}
QLabel#sectionTitle {{
    font-size: 11pt;
    font-weight: 600;
    color: {TEXT};
    background: transparent;
}}
QLabel#phoneQr {{
    background: #ffffff;
    border-radius: 8px;
    padding: 8px;
}}
QGraphicsView#imageWell, QLabel#imageWell, QWidget#imageWell {{
    background: #12141a;
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QWidget#sidePanel, QScrollArea#sidePanel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QSplitter::handle {{
    background: {BORDER};
}}
QSplitter::handle:horizontal {{
    width: 2px;
    margin: 8px 4px;
}}
QMessageBox QLabel {{
    background: transparent;
}}
QProgressBar {{
    background: #1a1d23;
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {TEXT};
    text-align: center;
    min-height: 18px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 5px;
}}
QScrollBar:vertical {{
    background: {SURFACE};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #4a5260;
    min-height: 24px;
    border-radius: 6px;
}}
QScrollBar:horizontal {{
    background: {SURFACE};
    height: 12px;
}}
QScrollBar::handle:horizontal {{
    background: #4a5260;
    min-width: 24px;
    border-radius: 6px;
}}
QToolTip {{
    background: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 8px;
}}
"""


def _palette() -> QPalette:
    palette = QPalette()
    background = QColor(BACKGROUND)
    text = QColor(TEXT)
    muted = QColor(MUTED)
    accent = QColor(ACCENT)
    base = QColor("#1a1d23")
    palette.setColor(QPalette.ColorRole.Window, background)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1b1e24"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
    palette.setColor(QPalette.ColorRole.BrightText, accent)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, muted)
    return palette


def apply_theme(app: QApplication | None = None) -> None:
    application = app or QApplication.instance()
    if application is None:
        return
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        application.setStyle(fusion)
    application.setPalette(_palette())
    application.setStyleSheet(STYLESHEET)
    font = QFont("Segoe UI")
    font.setPointSize(10)
    application.setFont(font)


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def mark_primary(button: QPushButton) -> QPushButton:
    button.setProperty("role", "primary")
    _repolish(button)
    return button


def mark_danger(button: QPushButton) -> QPushButton:
    button.setProperty("role", "danger")
    _repolish(button)
    return button


def stage_header(title: str, subtitle: str) -> QWidget:
    wrap = QWidget()
    wrap.setObjectName("stageHeader")
    layout = QVBoxLayout(wrap)
    layout.setContentsMargins(0, 0, 0, 8)
    layout.setSpacing(2)
    title_label = QLabel(title)
    title_label.setObjectName("stageTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("stageSubtitle")
    subtitle_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return wrap


def muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("mutedLabel")
    label.setWordWrap(True)
    return label
