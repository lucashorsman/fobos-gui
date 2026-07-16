"""Owns the lifecycle of hardware worker threads (FPS poller + camera).

Handles construction, signal wiring, reconnection, and shutdown of worker
threads.  Does not own any widgets — only AppModel references are needed.
Positioner center assignments are loaded from ``positioner_centers.json``
instead of being hardcoded.
"""

from __future__ import annotations

import json
import os
from PySide6.QtCore import QObject, Signal, Slot, Qt

from core.app_model import AppModel
from workers.fps_manager import FPSManager
from workers.vimba_worker import VimbaWorker
from workers.stream_worker import StreamWorker

_CAMERA_BACKEND = os.environ.get("FOBOS_CAMERA", "vimba").lower()
_STREAM_HOST = os.environ.get("FOBOS_STREAM_HOST", "localhost")
_STREAM_PORT = int(os.environ.get("FOBOS_STREAM_PORT", "8765"))

# Path to positioner center configuration (project root)
_CENTERS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "positioner_centers.json")
)


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

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self._model = model
        self._poller: FPSManager | None = None
        self._camera_worker = None
        self._centers = _load_positioner_centers()

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
