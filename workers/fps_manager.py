import asyncio
import traceback
import os
import time
from PySide6.QtCore import QThread, Signal
from jaeger.core import FPS

POLL_INTERVAL = 1 / 3

class FPSManager(QThread):
    ready = Signal(object, object)  # (fps, loop)
    positions_updated = Signal(object)
    error = Signal(str)
    connection_status = Signal(bool)

    def __init__(self):
        super().__init__()
        self._fps = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._is_connected = False

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        # Schedule the setup task
        self._loop.create_task(self._main())
        
        # jaeger-core expects to be in a run_forever loop.
        # It will explicitly call self._loop.stop() when its shutdown() method is called.
        self._loop.run_forever()
        
        # Clean up the loop once it has stopped
        self._loop.close()

    async def _main(self):
        self._stop_event = asyncio.Event()
        try:
            if os.environ.get("FOBOS_MOCK") == "1":
                from .mock_fps import MockFPS
                self._fps = MockFPS(num_positioners=5)
            else:
                from jaeger.core import FPS
                # Create a clean, new FPS instance. 
                # Since we properly call shutdown() on teardown, there's no need to manually discard old instances.
                self._fps = FPS()

            await self._fps.initialise()
            
            # Check if CAN connection succeeded (jaeger-core returns early with a warning if not)
            if os.environ.get("FOBOS_MOCK") != "1":
                if getattr(self._fps, "can", None) is None or len(self._fps.can.interfaces) == 0:
                    raise ConnectionError("FPS failed to connect: CAN interfaces not found.")

            self._is_connected = True
            self.connection_status.emit(True)
            self.ready.emit(self._fps, self._loop)
            
            await self._poll_loop()
        except Exception as e:
            print(f"FPSManager main loop error: {e}")
            self.error.emit(str(e))
            self.connection_status.emit(False)
            # If initialization fails, we must manually stop the loop since shutdown() won't be called.
            self._loop.stop()

    async def _poll_loop(self):
        timeout_count = 0
        while not self._stop_event.is_set():
            try:
                start_time = time.time()
                await self._fps.update_position()
                elapsed = time.time() - start_time
                
                # Detect jaeger-core timeout (usually takes > 2s when timing out on network drop)
                if elapsed > 1.5 and os.environ.get("FOBOS_MOCK") != "1":
                    timeout_count += 1
                else:
                    if timeout_count > 0 or not self._is_connected:
                        self._is_connected = True
                        self.connection_status.emit(True)
                    timeout_count = 0

                if timeout_count >= 3 and self._is_connected:
                    self._is_connected = False
                    self.connection_status.emit(False)

                positions = {}
                for pid, p in self._fps.positioners.items():
                    positions[pid] = (float(p.alpha), float(p.beta))
                self.positions_updated.emit(positions)
            except Exception as e:
                # Poller was likely cancelled or failed during shutdown
                if not self._stop_event.is_set():
                    print(f"FPSManager iteration error: {e}")
                    traceback.print_exc()
            await asyncio.sleep(POLL_INTERVAL)

    def stop(self):
        if self._loop and not self._loop.is_closed():
            if self._stop_event:
                self._loop.call_soon_threadsafe(self._stop_event.set)
                
            # Jaegar-core's shutdown() is an async coroutine that cleans up tasks and calls loop.stop()
            if self._fps and hasattr(self._fps, "shutdown"):
                asyncio.run_coroutine_threadsafe(self._fps.shutdown(), self._loop)
            else:
                self._loop.call_soon_threadsafe(self._loop.stop)
                
        self.wait()
