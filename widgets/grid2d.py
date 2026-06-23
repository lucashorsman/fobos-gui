import math
import sys

from PySide6.QtCore import QPointF, Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from helpers.annulus import solve_inverse_kinematics
from helpers.constants import SHORT_ARM_LENGTH, LONG_ARM_LENGTH
from helpers.drawing import draw_positioner
from widgets.pan_zoom_mixin import PanZoomMixin

class Grid2d(QWidget, PanZoomMixin):
    move_requested = Signal(int, float, float)
    selection_changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.init_pan_zoom()
        self.setMinimumSize(400, 300)
        self.setWindowTitle("Grid 2D")
        self.positioners_dict = {}
        self.target_points = []
        self.target_angles = {}
        self._selected_pid = None
        self.setMouseTracking(True)
        

    def update_display(self, positioners_dict, selected_pid=None):
        self.positioners_dict = positioners_dict
        self._selected_pid = selected_pid
        self.update()

    def update_positioners(self, pids):
        self._positioner_ids = sorted(pids)

    def wheelEvent(self, event):
        self.apply_wheel_zoom(event)
        self.update()

    def mousePressEvent(self, event):
        if self.start_pan(event):
            return

        if event.button() == Qt.MouseButton.LeftButton:
            phys_x, phys_y = self.get_physical_click_coords(event)
            
            closest_pid = None
            min_dist = float('inf')
            outer_radius = SHORT_ARM_LENGTH + LONG_ARM_LENGTH

            for pid, pos in self.positioners_dict.items():
                cx, cy = pos.get('center', (0.0, 0.0))
                dist = math.hypot(phys_x - cx, phys_y - cy)
                if dist <= outer_radius and dist < min_dist:
                    min_dist = dist
                    closest_pid = pid

            if closest_pid is not None:
                self.selection_changed.emit(closest_pid)

    def mouseMoveEvent(self, event):
        if self.do_pan(event):
            self.update()

    def mouseReleaseEvent(self, event):
        self.end_pan(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.positioners_dict:
            return

        painter.save()
        painter.translate(self._offset)
        painter.scale(self._scale, self._scale)

        for pid, pos in self.positioners_dict.items():
            is_selected = (pid == self._selected_pid)
            draw_positioner(painter, pid, pos, is_selected, draw_arms=True)

        # Draw Target Points
        for target in self.target_points:
            x, y = target
            painter.setPen(QPen(Qt.red))
            painter.setBrush(Qt.red)
            painter.drawEllipse(QPointF(x, y), 5, 5)

        painter.restore()