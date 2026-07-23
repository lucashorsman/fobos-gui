"""Widget for displaying live Vimba camera frames."""

from __future__ import annotations
import datetime
import os
import json
import cv2
from PySide6.QtCore import QTimer

import math
from PySide6.QtCore import QPoint, QPointF, Qt, Slot, Signal, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QImage, QPainter, QTransform, QPen, QPainterPath, QColor   
from PySide6.QtWidgets import QLabel, QListWidget, QMessageBox, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QDialog, QFormLayout, QLineEdit, QSlider
from helpers.constants import GRID_SPACING
from helpers.geometry import resolve_positioner_click
from helpers.projection import PositionerProjection
from helpers.drawing import draw_positioner, draw_coordinate_grid
from helpers.calibration_io import save_calibration, load_calibration, is_valid_calibration_quad
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

class CameraSettingsPanel(QWidget):
    exposure_changed = Signal(int)
    gain_changed = Signal(float)
    save_image_requested = Signal()
    
    # Milliseconds to wait after the slider stops before firing the signal.
    _DEBOUNCE_MS = 400

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Camera Functions")
        self.setLayout(QFormLayout())
        self.setAutoFillBackground(True)
        # Darker background for visibility over the camera
        self.setStyleSheet("CameraSettingsPanel { background-color: #2b2b2b; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; border: 1px solid #555; border-top: none; }")

        self.exposure_label = QLabel("10000 \u00B5s")
        self.exposure_slider = QSlider(Qt.Horizontal)
        self.exposure_slider.setRange(100, 100000)
        self.exposure_slider.setValue(10000)

        self.gain_label = QLabel("0.0 dB")
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setRange(0, 400)  # 0 to 40.0 dB
        self.gain_slider.setValue(0)

        layout = self.layout()
        layout.addRow("Exposure:", self.exposure_slider)
        layout.addRow("", self.exposure_label)
        layout.addRow("Gain:", self.gain_slider)
        layout.addRow("", self.gain_label)

        # Save Image button
        self.save_image_button = QPushButton("Save Image")
        self.save_image_button.setObjectName("save_image_button")
        self.save_image_button.clicked.connect(self.save_image_requested.emit)
        layout.addRow(self.save_image_button)

        # Debounce timers — restart on every slider tick, fire only when settled.
        self._exposure_timer = QTimer(self)
        self._exposure_timer.setSingleShot(True)
        self._exposure_timer.setInterval(self._DEBOUNCE_MS)
        self._exposure_timer.timeout.connect(self._emit_exposure)

        self._gain_timer = QTimer(self)
        self._gain_timer.setSingleShot(True)
        self._gain_timer.setInterval(self._DEBOUNCE_MS)
        self._gain_timer.timeout.connect(self._emit_gain)

        self.exposure_slider.valueChanged.connect(self.on_exposure_changed)
        self.gain_slider.valueChanged.connect(self.on_gain_changed)

    def on_exposure_changed(self, val):
        # Update the label immediately for snappy visual feedback.
        self.exposure_label.setText(f"{val} \u00B5s")
        # Restart the debounce timer; the signal fires only after the slider settles.
        self._exposure_timer.start()

    def _emit_exposure(self):
        self.exposure_changed.emit(self.exposure_slider.value())

    def on_gain_changed(self, val):
        gain_db = val / 10.0
        self.gain_label.setText(f"{gain_db:.1f} dB")
        self._gain_timer.start()

    def _emit_gain(self):
        self.gain_changed.emit(self.gain_slider.value() / 10.0)

