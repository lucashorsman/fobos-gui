"""Assembles all widgets, wires signals/slots between components, owns layout.

After the decomposition, MainWindow is purely a UI assembly and signal-routing
layer.  Move dispatch lives in MoveDispatcher, hardware lifecycle lives in
HardwareManager.
"""

from widgets.grid2d import Grid2d
from PySide6.QtWidgets import QMainWindow, QWidget, QSplitter, QLabel
from PySide6.QtCore import Qt, QEvent
from core.app_model import AppModel
from core.hardware_manager import HardwareManager
from core.move_dispatcher import MoveDispatcher
from widgets.camera_widget import CameraWidget
from widgets.status_bar import StatusBar
from widgets.control_panel import ControlPanel
from helpers.constants import PositionerState
import os


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fobos GUI")
        self.setGeometry(100, 100, 1800, 1000)

        # -- Core components --
        self.model = AppModel()
        self.hardware = HardwareManager(self.model, parent=self)
        self.dispatcher = MoveDispatcher(self.model, parent=self)

        # -- UI widgets --
        self.status_bar = StatusBar()
        self.control_panel = ControlPanel()
        self.grid2D = Grid2d()
        self.camera_widget = CameraWidget()

        # -- Stylesheet --
        style_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "style.qss")
        if os.path.exists(style_path):
            with open(style_path, "r") as f:
                self.setStyleSheet(f.read())

        # -- Layout --
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(self.status_bar)
        self.right_splitter.addWidget(self.camera_widget)
        self.right_splitter.addWidget(self.control_panel)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.grid2D)
        self.main_splitter.addWidget(self.right_splitter)

        self.main_splitter.setSizes([700, 300])
        self.right_splitter.setSizes([205, 620, 200])

        self.setCentralWidget(self.main_splitter)

        self.current_main_view = self.grid2D
        self.current_small_view = self.camera_widget
        self.current_main_view.swap_button.setVisible(False)
        self.current_small_view.swap_button.setVisible(True)

        # Used to detect PID-switch and settle events in _on_model_updated
        self._prev_selected_pid: int | None = None
        self._prev_selected_state: str | None = None

        self.mouse_coord_label = QLabel("X: --, Y: --")
        self.mouse_coord_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.statusBar().addPermanentWidget(self.mouse_coord_label)
        self.grid2D.installEventFilter(self)
        self.camera_widget.installEventFilter(self)

        # -- Wire signals --
        self._wire_model_signals()
        self._wire_hardware_signals()
        self._wire_dispatcher_signals()
        self._wire_widget_signals()

        # -- Start hardware --
        self.hardware.start_fps()
        self.hardware.start_camera()

    # -- Signal wiring (grouped by concern) ----------------------------------

    def _wire_model_signals(self):
        """AppModel → MainWindow (view refresh)."""
        self.model.model_updated.connect(self._on_model_updated)
        self.model.connection_updated.connect(self._on_connection_updated)

    def _wire_hardware_signals(self):
        """HardwareManager ↔ MainWindow ↔ widgets."""
        self.hardware.fps_ready.connect(self._on_fps_ready)
        self.hardware.positioners_registered.connect(self._on_positioners_registered)
        self.hardware.frame_ready.connect(self.camera_widget.update_frame)

        self.status_bar.reconnect_fps_requested.connect(self._on_reconnect_fps)
        self.status_bar.reconnect_camera_requested.connect(self.hardware.reconnect_camera)
        self.camera_widget.exposure_changed.connect(self.hardware.set_exposure)
        self.camera_widget.gain_changed.connect(self.hardware.set_gain)

    def _wire_dispatcher_signals(self):
        """MoveDispatcher ↔ MainWindow ↔ ControlPanel."""
        self.control_panel.move_requested.connect(self.dispatcher.on_move_requested)
        self.control_panel.xy_move_requested.connect(self.dispatcher.on_xy_move_requested)
        self.control_panel.batch_move_requested.connect(self.dispatcher.on_batch_move_requested)
        self.dispatcher.angles_updated.connect(self.control_panel.update_angles)
        self.dispatcher.invalid_position.connect(self.control_panel.flash_invalid_position)

    def _wire_widget_signals(self):
        """Widget ↔ AppModel direct connections and widget-to-widget connections."""
        self.grid2D.move_queued.connect(self.model.queue_move)
        self.camera_widget.move_queued.connect(self.model.queue_move)
        self.control_panel.selection_changed.connect(self.model.set_selected_positioner)
        self.grid2D.selection_changed.connect(self.model.set_selected_positioner)
        self.camera_widget.selection_changed.connect(self.model.set_selected_positioner)
        self.grid2D.swap_requested.connect(self.on_swap_views_requested)
        self.camera_widget.swap_requested.connect(self.on_swap_views_requested)
        self.control_panel.calibrate_requested.connect(self.camera_widget.start_calibration)
        self.camera_widget.calibration_completed.connect(self.control_panel.on_calibration_completed)
        self.control_panel.swap_solution_requested.connect(self.model.swap_solution)

    # -- Slots ---------------------------------------------------------------

    def _on_fps_ready(self, fps, loop):
        """Forward FPS reference to the move dispatcher."""
        self.dispatcher.set_fps(fps, loop)

    def _on_reconnect_fps(self):
        """Clear dispatcher's FPS reference, then rebuild the poller."""
        self.dispatcher.clear_fps()
        self.hardware.reconnect_fps()

    def _on_positioners_registered(self):
        """Notify UI controls of discovered positioner IDs."""
        self.control_panel.update_positioners(self.model.positioners.keys())
        self.grid2D.update_positioners(self.model.positioners.keys())

    def _on_connection_updated(self):
        self.status_bar.update_connections(self.model.fps_connected, self.model.camera_connected)

    def _on_model_updated(self):
        """Called when AppModel emits model_updated; re-renders all views."""
        self.status_bar.update_display(self.model.positioners)
        self.grid2D.update_display(self.model.positioners, self.model.selected_positioner_id)
        self.camera_widget.update_display(self.model.positioners, self.model.selected_positioner_id)
        self.control_panel.update_selected_positioner(self.model.selected_positioner_id)
        self.control_panel.update_queue_state(self.model.positioners)
        self._maybe_fill_control_panel_inputs()

    def _maybe_fill_control_panel_inputs(self):
        """Fill control panel inputs only on PID-switch or positioner settle.

        Avoids clobbering user input during a move or on every 5 Hz poll tick.
        Triggers when:
        - The selected positioner ID changes (operator switched PIDs).
        - The selected positioner transitions from MOVING → READY (move settled).
        """
        pid = self.model.selected_positioner_id
        pos = self.model.positioners.get(pid)
        current_state = pos.state if pos else None

        pid_changed = pid != self._prev_selected_pid
        settled = (
            self._prev_selected_state == PositionerState.MOVING
            and current_state == PositionerState.READY
        )

        if pid_changed or settled:
            self.control_panel.update_current_positioner_data(pos)

        self._prev_selected_pid = pid
        self._prev_selected_state = current_state

    # -- View swapping -------------------------------------------------------

    def on_swap_views_requested(self):
        view_main = self.current_main_view
        view_small = self.current_small_view

        idx_main = self.main_splitter.indexOf(view_main)
        idx_small = self.right_splitter.indexOf(view_small)

        # Use a dummy widget to hold the spot in right_splitter
        dummy = QWidget()
        self.right_splitter.replaceWidget(idx_small, dummy)

        # Now view_small is detached. Replace view_main with view_small
        self.main_splitter.replaceWidget(idx_main, view_small)

        # Now view_main is detached. Replace dummy with view_main
        self.right_splitter.replaceWidget(idx_small, view_main)

        # Clean up dummy widget
        dummy.deleteLater()

        # Update references
        self.current_main_view = view_small
        self.current_small_view = view_main

        self.current_main_view.swap_button.setVisible(False)
        self.current_small_view.swap_button.setVisible(True)

    # -- Mouse coordinates ---------------------------------------------------

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove:
            if obj in (self.grid2D, self.camera_widget):
                try:
                    phys_x, phys_y = obj.get_physical_click_coords(event)
                    self.mouse_coord_label.setText(f"X: {int(phys_x)}, Y: {int(phys_y)}")
                except Exception:
                    pass
        return super().eventFilter(obj, event)

    # -- Shutdown ------------------------------------------------------------

    def closeEvent(self, event):
        self.hardware.stop_camera()
        self.hardware.stop_fps()
        super().closeEvent(event)
