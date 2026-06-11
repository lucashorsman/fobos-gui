#manages the api connection to the positioner
#runs in a separate thread, so it can do blocking calls to the positioner without freezing the UI
#communicates with the main thread via signals/slots, to update the app model with new positions and state of the positioner
from PySide6.QtCore import QObject, Signal
from app_model import AppModel
import constants
import asyncio
from PySide6.QtCore import QThread, Signal, Slot
from jaeger.core import FPS

POLL_INTERVAL = 1 / 3  # 3hz

class PositionerWorker(QThread):
    position_updated = Signal(float, float)
    move_done = Signal()
    move_started = Signal()
    error = Signal(str)

    def __init__(self, positioner_id: int):
        super().__init__()
        self.positioner_id = positioner_id
        self._loop = None
        self._fps = None
        self._is_moving = False
        self._stop_event = None

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        self._loop.run_until_complete(self._main())

    async def _main(self):
        try:
            self._fps = FPS()
            await self._fps.initialise()
            await self._poll_loop()
        except Exception as e:
            self.error.emit(str(e))

    async def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                await self._fps.update_position()
                p = self._fps[self.positioner_id]
                self.position_updated.emit(p.alpha, p.beta)
            except Exception as e:
                self.error.emit(str(e))
            await asyncio.sleep(POLL_INTERVAL)

    @Slot(float, float)
    def request_move(self, alpha: float, beta: float):
        if self._loop is None or self._fps is None:
            self.error.emit("Positioner not initialized")
            return
        if self._is_moving:
            self.error.emit("Move already in progress")
            return
        asyncio.run_coroutine_threadsafe(
            self._do_move(alpha, beta), self._loop
        )

    async def _do_move(self, alpha: float, beta: float):
        try:
            self._is_moving = True
            self.move_started.emit()
            await self._fps[self.positioner_id].goto(alpha, beta)
            await self._fps.update_position()
            p = self._fps[self.positioner_id]
            self.position_updated.emit(p.alpha, p.beta)
            self.move_done.emit()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self._is_moving = False

    def stop(self):
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self.wait()