"""Owns the lifecycle of hardware worker threads (FPS poller + camera).

Handles construction, signal wiring, reconnection, and shutdown of worker
threads.  Does not own any widgets — only AppModel references are needed.
Positioner center assignments are loaded from ``positioner_centers.json``
instead of being hardcoded.  Also initialises the laser mapping interpolator
for the Verify feature.
"""

from __future__ import annotations

import json
import os
from PySide6.QtCore import QObject, Signal, Slot, Qt

from core.app_model import AppModel
from workers.fps_manager import FPSManager
from workers.vimba_worker import VimbaWorker
from workers.stream_worker import StreamWorker
from workers.verify_worker import VerifyWorker
from helpers.metrology import LaserMappingInterpolator
from helpers.projection import PositionerProjection
from helpers.calibration_io import load_calibration

_CAMERA_BACKEND = os.environ.get("FOBOS_CAMERA", "vimba").lower()
_STREAM_HOST = os.environ.get("FOBOS_STREAM_HOST", "localhost")
_STREAM_PORT = int(os.environ.get("FOBOS_STREAM_PORT", "8765"))

# Path to positioner center configuration (project root)
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
_CENTERS_PATH = os.path.join(_PROJECT_ROOT, "config", "positioner_centers.json")
_LASER_MAPPING_PATH = os.path.join(_PROJECT_ROOT, "config", "laser_mapping.json")
_CALIBRATION_PATH = os.path.join(_PROJECT_ROOT, "config", "calibration.json")


def _load_positioner_centers(path: str = _CENTERS_PATH) -> dict[int, tuple[float, float]]:
    """Load PID → (cx, cy) mapping from the JSON config file."""
    try:
        with open(path, "r") as f:
            raw = json.load(f)
        return {int(pid): tuple(center) for pid, center in raw.items()}
    except FileNotFoundError:
        print(f"Warning: {path} not found — using fallback centers for all positioners.")
        return {}
    except Exception as e:
        print(f"Warning: failed to load positioner centers: {e}")
        return {}


