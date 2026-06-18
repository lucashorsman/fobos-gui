"""Widget for displaying live Vimba camera frames."""

from __future__ import annotations

import math
from PySide6.QtCore import QPoint, QPointF, Qt, Slot, Signal, QRectF
from PySide6.QtGui import QImage, QPainter, QTransform, QPen, QPainterPath, QColor   
from PySide6.QtWidgets import QWidget

from helpers.constants import SHORT_ARM_LENGTH, LONG_ARM_LENGTH
from helpers.annulus import solve_inverse_kinematics
from helpers.projection import PositionerProjection


class CameraWidget(QWidget):
    move_requested = Signal(int, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = None
        self._image = None
        self._selected_pid = None
        self.setMinimumSize(400, 300)
        self.setWindowTitle("Camera View")

        # Create a placeholder image so the overlay can be tested without a real camera
        self._image = QImage(1920, 1080, QImage.Format_RGB32)
        self._image.fill(Qt.darkGray)

        self.projection = PositionerProjection()
        self.target_offset = None

        # Calibration: Mapping destination (rectified/physical) to source (camera pixels)
        # Using highly distorted camera points (a steep trapezoid) to test the projection warp!
        self.projection.calibrate(
            physical_pts=[(825, 525), (1725, 525), (825, 1650), (1725, 1650)],
            camera_pts=[(800, 300), (1100, 300), (200, 900), (1700, 900)]
        )

    def update_display(self, positioners_dict, selected_pid=None):
        self._positioners_dict = positioners_dict
        self._selected_pid = selected_pid
        self.update()

    @Slot(object)
    def update_frame(self, frame):
        self._frame = frame.copy() if hasattr(frame, "copy") else frame
        self._image = self._frame_to_qimage(self._frame)
        self.update()

    def _normalize_for_positioner(self, angle_deg):
        adjusted = float(angle_deg)
        while adjusted < -10.0:
            adjusted += 360.0
        while adjusted > 370.0:
            adjusted -= 360.0
        return adjusted

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._image is None:
            return

        click = event.position()
        available = self.rect().adjusted(8, 8, -8, -8)
        scaled = self._image.scaled(available.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = available.x() + (available.width() - scaled.width()) // 2
        y = available.y() + (available.height() - scaled.height()) // 2

        # 1. Map widget click to raw image pixels
        scale_x = scaled.width() / self._image.width()
        scale_y = scaled.height() / self._image.height()
        
        raw_pixel_x = (click.x() - x) / scale_x
        raw_pixel_y = (click.y() - y) / scale_y

        # 2. Map raw pixels to destination coordinates
        dest_x, dest_y = self.projection.camera_to_physical(raw_pixel_x, raw_pixel_y)

        # 3. Apply the offset to get actual physical mm relative to the positioner center
        # We previously translated the painter by (1275, 1087), so we subtract it here.
        if hasattr(self, '_positioners_dict') and self._selected_pid in self._positioners_dict:
            cx, cy = self._positioners_dict[self._selected_pid].get("center", (0.0, 0.0))
        else:
            cx, cy = 0.0, 0.0

        phys_x = dest_x - (1275 + cx)
        phys_y = dest_y - (1087 + cy)

        self.target_offset = (phys_x, phys_y)

        # 4. Calculate IK
        solutions = solve_inverse_kinematics(phys_x, phys_y, SHORT_ARM_LENGTH, LONG_ARM_LENGTH)
        if solutions:
            alpha_1, beta_1 = solutions[0]
            alpha_1 = self._normalize_for_positioner(alpha_1)
            beta_1 = self._normalize_for_positioner(beta_1)
            print(f"IK was calculated for position ({phys_x:.2f}, {phys_y:.2f}) -> alpha: {alpha_1:.2f}, beta: {beta_1:.2f}")
            if self._selected_pid is not None:
                print(f"Emitting move_requested for PID {self._selected_pid} with alpha={alpha_1:.2f}, beta={beta_1:.2f}")
                self.move_requested.emit(self._selected_pid, alpha_1, beta_1)
            else:
                print("No positioner selected in UI, so 'move_requested' signal was not emitted.")
        else:
            print(f"No IK solution for physical point: {phys_x:.2f}, {phys_y:.2f} (Dest: {dest_x:.2f}, {dest_y:.2f})")

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._image is None:
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignCenter, "Waiting for camera frame")
            return

        available = self.rect().adjusted(8, 8, -8, -8)
        scaled = self._image.scaled(available.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = available.x() + (available.width() - scaled.width()) // 2
        y = available.y() + (available.height() - scaled.height()) // 2
        painter.drawImage(QPoint(x, y), scaled)

        # Draw the projected annulus overlay
        if self.projection.is_calibrated:
            painter.save()

            # Transform from physical space -> raw camera pixels
            t_proj = self.projection.get_qtransform()
            
            # Transform from raw camera pixels -> scaled widget space
            scale_x = scaled.width() / self._image.width()
            scale_y = scaled.height() / self._image.height()
            
            t_base = QTransform()
            t_base.translate(x, y)
            t_base.scale(scale_x, scale_y)
            
            # Combine transforms (right multiply applies t_proj first, then t_base)
            painter.setTransform(t_proj * t_base)

            # Move origin to the center of the provided destination coordinates so the annulus grid is visible
            painter.translate(1275, 1087)

            inner_radius = abs(SHORT_ARM_LENGTH - LONG_ARM_LENGTH)
            outer_radius = SHORT_ARM_LENGTH + LONG_ARM_LENGTH

            positioner_items = self._positioners_dict.items() if hasattr(self, '_positioners_dict') else []
            for pid, p_info in positioner_items:
                cx, cy = p_info.get("center", (0.0, 0.0))
                painter.save()
                painter.translate(cx, cy)

                is_selected = (pid == self._selected_pid)

                if is_selected:
                    pen = QPen(Qt.green)
                    pen.setWidthF(0.5) # Thin line in physical space
                    pen.setCosmetic(True) # Line width remains constant regardless of transform
                    painter.setPen(pen)

                    path = QPainterPath()
                    path.addEllipse(QPointF(0, 0), outer_radius, outer_radius)
                    path.addEllipse(QPointF(0, 0), inner_radius, inner_radius)
                    
                    painter.setBrush(QColor(0, 255, 0, 50)) # Semi-transparent green
                    painter.drawPath(path)
                else:
                    pen = QPen(QColor(0, 150, 0, 100)) # Faint green
                    pen.setWidthF(0.5)
                    pen.setCosmetic(True)
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)

                    painter.drawEllipse(QPointF(0, 0), inner_radius, inner_radius)
                    painter.drawEllipse(QPointF(0, 0), outer_radius, outer_radius)

                # Draw positioner ID text
                font = painter.font()
                font.setPixelSize(40) # 40mm tall in physical space
                painter.setFont(font)
                
                if is_selected:
                    painter.setPen(Qt.white)
                else:
                    painter.setPen(QColor(200, 200, 200, 150))
                    
                rect = QRectF(-50, -50, 100, 100)
                painter.drawText(rect, Qt.AlignCenter, str(pid))

                # Draw target point if exists and is selected
                if is_selected and self.target_offset is not None:
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