class CameraWidget(QWidget, PanZoomMixin):
    move_requested = Signal(int, float, float)
    move_queued = Signal(int, list)
    selection_changed = Signal(int)
    swap_requested = Signal()
    exposure_changed = Signal(int)
    gain_changed = Signal(float)
    calibration_completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_pan_zoom()
        self._frame = None
        self._image = None
        self._calibration_mode = False
        self._selected_pid = None
        self._positioners_dict = {}  # initialized here; populated via update_display

        self.setMinimumSize(400, 300)
        self.setWindowTitle("Camera View")
        self.setMouseTracking(True)
        self.first_frame = True  # Flag to indicate if the first frame has been received
        # Create a placeholder image so the overlay can be tested without a real camera
        self._image = QImage(1920, 1080, QImage.Format_RGB32)
        self._image.fill(Qt.darkGray)

        self.projection = PositionerProjection()

        # Active physical reference points (TL, TR, BL, BR) in positioner mm coordinates.
        # These define what the 4 clicked camera points map TO during calibration.
        self.physical_pts = [(-50.165, 66.675), (55.88, 65.405), (-80.01, -68.58), (72.39, -69.85)]
        #this is found by counting the number of boxes, then multiplying by GRID_SPACING 
        self.camera_pts = []

        # Attempt to restore a previously saved calibration from disk
        saved = load_calibration()
        if saved is not None:
            physical_pts, camera_pts = saved
            self.physical_pts = list(physical_pts)
            self.camera_pts = list(camera_pts)
            try:
                self.projection.calibrate(self.physical_pts, self.camera_pts)
                QTimer.singleShot(0, self.calibration_completed.emit)
                print("CameraWidget: calibration restored from disk")
            except Exception as e:
                print(f"CameraWidget: failed to restore calibration: {e}")
                self.camera_pts = []
        
        # UI overlays
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        top_layout = QHBoxLayout()
        self.swap_button = QPushButton("Swap Views")
        self.swap_button.clicked.connect(self.swap_requested.emit)
        top_layout.addWidget(self.swap_button, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self.settings_button = QPushButton("Camera Functions")
        self.settings_button.clicked.connect(self.toggle_settings_panel)
        top_layout.addWidget(self.settings_button, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        
        layout.addLayout(top_layout)
        layout.addStretch()
        
        self.settings_panel = CameraSettingsPanel(self)
        self.settings_panel.exposure_changed.connect(self.exposure_changed.emit)
        self.settings_panel.gain_changed.connect(self.gain_changed.emit)
        self.settings_panel.save_image_requested.connect(self.save_current_frame)
        
        self._panel_visible = False
        self.panel_animation = QPropertyAnimation(self.settings_panel, b"pos")
        self.panel_animation.setDuration(300)
        self.panel_animation.setEasingCurve(QEasingCurve.OutCubic)

    def toggle_settings_panel(self):
        self.settings_panel.adjustSize()
        panel_x = (self.width() - self.settings_panel.width()) // 2
        
        self.settings_panel.show()
        self.settings_panel.raise_()
        
        self.panel_animation.stop()
        self.panel_animation.setStartValue(self.settings_panel.pos())
        
        if self._panel_visible:
            # Slide up
            self.panel_animation.setEndValue(QPoint(panel_x, -self.settings_panel.height()))
            self._panel_visible = False
            self.settings_button.setText("Camera Functions")
        else:
            # Slide down
            self.panel_animation.setEndValue(QPoint(panel_x, 0))
            self._panel_visible = True
            self.settings_button.setText("Hide Functions")
            
        self.panel_animation.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        panel_x = (self.width() - self.settings_panel.width()) // 2
        if self._panel_visible:
            self.settings_panel.move(panel_x, 0)
        else:
            self.settings_panel.move(panel_x, -self.settings_panel.height())

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

    @Slot()
    def save_current_frame(self):
        """Save the latest camera frame to a timestamped PNG file.

        Works with both StreamWorker and VimbaWorker since both store frames
        in self._frame via update_frame().  Falls back to saving the QImage
        if no numpy array is available (e.g. placeholder frame before camera
        connects).
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        save_dir = os.path.join(os.path.expanduser("~"), "Pictures", "fobos_captures")
        os.makedirs(save_dir, exist_ok=True)
        filename = os.path.join(save_dir, f"frame_{timestamp}.png")

        saved = False
        if self._frame is not None:
            try:
                cv2.imwrite(filename, self._frame)
                saved = True
            except Exception as exc:
                print(f"CameraWidget: cv2.imwrite failed: {exc}")

        if not saved and self._image is not None:
            try:
                self._image.save(filename)
                saved = True
            except Exception as exc:
                print(f"CameraWidget: QImage.save failed: {exc}")

        if saved:
            print(f"CameraWidget: frame saved to {filename}")

            metadata = {}
            if hasattr(self, "_positioners_dict") and self._positioners_dict:
                for pid, pdata in self._positioners_dict.items():
                    px, py = self.projection.physical_to_camera(pdata.center[0], pdata.center[1])
                    metadata[pid] = {
                        "alpha": pdata.alpha,
                        "beta": pdata.beta,
                        "pixel_x": px,
                        "pixel_y": py
                    }
            
            json_filename = os.path.join(save_dir, f"frame_{timestamp}.json")
            try:
                with open(json_filename, "w") as f:
                    json.dump(metadata, f, indent=4)
                print(f"CameraWidget: metadata saved to {json_filename}")
            except Exception as exc:
                print(f"CameraWidget: metadata save failed: {exc}")
        else:
            print("CameraWidget: no frame available to save")


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
        # Persist the calibration so it is restored automatically on the next launch
        try:
            save_calibration(self.physical_pts, self.camera_pts)
            print("CameraWidget: calibration written to disk")
        except Exception as e:
            print(f"CameraWidget: failed to save calibration: {e}")
        self.calibration_completed.emit()
        

    def get_physical_click_coords(self, event):
        raw_x, raw_y = super().get_physical_click_coords(event)
        if self.projection.is_calibrated:
            return self.projection.camera_to_physical(raw_x, raw_y)
        return raw_x, raw_y

    def mousePressEvent(self, event):
        if self.start_pan(event):
            return

        if event.button() != Qt.LeftButton or self._image is None:
            return
        if self._calibration_mode:
            # In calibration mode, we want to collect the clicked points
            if len(self.camera_pts) < 4:
                raw_pixel_x, raw_pixel_y = super().get_physical_click_coords(event)
                self.camera_pts.append((raw_pixel_x, raw_pixel_y))
                print(f"Calibration point {len(self.camera_pts)}: Camera pixel coordinates: ({raw_pixel_x}, {raw_pixel_y})")
                if len(self.camera_pts) < 4:
                    self.instruction_label.setText(f"Points collected: {len(self.camera_pts)}/4\nClick the next corner.")
                elif len(self.camera_pts) == 4:
                    self.instruction_label.setText("4 points collected!\nValidating and previewing projection...")
                    self.finish_button.setEnabled(True)
                    self.redo_button.setEnabled(True)

                    if not is_valid_calibration_quad(self.camera_pts):
                        self.instruction_label.setText(
                            "Points are nearly collinear or cover too small an area.\n"
                            "Please click 'Redo' and choose more spread-out corners."
                        )
                        self.finish_button.setEnabled(False)
                    else:
                        try:
                            self.projection.calibrate(self.physical_pts, self.camera_pts)
                        except Exception:
                            self.instruction_label.setText("Error during calibration! Please click 'Redo'.")
                            self.finish_button.setEnabled(False)

                    self.update()
            return
        if not self.projection.is_calibrated:
            QMessageBox.warning(self, "Calibration Required", "Please calibrate the camera before moving positioners.")
            return
        dest_x, dest_y = self.get_physical_click_coords(event)

        grid_x, grid_y = dest_x, dest_y

        action, pid, solutions = resolve_positioner_click(
            grid_x, grid_y, self._positioners_dict, self._selected_pid
        )

        if action == "select":
            self.selection_changed.emit(pid)
        elif action == "queue":
            self.move_queued.emit(pid, solutions)

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
        painter.scale(self._scale, -self._scale)
        # Image is pre-flipped in _frame_to_qimage so we can just draw it natively in this Cartesian space
        painter.drawImage(QPointF(-self._image.width() / 2, -self._image.height() / 2), self._image)
        painter.restore()

        # Draw the projected annulus overlay
        if self.projection.is_calibrated:
            painter.save()

            # Transform from physical space -> raw camera pixels
            t_proj = self.projection.get_qtransform()
            

            t_base = QTransform()
            t_base.translate(self._offset.x(), self._offset.y())
            t_base.scale(self._scale, -self._scale)
            
            # Combine transforms (right multiply applies t_proj first, then t_base)
            painter.setTransform(t_proj * t_base)

            # painter.translate(1275, 1087)

            # Calculate visible rect in physical coordinates
            inverse_transform, invertible = painter.transform().inverted()
            if invertible:
                visible_rect = inverse_transform.mapRect(QRectF(self.rect()))
                draw_coordinate_grid(painter, visible_rect, spacing=GRID_SPACING)

            positioner_items = self._positioners_dict.items()
            for pid, p_info in positioner_items:
                is_selected = (pid == self._selected_pid)
                draw_positioner(painter, pid, p_info, is_selected, draw_arms=True)



            painter.restore()

    def _frame_to_qimage(self, frame):
        if frame is None:
            return None

        if frame.ndim == 2:
            height, width = frame.shape
            bytes_per_line = width
            img = QImage(frame.data, width, height, bytes_per_line, QImage.Format_Grayscale8).copy()
            return img.mirrored(False, True)

        if frame.ndim == 3:
            if frame.shape[2] == 3:
                height, width, _ = frame.shape
                bytes_per_line = width * 3
                img = QImage(frame.data, width, height, bytes_per_line, QImage.Format_BGR888).copy()
                return img.mirrored(False, True)
            elif frame.shape[2] == 1:
                height, width, _ = frame.shape
                bytes_per_line = width
                img = QImage(frame.data, width, height, bytes_per_line, QImage.Format_Grayscale8).copy()
                return img.mirrored(False, True)

        return None