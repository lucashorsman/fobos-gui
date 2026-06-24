import asyncio
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
        self._is_moving = False

    @Slot(float, float)
    def request_move(self, alpha: float, beta: float):
        if self._loop is None or self._fps is None:
            self.error.emit(self.positioner_id, "Positioner not initialized")
            return
        if self._is_moving:
            self.error.emit(self.positioner_id, "Move already in progress")
            return
        
        # Submits coroutine to the FPSManager's asyncio loop from the main thread
        asyncio.run_coroutine_threadsafe(
            self._do_move(alpha, beta), self._loop
        )
    async def _do_move(self, alpha: float, beta: float):
        try:
            self._is_moving = True
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
            await self._fps.goto({self.positioner_id: (alpha, beta)})
            
            self.move_done.emit(self.positioner_id)
        except Exception as e:
            self.error.emit(self.positioner_id, str(e))
        finally:
            self._is_moving = False

    def stop(self):
        # QObject doesn't need to be stopped or waited on
        pass