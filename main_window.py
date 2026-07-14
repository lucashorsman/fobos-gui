#assembles all widgets and components for the main window
from widgets.grid2d import Grid2d
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel
from PySide6.QtGui import QFont
from app_model import AppModel
from PySide6.QtCore import Qt, QEvent, Signal, Slot
from workers.fps_manager import FPSManager
from workers.vimba_worker import VimbaWorker
from workers.stream_worker import StreamWorker
from widgets.camera_widget import CameraWidget
from widgets.status_bar import StatusBar
from widgets.control_panel import ControlPanel
from helpers.constants import PositionerState, normalize_for_positioner, SHORT_ARM_LENGTH, LONG_ARM_LENGTH
from helpers.annulus import solve_inverse_kinematics
import asyncio
import os

# Camera backend selection:
#   FOBOS_CAMERA=vimba   (default) — use VimbaWorker via vmbpy
#   FOBOS_CAMERA=stream  — use StreamWorker via RPi5 WebSocket bridge
#
# When using the stream backend, also set:
#   FOBOS_STREAM_HOST  (default: localhost)
#   FOBOS_STREAM_PORT  (default: 8765)
_CAMERA_BACKEND = os.environ.get("FOBOS_CAMERA", "vimba").lower()
_STREAM_HOST = os.environ.get("FOBOS_STREAM_HOST", "localhost")
_STREAM_PORT = int(os.environ.get("FOBOS_STREAM_PORT", "8765"))

