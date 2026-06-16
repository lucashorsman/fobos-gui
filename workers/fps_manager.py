import asyncio
import traceback
import os
from PySide6.QtCore import QThread, Signal
from jaeger.core import FPS

POLL_INTERVAL = 1 / 3

class FPSManager(QThread):
    ready = Signal(object)
    positions_updated = Signal(object)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._fps = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())
        self._loop.close()

    async def _main(self):
        self._stop_event = asyncio.Event()
        try:
            if os.environ.get("FOBOS_MOCK") == "1":
                from workers.mock_fps import MockFPS
                self._fps = MockFPS(num_positioners=5)
            else:
                from jaeger.core import FPS
                self._fps = FPS()

            await self._fps.initialise()
            self.ready.emit(self._fps)
            
            await self._poll_loop()
        except Exception as e:
            print(f"FPSManager main loop error: {e}")
            self.error.emit(str(e))

    async def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                await self._fps.update_position()
                positions = {}
                for pid, p in self._fps.positioners.items():
                    positions[pid] = (float(p.alpha), float(p.beta))
                self.positions_updated.emit(positions)
            except Exception as e:
                print(f"FPSManager iteration error: {e}")
                traceback.print_exc()
            await asyncio.sleep(POLL_INTERVAL)

    def stop(self):
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self.wait()
