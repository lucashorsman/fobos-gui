"""Owns all positioner move dispatch logic — the async bridge between the Qt
main thread and the FPSManager's asyncio event loop.

This is the single code path through which all goto commands reach hardware.
Angle normalization into [-10°, 370°] happens here at the dispatch boundary.
"""

from __future__ import annotations

import asyncio
from PySide6.QtCore import QObject, Signal, Slot

from core.app_model import AppModel
from helpers.constants import PositionerState, normalize_for_positioner, SHORT_ARM_LENGTH, LONG_ARM_LENGTH
from helpers.annulus import solve_inverse_kinematics


class MoveDispatcher(QObject):
    """Coordinates positioner move requests between the Qt UI and the FPS asyncio loop.

    All move commands — single manual, XY-based, or batch queued — flow through
    ``_dispatch()`` which guards against concurrent moves, marks positioners
    MOVING, and submits the async coroutine.  Results signal back to the main
    thread via ``_move_batch_succeeded`` / ``_move_batch_failed``.
    """

    # Cross-thread signals (emitted from the FPSManager asyncio loop thread).
    # PySide6 auto-promotes to QueuedConnection when emitted from a non-main
    # thread, ensuring AppModel is only mutated from the Qt event loop.
    _move_batch_succeeded = Signal(list)
    _move_batch_failed = Signal(list)

    # UI feedback signals — MainWindow routes these to ControlPanel
    angles_updated = Signal(float, float)       # normalized (alpha, beta) for display
    invalid_position = Signal()                 # XY target outside reachable annulus

    def __init__(self, model: AppModel, parent=None):
        super().__init__(parent)
        self._model = model
        self._fps = None
        self._fps_loop: asyncio.AbstractEventLoop | None = None

        self._move_batch_succeeded.connect(self._on_batch_move_success)
        self._move_batch_failed.connect(self._on_batch_move_failure)

    def set_fps(self, fps, loop: asyncio.AbstractEventLoop):
        """Called once after FPSManager emits ready(fps, loop)."""
        self._fps = fps
        self._fps_loop = loop

    def clear_fps(self):
        """Called when FPS is disconnected / being reconnected."""
        self._fps = None
        self._fps_loop = None

    # -- Public dispatch entry points ----------------------------------------

    def on_move_requested(self, pid: int, alpha: float, beta: float):
        """Single-positioner move from the manual angle entry panel."""
        self.angles_updated.emit(
            normalize_for_positioner(alpha),
            normalize_for_positioner(beta),
        )
        self._dispatch({pid: (alpha, beta)})

    def on_xy_move_requested(self, pid: int, abs_x: float, abs_y: float):
        """Single-positioner move from the manual XY entry panel.

        Converts absolute physical coordinates to a positioner-relative offset,
        runs IK, then dispatches immediately via the same path as angle mode.
        IK and center lookup live here (not in ControlPanel) because this is
        the only layer that has access to both the model and the dispatch loop.
        """
        if pid not in self._model.positioners:
            return
        p = self._model.positioners[pid]
        cx, cy = p.center
        rel_x = abs_x - cx
        rel_y = abs_y - cy
        # Axis inversion matches the kinematic convention in Grid2d / CameraWidget.
        solutions = solve_inverse_kinematics(-rel_x, -rel_y, SHORT_ARM_LENGTH, LONG_ARM_LENGTH)
        if solutions:
            alpha, beta = solutions[0]
            self.angles_updated.emit(
                normalize_for_positioner(alpha),
                normalize_for_positioner(beta),
            )
            self.on_move_requested(pid, alpha, beta)
        else:
            self.invalid_position.emit()

    def on_batch_move_requested(self):
        """Send all queued targets to hardware in a single CAN bus transaction."""
        queued_moves = self._model.get_queued_moves()
        if not queued_moves:
            return
        # Clear queue only after confirming the coroutine was submitted.
        # If _dispatch fails, queued targets remain in the model so the
        # operator can retry or inspect what was lost.
        if self._dispatch(queued_moves):
            self._model.clear_queued_moves()

    # -- Internal dispatch ---------------------------------------------------

    def _is_any_moving(self) -> bool:
        return any(
            p.state == PositionerState.MOVING
            for p in self._model.positioners.values()
        )

    def _dispatch(self, targets: dict) -> bool:
        """Common guard, state-mutation, and asyncio submission for all move paths.

        Marks the given positioners MOVING, then submits targets to the FPS loop.
        Returns True if the coroutine was successfully submitted, False otherwise.
        On submission failure, rolls back affected positioners to ERROR so the UI
        reflects reality instead of leaving them stuck in the MOVING state.
        """
        if not self._fps or not self._fps_loop:
            return False
        if self._is_any_moving():
            print("Move already in progress, ignoring request.")
            return False

        for pid in targets:
            self._model.update_positioner_state(pid, PositionerState.MOVING)
        try:
            asyncio.run_coroutine_threadsafe(
                self._do_batch_move(targets), self._fps_loop
            )
            # Update angle display for the selected positioner
            if self._model.selected_positioner_id in targets:
                alpha, beta = targets[self._model.selected_positioner_id]
                self.angles_updated.emit(
                    normalize_for_positioner(alpha),
                    normalize_for_positioner(beta),
                )
            return True
        except RuntimeError as e:
            print(f"Failed to submit move coroutine: {e}")
            for pid in targets:
                self._model.update_positioner_state(pid, PositionerState.ERROR)
            # Reset angles on submission failure (should only happen on hw failure)
            if self._model.selected_positioner_id in targets:
                self.angles_updated.emit(0.0, 0.0)
            return False

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
            self._model.update_positioner_state(pid, PositionerState.READY)

    @Slot(list)
    def _on_batch_move_failure(self, pids: list):
        """Called on the main thread after a failed batch goto."""
        for pid in pids:
            self._model.update_positioner_state(pid, PositionerState.ERROR)
