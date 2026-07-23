import asyncio
import threading
from PySide6.QtCore import QObject, Signal, Slot
from jaeger.core import FPS

class PositionerWorker(QObject):
    move_started = Signal(int)
    move_done = Signal(int)
    error = Signal(int, str)

    def __init__(self, fps: FPS, loop: asyncio.AbstractEventLoop, positioner_id: int):
        super().__init__()
        self.positioner_id = positioner_id
        self._fps = fps
        self._loop = loop
        self._move_lock = threading.Lock()  # guards against concurrent move requests

    @Slot(float, float)
    def request_move(self, alpha: float, beta: float):
        if self._loop is None or self._fps is None:
            self.error.emit(self.positioner_id, "Positioner not initialized")
            return
        # acquire(blocking=False) is an atomic test-and-set — safe to call from main thread
        if not self._move_lock.acquire(blocking=False):
            self.error.emit(self.positioner_id, "Move already in progress")
            return
        
        # Submits coroutine to the FPSManager's asyncio loop from the main thread.
        # The lock is released inside _do_move's finally block on the worker loop.
        asyncio.run_coroutine_threadsafe(
            self._do_move(alpha, beta), self._loop
        )

    async def _do_move(self, alpha: float, beta: float):
        try:
            self.move_started.emit(self.positioner_id)
            
            # ARCHITECTURE NOTE ON BATCHING:
            # Currently, the GUI submits batch moves by calling `request_move` concurrently 
            # across multiple independent PositionerWorkers. 
            # Because `jaeger-core`'s `goto()` inherently accepts a dictionary of multiple 
            # positioners (e.g., `goto({1: (a, b), 2: (c, d)})`), it is fundamentally 
            # designed to handle bulk multi-arm moves in a single command. 
            # If CAN bus congestion occurs, or if we need to leverage jaeger-core's 
            # built-in collision detection across multiple arms, we should refactor 
            # this architecture to submit a single bulk dictionary to a centralized 
            # worker rather than firing off individual concurrent goto commands.
            print("goto called for positioner", self.positioner_id, "to", (alpha, beta))
            await self._fps.goto({self.positioner_id: (alpha, beta)})
            self.move_done.emit(self.positioner_id)
        except Exception as e:
            self.error.emit(self.positioner_id, str(e))
        finally:
            self._move_lock.release()

    def stop(self):
        # QObject doesn't need to be stopped or waited on
        pass