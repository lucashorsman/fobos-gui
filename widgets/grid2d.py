from widgets.pan_zoom_mixin import PanZoomMixin
from helpers.drawing import draw_positioner
from helpers.geometry import get_clicked_positioner
import math
import sys

from PySide6.QtCore import QPointF, Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from helpers.annulus import solve_inverse_kinematics
from helpers.constants import SHORT_ARM_LENGTH, LONG_ARM_LENGTH

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
            
            closest_pid = get_clicked_positioner(phys_x, phys_y, self.positioners_dict, self._selected_pid)
            
            if closest_pid is None:
                return

            #if pid swapped, then dont move arms
            if closest_pid is not None and closest_pid != self._selected_pid:
                print(f"Selected PID {closest_pid}")
                self.selection_changed.emit(closest_pid)
                return 
            
            cx, cy = self.positioners_dict[closest_pid].get('center', (0.0, 0.0))
            rel_x = phys_x - cx
            rel_y = phys_y - cy
            
            solutions = solve_inverse_kinematics(rel_x, rel_y, SHORT_ARM_LENGTH, LONG_ARM_LENGTH)
            if solutions:
                alpha_1, beta_1 = solutions[0]
                self.move_requested.emit(closest_pid, alpha_1, beta_1)

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