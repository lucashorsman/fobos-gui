"""Background thread for running the metrology verification pass.

Captures a check frame (laser ON), turns the laser off, captures a reference
frame (laser OFF), restores the laser, then runs the collision-safe
``verify_fibers_global()`` algorithm to detect laser spots and compare them
against expected positions.

Threading model
---------------
``VerifyWorker`` is a ``QThread`` that runs on a short-lived background thread.
It communicates with the camera by temporarily connecting to
``frame_ready(ndarray)`` via a ``Qt.QueuedConnection`` and waiting on a
``threading.Event``.  Laser control goes through ``StreamWorker`` control
commands (``laser_off``, ``laser_on``, ``status``).

When using the Vimba backend (no laser control channel), the worker falls
back to a dialog-based flow where the operator manually toggles the laser.
"""

from __future__ import annotations

import logging
import threading
import time

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal, Slot, Qt

from helpers.constants import VERIFY_ROI_SIZE, VERIFY_TOLERANCE_PX, VERIFY_THRESH
from helpers.metrology import verify_fibers_global


# Settle time (seconds) after laser on/off before capturing a frame,
# to allow the camera exposure to stabilise.
_LASER_SETTLE_S = 0.3

# Timeout (seconds) for waiting for a camera frame.
_FRAME_TIMEOUT_S = 5.0

# Timeout (seconds) for waiting for laser status confirmation.
_STATUS_TIMEOUT_S = 3.0