class MainWindow(QMainWindow):
    # Private signals used to dispatch move results back to the main thread
    # from the FPSManager asyncio loop. These must be class-level Signal
    # declarations so PySide6 registers them on the QObject metaclass.
    # The auto-connection (default) becomes a QueuedConnection when the
    # signal is emitted from a non-main thread, which is exactly what
    # _do_batch_move does — it runs on the FPSManager's asyncio loop thread.
    _move_batch_succeeded = Signal(list)  # list of positioner IDs that completed
    _move_batch_failed = Signal(list)     # list of positioner IDs that errored

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fobos GUI")
        self.setGeometry(100, 100, 1800, 1000)
       
        # Instantiate UI components
        self.status_bar = StatusBar()
        self.control_panel = ControlPanel()
        self.grid2D = Grid2d()
        self.camera_widget = CameraWidget()

        style_path = os.path.join(os.path.dirname(__file__), "style.qss")
        if os.path.exists(style_path):
            with open(style_path, "r") as f:
                self.setStyleSheet(f.read())

        # create the right-side vertical splitter for Status and Control
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(self.status_bar)
        self.right_splitter.addWidget(self.camera_widget)
        self.right_splitter.addWidget(self.control_panel)
        
        # create the main horizontal splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.grid2D)
        self.main_splitter.addWidget(self.right_splitter)
        
        # Set custom proportions
        self.main_splitter.setSizes([700, 300]) 
        self.right_splitter.setSizes([205, 620, 200])
        
        # Set the main splitter as the central widget
        self.setCentralWidget(self.main_splitter)
        
        self.current_main_view = self.grid2D
        self.current_small_view = self.camera_widget
        
        self.current_main_view.swap_button.setVisible(False)
        self.current_small_view.swap_button.setVisible(True)

        self.mouse_coord_label = QLabel("X: --, Y: --")
        self.mouse_coord_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.statusBar().addPermanentWidget(self.mouse_coord_label)

        self.grid2D.installEventFilter(self)
        self.camera_widget.installEventFilter(self)

        self.model = AppModel()
        
        # Wire up UI to model and actions
        self.model.model_updated.connect(self._on_model_updated)
        self.model.connection_updated.connect(self._on_connection_updated)
        self.control_panel.move_requested.connect(self.on_move_requested)
        self.control_panel.xy_move_requested.connect(self.on_xy_move_requested)
        self.grid2D.move_queued.connect(self.model.queue_move)
        self.camera_widget.move_queued.connect(self.model.queue_move)
        self.control_panel.batch_move_requested.connect(self.on_batch_move_requested)
        self.control_panel.selection_changed.connect(self.model.set_selected_positioner)
        self.grid2D.selection_changed.connect(self.model.set_selected_positioner)
        self.camera_widget.selection_changed.connect(self.model.set_selected_positioner)
        self.grid2D.swap_requested.connect(self.on_swap_views_requested)
        self.camera_widget.swap_requested.connect(self.on_swap_views_requested)
        self.control_panel.calibrate_requested.connect(self.camera_widget.start_calibration)
        self.camera_widget.calibration_completed.connect(self.control_panel.on_calibration_completed)
        self.control_panel.swap_solution_requested.connect(self.model.swap_solution)
        self.status_bar.reconnect_fps_requested.connect(self.reconnect_fps)
        self.status_bar.reconnect_camera_requested.connect(self.reconnect_camera)

        # Camera settings are routed through stable MainWindow intermediaries so
        # that the camera_widget to camera_worker connection is never direct.
        # This avoids stale connections when the worker is replaced on reconnect.
        self.camera_widget.exposure_changed.connect(self._on_exposure_changed)
        self.camera_widget.gain_changed.connect(self._on_gain_changed)

        # Connect thread-safe result signals to main-thread slots.
        # Because _do_batch_move runs on the FPSManager asyncio loop (a non-main
        # thread), emitting these signals will be auto-queued to the main thread,
        # ensuring AppModel is only mutated from the Qt event loop.
        self._move_batch_succeeded.connect(self._on_batch_move_success)
        self._move_batch_failed.connect(self._on_batch_move_failure)
        
        self.poller = None
        self.camera_worker = None
        self._fps = None
        self._fps_loop = None
        
        # Start the poller which will initialize the FPS instance
        self.poller = FPSManager()
        self.poller.ready.connect(self.on_fps_ready)
        self.poller.positions_updated.connect(self.model.update_positions)
        self.poller.error.connect(self.on_fps_error)
        self.poller.connection_status.connect(self.model.set_fps_connected)
        self.poller.start()

        self.camera_worker = self._make_camera_worker()
        self._connect_camera_worker()
        self.camera_worker.start()

    def reconnect_fps(self):
        if self.poller:
            self.poller.stop()
            self.poller.deleteLater()
            
        self.model.set_fps_connected(False)
        self._fps = None
        self._fps_loop = None
        
        self.poller = FPSManager()
        self.poller.ready.connect(self.on_fps_ready)
        self.poller.positions_updated.connect(self.model.update_positions)
        self.poller.error.connect(self.on_fps_error)
        self.poller.connection_status.connect(self.model.set_fps_connected)
        self.poller.start()

    def reconnect_camera(self):
        if self.camera_worker:
            self.camera_worker.stop()
            self.camera_worker.deleteLater()

        self.model.set_camera_connected(False)
        self.camera_worker = self._make_camera_worker()
        self._connect_camera_worker()
        self.camera_worker.start()

    def _make_camera_worker(self):
        """Construct the camera worker selected by FOBOS_CAMERA."""
        if _CAMERA_BACKEND == "stream":
            print(f"Camera backend: StreamWorker ({_STREAM_HOST}:{_STREAM_PORT})")
            return StreamWorker(host=_STREAM_HOST, port=_STREAM_PORT, parent=self)
        print("Camera backend: VimbaWorker")
        return VimbaWorker(self)

    def _connect_camera_worker(self):
        """Wire the camera worker signals/slots (identical for both backends).

        Only worker to UI/model connections are made here. The UI to worker direction
        (exposure, gain) is routed through permanent MainWindow intermediary slots
        so there are no stale connections to clean up when the worker is replaced on reconnect.
        """
        self.camera_worker.frame_ready.connect(self.camera_widget.update_frame, Qt.QueuedConnection)
        self.camera_worker.error.connect(self.on_camera_error)
        self.camera_worker.connection_status.connect(self.model.set_camera_connected)

    # Camera settings intermediaries
    @Slot(int)
    def _on_exposure_changed(self, val: int):
        """Forward exposure changes to whichever camera worker is currently live."""
        if self.camera_worker:
            self.camera_worker.set_exposure(val)

    @Slot(float)
    def _on_gain_changed(self, val: float):
        """Forward gain changes to whichever camera worker is currently live."""
        if self.camera_worker:
            self.camera_worker.set_gain(val)

    def _on_connection_updated(self):
        self.status_bar.update_connections(self.model.fps_connected, self.model.camera_connected)

    def _on_model_updated(self):
        """Called when AppModel emits model_updated; re-renders all views."""
        self.status_bar.update_display(self.model.positioners)
        self.grid2D.update_display(self.model.positioners, self.model.selected_positioner_id)
        self.camera_widget.update_display(self.model.positioners, self.model.selected_positioner_id)
        self.control_panel.update_selected_positioner(self.model.selected_positioner_id)
        self.control_panel.update_queue_state(self.model.positioners)

    def _is_any_moving(self) -> bool:
        return any(pos.get("state") == PositionerState.MOVING for pos in self.model.positioners.values())

    def on_batch_move_requested(self):
        """Send all queued targets to hardware in a single CAN bus transaction."""
        if not self._fps or not self._fps_loop:
            return
        
        if self._is_any_moving():
            print("Move already in progress, ignoring batch move request.")
            return

        queued_moves = self.model.get_queued_moves()
        if not queued_moves:
            return

        # Mark all queued positioners as moving before dispatching.
        for pid in queued_moves:
            self.model.update_positioner_state(pid, PositionerState.MOVING)
        self.model.clear_queued_moves()

        asyncio.run_coroutine_threadsafe(
            self._do_batch_move(queued_moves), self._fps_loop
        )

    def on_move_requested(self, pid: int, alpha: float, beta: float):
        """Single-positioner move from the manual entry panel.

        Routes through the same batch coroutine as multi-positioner moves.
        NOTE: Concurrent rapid-fire calls are not guarded by a lock. An
        asyncio.Lock on _do_batch_move could prevent a second move from being
        submitted while the first is in-flight, but this path is a backup tool
        for manual correction — high-frequency use is not expected.
        """
        if not self._fps or not self._fps_loop:
            return
        
        if self._is_any_moving():
            print("Move already in progress, ignoring single move request.")
            return
        self.model.update_positioner_state(pid, PositionerState.MOVING)
        asyncio.run_coroutine_threadsafe(
            self._do_batch_move({pid: (alpha, beta)}), self._fps_loop
        )

    def on_xy_move_requested(self, pid: int, abs_x: float, abs_y: float):
        """Single-positioner move from the manual XY entry panel.

        Converts absolute physical coordinates to a positioner-relative offset,
        runs IK, then dispatches immediately via the same path as angle mode.
        IK and center lookup live here (not in ControlPanel) because this is
        the only layer that has access to both the model and the dispatch loop.
        """
        if pid not in self.model.positioners:
            return
        cx, cy = self.model.positioners[pid]["center"]
        rel_x = abs_x - cx
        rel_y = abs_y - cy
        # Axis inversion matches the kinematic convention in Grid2d / CameraWidget.
        solutions = solve_inverse_kinematics(-rel_x, -rel_y, SHORT_ARM_LENGTH, LONG_ARM_LENGTH)
        if solutions:
            self.on_move_requested(pid, solutions[0][0], solutions[0][1])

    async def _do_batch_move(self, targets: dict):
        """Execute a multi-positioner goto on the FPSManager asyncio loop.

        Args:
            targets: {pid: (alpha_deg, beta_deg)} — raw angles (not yet normalized).

        Normalization into the hardware range [-10°, 370°] is done here, at the
        single hardware-dispatch boundary, so widgets can store raw IK output.
        Results are dispatched back to the main thread via the
        _move_batch_succeeded / _move_batch_failed signals.
        """
        normalized = {
            pid: (normalize_for_positioner(a), normalize_for_positioner(b))
            for pid, (a, b) in targets.items()
        }
        try:
            await self._fps.goto(normalized)
            self._move_batch_succeeded.emit(list(normalized.keys()))
        except Exception as e:
            print(f"Batch move error: {e}")
            self._move_batch_failed.emit(list(normalized.keys()))

    @Slot(list)
    def _on_batch_move_success(self, pids: list):
        """Called on the main thread after a successful batch goto."""
        for pid in pids:
            self.model.update_positioner_state(pid, PositionerState.READY)

    @Slot(list)
    def _on_batch_move_failure(self, pids: list):
        """Called on the main thread after a failed batch goto."""
        for pid in pids:
            self.model.update_positioner_state(pid, PositionerState.ERROR)

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

    def on_fps_ready(self, fps, loop):
        self._fps = fps
        self._fps_loop = loop
        # Discover all connected positioners
        print(fps.positioners.items())
        x = 100
        for pid, pos in fps.positioners.items():
            
            # center = getattr(pos, 'center', (0.0, 0.0))
            if pid == 1403:
                center = (-36.83078, -130.32223)
            elif pid == 967:
                center = (0.50013, 499.49927)
            else:
                center = (x, 500.0)
            x+=100
            self.model.register_positioner(pid, center=center)
            
        # Update UI controls with discovered positioner IDs
        self.control_panel.update_positioners(self.model.positioners.keys())
        self.grid2D.update_positioners(self.model.positioners.keys())
            
        print(f"FPS initialized, {len(self.model.positioners)} positioners registered")
        print(f"pids in use: {self.model.positioners.keys()}")

    def on_fps_error(self, err_msg=""):
        print(f"Error initializing FPS: {err_msg}")

    def on_camera_error(self, err_msg=""):
        print(f"Camera error ({_CAMERA_BACKEND}): {err_msg}")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove:
            if obj in (self.grid2D, self.camera_widget):
                try:
                    phys_x, phys_y = obj.get_physical_click_coords(event)
                    self.mouse_coord_label.setText(f"X: {int(phys_x)}, Y: {int(phys_y)}")
                except Exception:
                    pass
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        if self.camera_worker:
            self.camera_worker.stop()
        if self.poller:
            self.poller.stop()
        super().closeEvent(event)
