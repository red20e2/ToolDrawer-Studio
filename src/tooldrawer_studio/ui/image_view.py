from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView


class ZoomableImageView(QGraphicsView):
    """Pixel-space image view with wheel zoom, pan, Fit, and 1:1."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setZValue(0.0)
        self._scene.addItem(self._pixmap_item)
        self._user_transformed = False
        self._panning = False
        self._pan_start = QPointF()
        self._space_down = False
        self._gray: np.ndarray | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("imageWell")

    @property
    def pixmap_item(self) -> QGraphicsPixmapItem:
        return self._pixmap_item

    def image_gray(self) -> np.ndarray | None:
        return None if self._gray is None else self._gray.copy()

    def set_image_bytes(self, raw: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(raw):
            raise ValueError("Unsupported or invalid image data")
        self._pixmap_item.setPixmap(pixmap)
        self._pixmap_item.setPos(0.0, 0.0)
        self._pixmap_item.setScale(1.0)
        self._pixmap_item.setVisible(True)
        self._scene.setSceneRect(pixmap.rect())
        encoded = np.frombuffer(raw, dtype=np.uint8)
        pixels = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
        self._gray = None if pixels is None else pixels
        self._user_transformed = False
        self.fit_image()

    def set_scene_image(
        self,
        pixmap: QPixmap,
        *,
        x: float = 0.0,
        y: float = 0.0,
        scale: float = 1.0,
        visible: bool = True,
    ) -> None:
        self._pixmap_item.setPixmap(pixmap)
        self._pixmap_item.setPos(x, y)
        self._pixmap_item.setScale(scale)
        self._pixmap_item.setVisible(visible and not pixmap.isNull())
        self._gray = None
        self._user_transformed = False
        if pixmap.isNull():
            return
        width = pixmap.width() * scale
        height = pixmap.height() * scale
        self._scene.setSceneRect(x, y, width, height)
        self.fit_image()

    def set_pixmap_visible(self, visible: bool) -> None:
        self._pixmap_item.setVisible(visible and not self._pixmap_item.pixmap().isNull())

    def fit_image(self) -> None:
        pixmap = self._pixmap_item.pixmap()
        if pixmap.isNull() or not self._pixmap_item.isVisible():
            return
        self._user_transformed = False
        self.resetTransform()
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_1_to_1(self) -> None:
        if self._pixmap_item.pixmap().isNull():
            return
        self._user_transformed = True
        self.resetTransform()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if not self._user_transformed:
            self.fit_image()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._pixmap_item.pixmap().isNull() or event.angleDelta().y() == 0:
            super().wheelEvent(event)
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self._user_transformed = True
        self.scale(factor, factor)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = True
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_down = False
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _begin_pan(self, event: QMouseEvent) -> bool:
        is_middle = event.button() == Qt.MouseButton.MiddleButton
        is_space_left = (
            event.button() == Qt.MouseButton.LeftButton and self._space_down
        )
        if not is_middle and not is_space_left:
            return False
        self._panning = True
        self._pan_start = event.position()
        self._user_transformed = True
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()
        return True

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._begin_pan(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and event.button() in {
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.LeftButton,
        }:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)