class VerifyWorker(QThread):
    """One-shot verification thread.

    Signals
    -------
    verify_complete(dict, list)
        Emitted on success with (results, unmatched_blobs).
    verify_failed(str)
        Emitted on error with a human-readable message.
    """

    verify_complete = Signal(object, object)   # (results, unmatched_blobs)
    verify_failed = Signal(str)            # error message
    manual_laser_toggle_requested = Signal(bool)  # True to turn ON, False to turn OFF

    def __init__(
        self,
        expected_positions: dict,
        camera_worker,
        has_laser_control: bool = False,
        parent=None,
    ):
        """
        Parameters
        ----------
        expected_positions : dict
            ``{pid: (expected_pixel_x, expected_pixel_y)}`` in top-left
            image coordinates.
        camera_worker : StreamWorker | VimbaWorker
            The currently active camera worker.  Used to grab frames via
            its ``frame_ready`` signal and (for StreamWorker) to issue
            laser on/off commands.
        has_laser_control : bool
            True when the camera backend supports programmatic laser
            control (i.e. StreamWorker).  When False, the worker expects
            that the operator has already been prompted via a dialog
            (handled by HardwareManager before starting this worker).
        """
        super().__init__(parent)
        self._expected = expected_positions
        self._camera_worker = camera_worker
        self._has_laser_control = has_laser_control

        # Frame capture synchronisation
        self._frame_event = threading.Event()
        self._captured_frame: np.ndarray | None = None

        # Laser status synchronisation (stream backend only)
        self._status_event = threading.Event()
        self._last_status: dict = {}

        # Manual laser toggle synchronisation (vimba backend only)
        self._manual_event = threading.Event()

    def confirm_manual_toggle(self):
        """Unblock the worker thread after the operator confirms the laser toggle."""
        self._manual_event.set()

    # -- Frame capture helpers -----------------------------------------------

    @Slot(object)
    def _on_frame_ready(self, frame):
        """Slot connected temporarily to camera_worker.frame_ready."""
        if frame is None:
            return

        if not isinstance(frame, np.ndarray):
            logging.error(
                "verifyWorker: frame_ready delivered non-ndarray frame (type=%s); "
                "dropping, capture will time out",
                type(frame).__name__,
            )
            return

        if frame.ndim == 3 and frame.shape[2] == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif frame.ndim == 3 and frame.shape[2] == 1:
            gray = frame.squeeze(axis=2)
        elif frame.ndim == 2:
            gray = frame
        else:
            logging.error(
                "verifyWorker: frame_ready delivered unexpected shape %s; "
                "dropping, capture will time out",
                frame.shape,
            )
            return

        self._captured_frame = gray.astype(np.float32)
        self._frame_event.set()

    def _capture_one_frame(self) -> np.ndarray | None:
        """Block until the next frame arrives from the camera worker."""
        self._frame_event.clear()
        self._captured_frame = None

        # Connect to frame_ready (queued so it arrives on *this* thread
        # when the event loop pumps — but we're not running an event loop
        # here, so use DirectConnection instead and protect with the Event).
        self._camera_worker.frame_ready.connect(
            self._on_frame_ready, Qt.DirectConnection
        )
        try:
            if not self._frame_event.wait(timeout=_FRAME_TIMEOUT_S):
                return None
            return self._captured_frame
        finally:
            try:
                self._camera_worker.frame_ready.disconnect(self._on_frame_ready)
            except RuntimeError:
                pass  # already disconnected

    # -- Laser control helpers (stream backend) ------------------------------

    @Slot(dict)
    def _on_laser_status(self, status: dict):
        """Slot connected temporarily to StreamWorker.laser_status_received."""
        self._last_status = status
        self._status_event.set()

    def _wait_laser_state(self, want_on: bool) -> bool:
        """Poll /status until the laser state matches *want_on*, or timeout."""
        if not self._has_laser_control:
            return True  # no way to confirm — assume it's fine

        deadline = time.monotonic() + _STATUS_TIMEOUT_S
        while time.monotonic() < deadline:
            self._status_event.clear()
            self._camera_worker.request_status()
            if self._status_event.wait(timeout=1.0):
                if self._last_status.get("on") == want_on:
                    return True
            time.sleep(0.1)
        return False

    # -- Main thread body ----------------------------------------------------

    def run(self):
        if not self._expected:
            self.verify_failed.emit("No expected positions to verify.")
            return

        try:
            # Connect laser status listener (stream backend only)
            if self._has_laser_control:
                self._camera_worker.laser_status_received.connect(
                    self._on_laser_status, Qt.DirectConnection
                )

            # Step 1: Capture CHECK frame (laser is already ON)
            print("VerifyWorker: capturing check frame (laser ON)...")
            check_frame = self._capture_one_frame()
            if check_frame is None:
                self.verify_failed.emit(
                    "Timed out waiting for camera frame (laser ON check)."
                )
                return

            # Step 2: Turn laser OFF
            if self._has_laser_control:
                print("VerifyWorker: sending laser_off...")
                self._camera_worker.laser_off()
                time.sleep(_LASER_SETTLE_S)
                if not self._wait_laser_state(want_on=False):
                    print("VerifyWorker: WARNING — laser status did not "
                          "confirm OFF within timeout, proceeding anyway")
            else:
                self._manual_event.clear()
                self.manual_laser_toggle_requested.emit(False)
                self._manual_event.wait()

            # Step 3: Capture REFERENCE frame (laser OFF)
            print("VerifyWorker: capturing reference frame (laser OFF)...")
            # Allow an extra settle after laser off for the camera to adjust
            time.sleep(_LASER_SETTLE_S)
            ref_frame = self._capture_one_frame()
            if ref_frame is None:
                # Try to restore laser before failing
                if self._has_laser_control:
                    try:
                        self._camera_worker.laser_on()
                    except Exception:
                        pass
                else:
                    self._manual_event.clear()
                    self.manual_laser_toggle_requested.emit(True)
                    self._manual_event.wait()
                    
                self.verify_failed.emit(
                    "Timed out waiting for camera frame (laser OFF reference)."
                )
                return

            # Step 4: Restore laser ON
            if self._has_laser_control:
                print("VerifyWorker: sending laser_on...")
                self._camera_worker.laser_on()
            else:
                self._manual_event.clear()
                self.manual_laser_toggle_requested.emit(True)
                self._manual_event.wait()
                time.sleep(_LASER_SETTLE_S)

            # Step 5: Run detection
            print(f"VerifyWorker: running verify_fibers_global on "
                  f"{len(self._expected)} position(s)...")
            results, unmatched = verify_fibers_global(
                ref_frame,
                check_frame,
                self._expected,
                roi_size=VERIFY_ROI_SIZE,
                thresh=VERIFY_THRESH,
                tolerance_px=VERIFY_TOLERANCE_PX,
            )

            # Log summary
            n_pass = sum(1 for r in results.values() if r["pass"])
            n_found = sum(1 for r in results.values() if r["found"])
            print(f"VerifyWorker: {n_found}/{len(results)} found, "
                  f"{n_pass}/{len(results)} passed, "
                  f"{len(unmatched)} unmatched blobs")

            self.verify_complete.emit(results, unmatched)

        except Exception as exc:
            # Attempt laser restore on unexpected failure
            if self._has_laser_control:
                try:
                    self._camera_worker.laser_on()
                except Exception:
                    pass
            self.verify_failed.emit(f"Verification error: {exc}")

        finally:
            # Disconnect laser status listener
            if self._has_laser_control:
                try:
                    self._camera_worker.laser_status_received.disconnect(
                        self._on_laser_status
                    )
                except RuntimeError:
                    pass
