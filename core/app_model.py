"""Central state store.  Single source of truth for all positioner state.

Widgets read from this model and never store their own copy of position or
state.  All mutations happen on the Qt main thread.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from PySide6.QtCore import QObject, Signal
from helpers.constants import PositionerState


@dataclass
class PositionerData:
    """Typed container for a single positioner's runtime state.

    Replaces the previous raw-dict representation.  Attribute access provides
    IDE autocomplete and crashes loudly on typos instead of silently returning
    ``None`` via ``.get()``.
    """
    alpha: float = 0.0
    beta: float = 0.0
    state: PositionerState = PositionerState.READY
    center: tuple[float, float] = (0.0, 0.0)
    queued_target: tuple[float, float] | None = None
    queued_solutions: list[tuple[float, float]] = field(default_factory=list)
    queued_solution_index: int = 0


class AppModel(QObject):
    """Observable model that emits signals on every state change."""

    model_updated = Signal()
    connection_updated = Signal()

    def __init__(self):
        super().__init__()
        self.positioners: dict[int, PositionerData] = {}
        self.selected_positioner_id: int | None = None
        self.fps_connected: bool = False
        self.camera_connected: bool = False

    def set_fps_connected(self, connected: bool):
        if self.fps_connected != connected:
            self.fps_connected = connected
            self.connection_updated.emit()

    def set_camera_connected(self, connected: bool):
        if self.camera_connected != connected:
            self.camera_connected = connected
            self.connection_updated.emit()

    def register_positioner(self, positioner_id: int, center=(0.0, 0.0)):
        if positioner_id not in self.positioners:
            self.positioners[positioner_id] = PositionerData(center=center)
            if self.selected_positioner_id is None:
                self.selected_positioner_id = positioner_id
            self.model_updated.emit()

    def set_selected_positioner(self, positioner_id: int):
        if positioner_id in self.positioners and self.selected_positioner_id != positioner_id:
            self.selected_positioner_id = positioner_id
            self.model_updated.emit()

    def update_positions(self, positions: dict):
        """Update alpha/beta for each positioner, emitting only if values actually changed."""
        changed = False
        for pid, (new_alpha, new_beta) in positions.items():
            if pid in self.positioners:
                p = self.positioners[pid]
                if p.alpha != new_alpha or p.beta != new_beta:
                    p.alpha = new_alpha
                    p.beta = new_beta
                    changed = True
        if changed:
            self.model_updated.emit()

    def update_positioner_state(self, positioner_id: int, new_state: PositionerState):
        if positioner_id in self.positioners:
            self.positioners[positioner_id].state = new_state
            self.model_updated.emit()

    def queue_move(self, positioner_id: int, solutions: list, active_index: int = 0):
        if positioner_id in self.positioners and solutions:
            p = self.positioners[positioner_id]
            p.queued_solutions = solutions
            p.queued_solution_index = active_index
            p.queued_target = solutions[active_index]
            self.model_updated.emit()

    def swap_solution(self, positioner_id: int):
        if positioner_id in self.positioners:
            p = self.positioners[positioner_id]
            if len(p.queued_solutions) > 1:
                new_idx = (p.queued_solution_index + 1) % len(p.queued_solutions)
                p.queued_solution_index = new_idx
                p.queued_target = p.queued_solutions[new_idx]
                self.model_updated.emit()

    def clear_queued_moves(self):
        changed = False
        for p in self.positioners.values():
            if p.queued_target is not None:
                p.queued_target = None
                p.queued_solutions = []
                p.queued_solution_index = 0
                changed = True
        if changed:
            self.model_updated.emit()

    def get_queued_moves(self) -> dict:
        return {
            pid: p.queued_target
            for pid, p in self.positioners.items()
            if p.queued_target is not None
        }
