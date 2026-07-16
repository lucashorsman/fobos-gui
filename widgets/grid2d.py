from widgets.pan_zoom_mixin import PanZoomMixin
from helpers.drawing import draw_positioner, draw_coordinate_grid
from helpers.geometry import resolve_positioner_click
import math
import sys

from PySide6.QtCore import QPointF, Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import QApplication, QPushButton, QWidget, QVBoxLayout

from helpers.constants import GRID_SPACING

class Grid2d(QWidget, PanZoomMixin):
    move_requested = Signal(int, float, float)
    move_queued = Signal(int, list)
    selection_changed = Signal(int)
    swap_requested = Signal()

    def __init__(self):
        super().__init__()
        self.init_pan_zoom()
        self.setMinimumSize(400, 300)
        self.setWindowTitle("Grid 2D")
        self.positioners_dict = {}
        self._selected_pid = None
        self.setMouseTracking(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.swap_button = QPushButton("Swap Views")
        self.swap_button.clicked.connect(self.swap_requested.emit)
        layout.addWidget(self.swap_button, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        


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

            action, pid, solutions = resolve_positioner_click(
                phys_x, phys_y, self.positioners_dict, self._selected_pid
            )

            if action == "select":
                print(f"Selected PID {pid}")
                self.selection_changed.emit(pid)
            elif action == "queue":
                self.move_queued.emit(pid, solutions)

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
        painter.scale(self._scale, -self._scale)

        # Calculate visible rect in physical coordinates
        inverse_transform, invertible = painter.transform().inverted()
        if invertible:
            visible_rect = inverse_transform.mapRect(QRectF(self.rect()))
            draw_coordinate_grid(painter, visible_rect, spacing=GRID_SPACING)

        for pid, pos in self.positioners_dict.items():
            is_selected = (pid == self._selected_pid)
            draw_positioner(painter, pid, pos, is_selected, draw_arms=True)

        painter.restore()