"""Background thread for streaming frames from the RPi5 camera bridge.

Connects to the bridge's /video and /control WebSocket endpoints and re-emits
frames through the same Qt signal surface as VimbaWorker. Signal names and
types are intentionally identical so MainWindow can swap between the two
workers without any wiring changes.

Environment variables (read at startup in main_window.py):
    FOBOS_CAMERA=stream         select this worker (default: vimba)
    FOBOS_STREAM_HOST           bridge hostname or IP (default: raspberrypi.local)
    FOBOS_STREAM_PORT           bridge WebSocket port  (default: 8765)
"""

from __future__ import annotations

import asyncio
import json
import logging

import cv2
import numpy as np
import websockets
from PySide6.QtCore import QThread, Signal, Slot

logger = logging.getLogger("stream_worker")


class StreamWorker(QThread):
    # Signal names match VimbaWorker exactly so MainWindow wiring is unchanged.
    frame_ready = Signal(object)        # decoded BGR ndarray
    error = Signal(str)
    connection_status = Signal(bool)

    # Extra signal specific to the RPi bridge control channel.
    laser_status_received = Signal(dict)

    def __init__(
        self,
        host: str = "raspberrypi.local",
        port: int = 8765,
        reconnect_delay: float = 2.0,
        parent=None,
    ):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay

        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._shutdown = False  # True during deliberate stop(); suppresses spurious signals
        self._control_ws = None

    # ---- QThread entry point ------------------------------------------------

    def run(self):
        self._running = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except RuntimeError as exc:
            # loop.stop() called while run_until_complete was in flight — this is
            # the expected path when stop() fires during a sleep/await between
            # reconnect attempts. Only warn if this was NOT a deliberate shutdown.
            if not self._shutdown:
                logger.warning("StreamWorker event loop stopped unexpectedly: %s", exc)
        finally:
            self._loop.close()

    def stop(self):
        self._shutdown = True
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.wait()

    # ---- async internals ----------------------------------------------------

    async def _main(self):
        await asyncio.gather(
            self._video_loop(),
            self._control_loop(),
        )

    async def _video_loop(self):
        uri = f"ws://{self.host}:{self.port}/video"
        self.connection_status.emit(False)  # initialise GUI state before first attempt
        _error_logged = False
        while self._running:
            try:
                async with websockets.connect(uri, max_size=None) as ws:
                    logger.info("Connected to video stream at %s", uri)
                    self.connection_status.emit(True)
                    _error_logged = False  # reset so the next drop is reported
                    async for message in ws:
                        frame = cv2.imdecode(
                            np.frombuffer(message, dtype=np.uint8), cv2.IMREAD_COLOR
                        )
                        if frame is not None:
                            self.frame_ready.emit(frame)
            except Exception as exc:
                if not self._shutdown and not _error_logged:
                    # Demoted to debug so the warning doesn't double-print alongside
                    # on_camera_error; error() is the single user-facing notification.
                    logger.debug("Video connection lost/failed: %s", exc)
                    self.connection_status.emit(False)
                    self.error.emit(str(exc))
                    _error_logged = True
            if self._running:
                await asyncio.sleep(self.reconnect_delay)


    async def _control_loop(self):
        uri = f"ws://{self.host}:{self.port}/control"
        _error_logged = False
        while self._running:
            try:
                async with websockets.connect(uri) as ws:
                    logger.info("Connected to control channel at %s", uri)
                    self._control_ws = ws
                    _error_logged = False  # reset so the next drop is reported
                    async for message in ws:
                        try:
                            reply = json.loads(message)
                        except json.JSONDecodeError:
                            continue
                        if "status" in reply:
                            self.laser_status_received.emit(reply["status"])
            except Exception as exc:
                if not self._shutdown and not _error_logged:
                    # Control channel failure is secondary — the video loop already
                    # notified the user. Log at debug level only; don't emit error().
                    logger.debug("Control connection lost/failed: %s", exc)
                    _error_logged = True
            finally:
                self._control_ws = None
            if self._running:
                await asyncio.sleep(self.reconnect_delay)

    def _send_control_command(self, payload: dict):
        """Thread-safe: schedules a send onto the worker's own event loop."""
        if self._loop is None or self._loop.is_closed() or self._control_ws is None:
            logger.warning("Control channel not connected, dropping command: %s", payload)
            return
        asyncio.run_coroutine_threadsafe(
            self._control_ws.send(json.dumps(payload)), self._loop
        )

    # ---- camera-compatible stubs (satisfy VimbaWorker slot wiring) ----------

    @Slot(int)
    def set_exposure(self, exposure_us: int):
        self._send_control_command({"cmd": "set_exposure", "value": exposure_us})

    @Slot(float)
    def set_gain(self, gain_db: float):
        self._send_control_command({"cmd": "set_gain", "value": gain_db})

    # ---- laser control slots ------------------------------------------------

    @Slot(float)
    def laser_on(self, intensity: float = 1.0):
        self._send_control_command({"cmd": "laser_on", "intensity": intensity})

    @Slot()
    def laser_off(self):
        self._send_control_command({"cmd": "laser_off"})

    @Slot(float)
    def set_laser_intensity(self, value: float):
        self._send_control_command({"cmd": "laser_set_intensity", "value": value})

    @Slot()
    def request_status(self):
        self._send_control_command({"cmd": "status"})
