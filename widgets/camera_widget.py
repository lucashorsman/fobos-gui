"""Widget for displaying live Vimba camera frames."""

from __future__ import annotations

import math
from PySide6.QtCore import QPoint, QPointF, Qt, Slot, Signal, QRectF
from PySide6.QtGui import QImage, QPainter, QTransform, QPen, QPainterPath, QColor   
from PySide6.QtWidgets import QLabel, QListWidget, QMessageBox, QPushButton, QListWidget, QVBoxLayout, QHBoxLayout, QWidget, QDialog, QFormLayout, QLineEdit
from helpers.constants import SHORT_ARM_LENGTH, LONG_ARM_LENGTH
from helpers.annulus import solve_inverse_kinematics
from helpers.projection import PositionerProjection
from helpers.drawing import draw_positioner, draw_coordinate_grid
from helpers.geometry import get_clicked_positioner
from widgets.pan_zoom_mixin import PanZoomMixin


class UnclosableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.allow_close = False
        
    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()

class CameraWidget(QWidget, PanZoomMixin):
    move_requested = Signal(int, float, float)
    move_queued = Signal(int, list)
    selection_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_pan_zoom()
        self._frame = None
        self._image = None
        self._calibration_mode = False
        self._selected_pid = None
        self.setMinimumSize(400, 300)
        self.setWindowTitle("Camera View")
        self.setMouseTracking(True)
        self.first_frame = True  # Flag to indicate if the first frame has been received
        # Create a placeholder image so the overlay can be tested without a real camera
        self._image = QImage(1920, 1080, QImage.Format_RGB32)
        self._image.fill(Qt.darkGray)

        self.projection = PositionerProjection()
        self.target_offset = None
        # Z-order (reading order): Top-Left, Top-Right, Bottom-Left, Bottom-Right
        self.physical_pts = [(825, 525), (1725, 525), (825, 1650), (1725, 1650)]
        self.camera_pts = []
        # Calibration: Mapping destination (rectified/physical) to source (camera pixels)
        # Using highly distorted camera points (a steep trapezoid) to test the projection warp!
        # self.projection.calibrate(
        #     physical_pts=[(825, 525), (1725, 525), (825, 1650), (1725, 1650)],
        #     camera_pts=[(800, 300), (1100, 300), (200, 900), (1700, 900)]
        # )
        #less insane projection from jchen
        # self.projection.calibrate(
        # physical_pts=[(825, 525), (1725, 525), (825, 1650), (1725, 1650)],
        # camera_pts=[(825, 525), (1725, 525), (825, 1650), (1725, 1650)]
        # )
        

    def fit_to_view(self):
        if self._image is None:
            return
        w_ratio = self.width() / self._image.width()
        h_ratio = self.height() / self._image.height()
        self._scale = min(w_ratio, h_ratio)
        self._offset = QPointF(self.width() / 2, self.height() / 2)
        self.update()

    def update_display(self, positioners_dict, selected_pid=None):
        self._positioners_dict = positioners_dict
        self._selected_pid = selected_pid
        self.update()

    @Slot(object)
    def update_frame(self, frame):
        self._frame = frame.copy() if hasattr(frame, "copy") else frame
        self._image = self._frame_to_qimage(self._frame)
        if self.first_frame:
            self.fit_to_view()
            self.first_frame = False
        else:
            self.update()
        
    def start_calibration(self):
        self.camera_pts = []
        self.projection.reset()
        self.update()
        #create the calibration dialogbox
        self.calibration_dialog = UnclosableDialog(self)
        self.calibration_dialog.setWindowTitle("Calibration")
        self._calibration_mode = True
        #fix the size of the dialog box
        self.calibration_dialog.setFixedSize(400, 200)
        #layout text instructions in the dialog box
        self.calibration_dialog.setLayout(QFormLayout())
        self.instruction_label = QLabel("Click on the 4 corners in this exact order:\n1. Top-Left\n2. Top-Right\n3. Bottom-Left\n4. Bottom-Right")
        self.calibration_dialog.layout().addRow("Instructions:", self.instruction_label)
        
        button_layout = QHBoxLayout()
        
        self.redo_button = QPushButton("Redo")
        self.redo_button.setEnabled(False)
        self.redo_button.clicked.connect(self.on_calibration_redo)
        button_layout.addWidget(self.redo_button)
        
        self.finish_button = QPushButton("Finish Calibration")
        self.finish_button.setEnabled(False)
        self.finish_button.clicked.connect(self.on_calibration_completed)
        button_layout.addWidget(self.finish_button)
        
        self.calibration_dialog.layout().addRow(button_layout)
        #force it on top of the main window

        self.calibration_dialog.setWindowFlags(self.calibration_dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        # You can adjust these X and Y coordinates to spawn it exactly where you want
        main_pos = self.window().pos()
        self.calibration_dialog.move(main_pos.x()+800 , main_pos.y()+600)
        
        #display asynchronously
        self.calibration_dialog.show()

    def on_calibration_redo(self):
        self.camera_pts = []
        self.projection.reset()
        self.instruction_label.setText("Click on the 4 corners in this exact order:\n1. Top-Left\n2. Top-Right\n3. Bottom-Left\n4. Bottom-Right")
        self.finish_button.setEnabled(False)
        self.redo_button.setEnabled(False)
        self.update()

    def on_calibration_completed(self):
        print("Calibration saved with points:", self.camera_pts)
        self._calibration_mode = False
        self.calibration_dialog.allow_close = True
        self.calibration_dialog.close()
        
    def _normalize_for_positioner(self, angle_deg):
        adjusted = float(angle_deg)
        while adjusted < -10.0:
            adjusted += 360.0
        while adjusted > 370.0:
            adjusted -= 360.0
        return adjusted

    def mousePressEvent(self, event):
        if self.start_pan(event):
            return

        if event.button() != Qt.LeftButton or self._image is None:
            return
        if self._calibration_mode:
            # In calibration mode, we want to collect the clicked points
            if len(self.camera_pts) < 4:
                raw_pixel_x, raw_pixel_y = self.get_physical_click_coords(event)
                self.camera_pts.append((raw_pixel_x, raw_pixel_y))
                print(f"Calibration point {len(self.camera_pts)}: Camera pixel coordinates: ({raw_pixel_x}, {raw_pixel_y})")
                if len(self.camera_pts) < 4:
                    self.instruction_label.setText(f"Points collected: {len(self.camera_pts)}/4\nClick the next corner.")
                elif len(self.camera_pts) == 4:
                    self.instruction_label.setText("4 points collected!\nPreviewing projection... Click 'Finish' to save or 'Redo' to try again.")
                    self.finish_button.setEnabled(True)
                    self.redo_button.setEnabled(True)
                    
                    try:
                        self.projection.calibrate(self.physical_pts, self.camera_pts)
                    except Exception as e:
                        self.instruction_label.setText("Error during calibration! Please click 'Redo'.")
                        self.finish_button.setEnabled(False)
                    
                    self.update()
            return
        raw_pixel_x, raw_pixel_y = self.get_physical_click_coords(event)
        dest_x, dest_y = self.projection.camera_to_physical(raw_pixel_x, raw_pixel_y)

        # Convert destination physical space to grid space (we translate painter by 1275, 1087)
        # grid_x = dest_x - 1275
        # grid_y = dest_y - 1087
        grid_x, grid_y = dest_x, dest_y

        positioners_dict = getattr(self, '_positioners_dict', {})
        closest_pid = get_clicked_positioner(grid_x, grid_y, positioners_dict, self._selected_pid)

        if closest_pid is None:
            return

        if closest_pid is not None and closest_pid != self._selected_pid:
            self.selection_changed.emit(closest_pid)
            return

        cx, cy = self._positioners_dict[closest_pid].get("center", (0.0, 0.0))
        rel_x = grid_x - cx
        rel_y = grid_y - cy

        self.target_offset = (rel_x, rel_y)

        # Calculate IK
        solutions = solve_inverse_kinematics(rel_x, rel_y, SHORT_ARM_LENGTH, LONG_ARM_LENGTH)
        if solutions:
            normalized_solutions = [
                (self._normalize_for_positioner(a), self._normalize_for_positioner(b)) 
                for a, b in solutions
            ]
            self.move_queued.emit(closest_pid, normalized_solutions)

        self.update()
      
    def wheelEvent(self, event):
        self.apply_wheel_zoom(event)
        self.update()

    def mouseMoveEvent(self, event):
        if self.do_pan(event):
            self.update()

    def mouseReleaseEvent(self, event):
        self.end_pan(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._image is None:
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignCenter, "Waiting for camera frame")
            return

        painter.save()
        painter.translate(self._offset)
        painter.scale(self._scale, self._scale)
        painter.drawImage(QPointF(-self._image.width() / 2, -self._image.height() / 2), self._image)
        painter.restore()

        # Draw the projected annulus overlay
        if self.projection.is_calibrated:
            painter.save()

            # Transform from physical space -> raw camera pixels
            t_proj = self.projection.get_qtransform()
            

            t_base = QTransform()
            t_base.translate(self._offset.x(), self._offset.y())
            t_base.scale(self._scale, self._scale)
            
            # Combine transforms (right multiply applies t_proj first, then t_base)
            painter.setTransform(t_proj * t_base)

            # painter.translate(1275, 1087)

            # Calculate visible rect in physical coordinates
            inverse_transform, invertible = painter.transform().inverted()
            if invertible:
                visible_rect = inverse_transform.mapRect(QRectF(self.rect()))
                draw_coordinate_grid(painter, visible_rect, spacing=100.0)

            positioner_items = self._positioners_dict.items() if hasattr(self, '_positioners_dict') else []
            for pid, p_info in positioner_items:
                is_selected = (pid == self._selected_pid)
                draw_positioner(painter, pid, p_info, is_selected, draw_arms=True)

                if is_selected and self.target_offset is not None:
                    painter.save()
                    cx, cy = p_info.get("center", (0.0, 0.0))
                    painter.translate(cx, cy)
                    pen = QPen(Qt.red)
                    pen.setCosmetic(True)
                    painter.setPen(pen)
                    painter.setBrush(Qt.red)
                    painter.drawEllipse(QPointF(self.target_offset[0], self.target_offset[1]), 1.5, 1.5)
                    painter.restore()

            painter.restore()

    def _frame_to_qimage(self, frame):
        if frame is None:
            return None

        if frame.ndim == 2:
            height, width = frame.shape
            bytes_per_line = width
            return QImage(frame.data, width, height, bytes_per_line, QImage.Format_Grayscale8).copy()

        if frame.ndim == 3:
            if frame.shape[2] == 3:
                height, width, _ = frame.shape
                bytes_per_line = width * 3
                return QImage(frame.data, width, height, bytes_per_line, QImage.Format_BGR888).copy()
            elif frame.shape[2] == 1:
                height, width, _ = frame.shape
                bytes_per_line = width
                return QImage(frame.data, width, height, bytes_per_line, QImage.Format_Grayscale8).copy()

        return None