class HardwareManager(QObject):
    """Manages FPS and camera worker lifecycles.

    Signals are forwarded to MainWindow / MoveDispatcher so that this class
    remains decoupled from UI widgets.
    """

    # Forwarded to MainWindow / MoveDispatcher
    fps_ready = Signal(object, object)      # (fps, loop)
    positioners_registered = Signal()        # after all PIDs registered in AppModel
    frame_ready = Signal(object)             # camera frame (ndarray)
    error = Signal(str)                      # any hardware error message
    verify_ready = Signal(bool)              # True when interpolator is loaded
    manual_laser_toggle_requested = Signal(bool) # Forwarded from VerifyWorker

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self._model = model
        self._poller: FPSManager | None = None
        self._camera_worker = None
        self._verify_worker: VerifyWorker | None = None
        self._centers = _load_positioner_centers()

        # Initialise the laser mapping interpolator for the Verify feature.
        self._interpolator = self._init_interpolator()

    # -- FPS lifecycle -------------------------------------------------------

    def start_fps(self):
        """Construct and start the FPS poller thread."""
        self._poller = FPSManager()
        self._poller.ready.connect(self._on_fps_ready)
        self._poller.positions_updated.connect(self._model.update_positions)
        self._poller.error.connect(self._on_fps_error)
        self._poller.connection_status.connect(self._model.set_fps_connected)
        self._poller.start()

    def reconnect_fps(self):
        """Tear down and rebuild the FPS poller."""
        if self._poller:
            self._poller.ready.disconnect()
            self._poller.positions_updated.disconnect()
            self._poller.error.disconnect()
            self._poller.connection_status.disconnect()
            self._poller.stop()
            self._poller.deleteLater()

        self._model.set_fps_connected(False)
        self.start_fps()

    def stop_fps(self):
        """Stop the FPS poller thread."""
        if self._poller:
            self._poller.stop()

    # -- Camera lifecycle ----------------------------------------------------

    def start_camera(self):
        """Construct and start the camera worker thread."""
        self._camera_worker = self._make_camera_worker()
        self._connect_camera_worker()
        self._camera_worker.start()

    def reconnect_camera(self):
        """Tear down and rebuild the camera worker."""
        if self._camera_worker:
            self._camera_worker.frame_ready.disconnect()
            self._camera_worker.error.disconnect()
            self._camera_worker.connection_status.disconnect()
            self._camera_worker.stop()
            self._camera_worker.deleteLater()

        self._model.set_camera_connected(False)
        self.start_camera()

    def stop_camera(self):
        """Stop the camera worker thread."""
        if self._camera_worker:
            self._camera_worker.stop()

    # -- Camera settings forwarding ------------------------------------------

    @Slot(int)
    def set_exposure(self, val: int):
        """Forward exposure changes to whichever camera worker is currently live."""
        if self._camera_worker:
            self._camera_worker.set_exposure(val)

    @Slot(float)
    def set_gain(self, val: float):
        """Forward gain changes to whichever camera worker is currently live."""
        if self._camera_worker:
            self._camera_worker.set_gain(val)

    # -- Internal ------------------------------------------------------------

    def _make_camera_worker(self):
        """Construct the camera worker selected by FOBOS_CAMERA."""
        if _CAMERA_BACKEND == "stream":
            print(f"Camera backend: StreamWorker ({_STREAM_HOST}:{_STREAM_PORT})")
            return StreamWorker(host=_STREAM_HOST, port=_STREAM_PORT, parent=self)
        print("Camera backend: VimbaWorker")
        return VimbaWorker(self)

    def _connect_camera_worker(self):
        """Wire the camera worker signals (identical for both backends)."""
        self._camera_worker.frame_ready.connect(self._forward_frame, Qt.QueuedConnection)
        self._camera_worker.error.connect(self._on_camera_error)
        self._camera_worker.connection_status.connect(self._model.set_camera_connected)

    @Slot(object)
    def _forward_frame(self, frame):
        """Re-emit camera frames so MainWindow can route them to CameraWidget
        without holding a direct reference to the camera worker."""
        self.frame_ready.emit(frame)

    def _on_fps_ready(self, fps, loop):
        """Register all discovered positioners and forward the ready signal."""
        print(fps.positioners.items())
        is_mock = os.environ.get("FOBOS_MOCK") == "1"
        fallback_x = 100
        for pid, pos in fps.positioners.items():
            if pid in self._centers:
                center = self._centers[pid]
            elif is_mock:
                center = (fallback_x, 500.0)
                fallback_x += 100
            else:
                print(f"WARNING: PID {pid} not found in positioner_centers.json — using fallback center.")
                center = (fallback_x, 500.0)
                fallback_x += 100
            self._model.register_positioner(pid, center=center)

        print(f"FPS initialized, {len(self._model.positioners)} positioners registered")
        print(f"pids in use: {self._model.positioners.keys()}")

        self.fps_ready.emit(fps, loop)
        self.positioners_registered.emit()

    def _on_fps_error(self, err_msg=""):
        print(f"Error initializing FPS: {err_msg}")
        self.error.emit(f"FPS: {err_msg}")

    def _on_camera_error(self, err_msg=""):
        print(f"Camera error ({_CAMERA_BACKEND}): {err_msg}")
        self.error.emit(f"Camera: {err_msg}")

    def _init_interpolator(self) -> LaserMappingInterpolator | None:
        """Load the laser mapping and camera calibration for the Verify feature."""
        if not os.path.isfile(_LASER_MAPPING_PATH):
            print("HardwareManager: laser_mapping.json not found — Verify disabled")
            return None

        # Set up projection from the calibration file
        projection = PositionerProjection()
        saved_cal = load_calibration(_CALIBRATION_PATH)
        if saved_cal:
            phys_pts, cam_pts = saved_cal
            try:
                projection.calibrate(phys_pts, cam_pts)
            except Exception as e:
                print(f"HardwareManager: failed to apply calibration for verify: {e}")
        else:
            print("HardwareManager: no calibration found — verify kinematic fallback unavailable")

        # Build the interpolator
        interpolator = LaserMappingInterpolator(
            _LASER_MAPPING_PATH,
            projection=projection,
            phys_centers={pid: tuple(c) for pid, c in self._centers.items()},
        )
        if interpolator.is_loaded:
            return interpolator
        return None

    @property
    def has_interpolator(self) -> bool:
        return self._interpolator is not None and self._interpolator.is_loaded

    @property
    def has_laser_control(self) -> bool:
        return _CAMERA_BACKEND == "stream"

    # -- Verify feature ------------------------------------------------------

    def run_verify(self):
        """Build expected positions and start a VerifyWorker thread.

        Expects that the caller (MainWindow) has already set
        ``model.verify_in_progress = True`` and, for VimbaWorker,
        has shown the manual laser dialog.
        """
        if self._verify_worker is not None and self._verify_worker.isRunning():
            print("HardwareManager: verify already in progress")
            return

        if self._interpolator is None:
            self._model.set_verify_in_progress(False)
            self.error.emit("Verify: laser_mapping.json not loaded")
            return

        if self._camera_worker is None:
            self._model.set_verify_in_progress(False)
            self.error.emit("Verify: camera not connected")
            return

        # Build expected positions from current positioner angles
        expected = {}
        for pid, p in self._model.positioners.items():
            pt = self._interpolator.get_expected_pixel(pid, p.alpha, p.beta)
            if pt is not None:
                expected[pid] = pt
            else:
                print(f"HardwareManager: no expected pixel for PID {pid} "
                      f"at α={p.alpha:.1f}°, β={p.beta:.1f}° — skipping")

        if not expected:
            self._model.set_verify_in_progress(False)
            self.error.emit("Verify: could not compute expected positions for any positioner")
            return

        print(f"HardwareManager: starting verify for {len(expected)} positioner(s)")

        self._verify_worker = VerifyWorker(
            expected_positions=expected,
            camera_worker=self._camera_worker,
            has_laser_control=self.has_laser_control,
            parent=self,
        )
        self._verify_worker.verify_complete.connect(self._on_verify_complete)
        self._verify_worker.verify_failed.connect(self._on_verify_failed)
        self._verify_worker.finished.connect(self._on_verify_thread_finished)
        self._verify_worker.manual_laser_toggle_requested.connect(self.manual_laser_toggle_requested.emit)
        self._verify_worker.start()

    def confirm_manual_laser_toggle(self):
        """Called by MainWindow after the operator confirms the laser toggle."""
        if self._verify_worker is not None:
            self._verify_worker.confirm_manual_toggle()

    @Slot(dict, list)
    def _on_verify_complete(self, results: dict, unmatched: list):
        self._model.set_verify_results(results, unmatched)
        self._model.set_verify_in_progress(False)

    @Slot(str)
    def _on_verify_failed(self, err_msg: str):
        print(f"VerifyWorker failed: {err_msg}")
        self.error.emit(f"Verify: {err_msg}")
        self._model.set_verify_in_progress(False)

    @Slot()
    def _on_verify_thread_finished(self):
        if self._verify_worker is not None:
            self._verify_worker.deleteLater()
            self._verify_worker = None
