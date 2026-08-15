from __future__ import annotations

import math

import cadquery as cq
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QWidget


class ModelPreview(QWidget):
    """Small dependency-free shaded preview for a tessellated CadQuery solid."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 260)
        self.setMouseTracking(True)
        self.vertices = np.empty((0, 3), dtype=float)
        self.triangles = np.empty((0, 3), dtype=np.int64)
        self.yaw_deg = 35.0
        self.pitch_deg = -25.0
        self.zoom = 1.0
        self.pan = np.zeros(2, dtype=float)
        self._last_mouse = None
        self._drag_button = Qt.MouseButton.NoButton

    def reset_view(self) -> None:
        self.yaw_deg = 35.0
        self.pitch_deg = -25.0
        self.zoom = 1.0
        self.pan[:] = 0.0
        self.update()

    def clear_model(self) -> None:
        self.vertices = np.empty((0, 3), dtype=float)
        self.triangles = np.empty((0, 3), dtype=np.int64)
        self.update()

    def set_model(self, model: cq.Workplane) -> None:
        shape = model.val()
        vertices, triangles = shape.tessellate(0.35, 0.15)
        vertex_array = np.array(
            [[float(v.x), float(v.y), float(v.z)] for v in vertices], dtype=float
        )
        triangle_array = np.array(triangles, dtype=np.int64)
        if vertex_array.size:
            bounds_center = (vertex_array.min(axis=0) + vertex_array.max(axis=0)) / 2.0
            vertex_array -= bounds_center
        self.vertices = vertex_array
        self.triangles = triangle_array.reshape((-1, 3)) if triangle_array.size else np.empty((0, 3), dtype=np.int64)
        self.reset_view()

    def _rotation_matrix(self) -> np.ndarray:
        yaw = math.radians(self.yaw_deg)
        pitch = math.radians(self.pitch_deg)
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        yaw_matrix = np.array(
            [[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]], dtype=float
        )
        pitch_matrix = np.array(
            [[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]], dtype=float
        )
        return pitch_matrix @ yaw_matrix

    def _project(self) -> tuple[np.ndarray, np.ndarray]:
        if not self.vertices.size:
            return np.empty((0, 2)), np.empty((0,))
        rotated = self.vertices @ self._rotation_matrix().T
        span = np.ptp(rotated[:, :2], axis=0)
        natural = max(float(span[0]), float(span[1]), 1.0)
        scale = min(self.width(), self.height()) * 0.78 / natural * self.zoom
        screen = np.empty((rotated.shape[0], 2), dtype=float)
        screen[:, 0] = self.width() / 2.0 + self.pan[0] + rotated[:, 0] * scale
        screen[:, 1] = self.height() / 2.0 + self.pan[1] - rotated[:, 1] * scale
        return screen, rotated[:, 2]

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#12141a"))
        if not self.vertices.size or not self.triangles.size:
            painter.setPen(QColor("#9aa3b2"))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Generate the organizer to preview the 3D model",
            )
            return

        screen, depth = self._project()
        rotated = self.vertices @ self._rotation_matrix().T
        faces: list[tuple[float, np.ndarray, float]] = []
        light = np.array([0.25, -0.35, 0.90], dtype=float)
        light /= np.linalg.norm(light)
        for triangle in self.triangles:
            points3 = rotated[triangle]
            normal = np.cross(points3[1] - points3[0], points3[2] - points3[0])
            normal_length = float(np.linalg.norm(normal))
            if normal_length <= 1e-12:
                continue
            normal /= normal_length
            shade = max(0.18, min(1.0, 0.40 + 0.60 * abs(float(np.dot(normal, light)))))
            faces.append((float(depth[triangle].mean()), triangle, shade))
        faces.sort(key=lambda item: item[0])

        outline = QPen(self.palette().mid().color())
        outline.setWidthF(0.6)
        for _z, triangle, shade in faces:
            value = int(80 + 145 * shade)
            polygon = QPolygonF(
                [QPointF(float(screen[index, 0]), float(screen[index, 1])) for index in triangle]
            )
            painter.setPen(outline)
            painter.setBrush(QBrush(QColor(value, value, value)))
            painter.drawPolygon(polygon)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._last_mouse = event.position()
        self._drag_button = event.button()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_mouse is None:
            return
        delta = event.position() - self._last_mouse
        self._last_mouse = event.position()
        if self._drag_button == Qt.MouseButton.LeftButton:
            self.yaw_deg += delta.x() * 0.6
            self.pitch_deg = max(-89.0, min(89.0, self.pitch_deg + delta.y() * 0.6))
        elif self._drag_button in {Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton}:
            self.pan[0] += delta.x()
            self.pan[1] += delta.y()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        del event
        self._last_mouse = None
        self._drag_button = Qt.MouseButton.NoButton

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() / 120.0
        self.zoom = max(0.15, min(8.0, self.zoom * (1.12 ** steps)))
        self.update()
