#holds the state of the application, like current alpha/beta of the positioners
#whether the positioners are moving/ready/errored
#other widgets will connect to the signals emitted by this class
#this class emits model_updated() whenever the state changes, and the widgets will update themselves accordingly

from PySide6.QtCore import QObject, Signal

class AppModel(QObject):
    model_updated = Signal()

    def __init__(self):
        super().__init__()
        self.positioners = {}
        self.selected_positioner_id = None
        # {id: {"alpha": 0.0, "beta": 0.0, "state": "ready"}}

    def register_positioner(self, positioner_id: int, center=(0.0, 0.0)):
        if positioner_id not in self.positioners:
            self.positioners[positioner_id] = {
                "alpha": 0.0,
                "beta": 0.0,
                "state": "ready",
                "center": center,
                "queued_target": None,
                "queued_solutions": [],
                "queued_solution_index": 0,
            }
            if self.selected_positioner_id is None:
                self.selected_positioner_id = positioner_id
            self.model_updated.emit()


    def set_selected_positioner(self, positioner_id: int):
        if positioner_id in self.positioners and self.selected_positioner_id != positioner_id:
            self.selected_positioner_id = positioner_id
            self.model_updated.emit()

    def update_positions(self, positions: dict):
        changed = False
        for pid, (new_alpha, new_beta) in positions.items():
            if pid in self.positioners:
                self.positioners[pid]["alpha"] = new_alpha
                self.positioners[pid]["beta"] = new_beta
                changed = True
        if changed:
            self.model_updated.emit()

    def update_positioner_state(self, positioner_id: int, new_state: str):
        if positioner_id in self.positioners:
            self.positioners[positioner_id]["state"] = new_state
            self.model_updated.emit()

    def queue_move(self, positioner_id: int, solutions: list, active_index: int = 0):
        if positioner_id in self.positioners and solutions:
            self.positioners[positioner_id]["queued_solutions"] = solutions
            self.positioners[positioner_id]["queued_solution_index"] = active_index
            self.positioners[positioner_id]["queued_target"] = solutions[active_index]
            self.model_updated.emit()

    def swap_solution(self, positioner_id: int):
        if positioner_id in self.positioners:
            pos = self.positioners[positioner_id]
            solutions = pos.get("queued_solutions", [])
            if len(solutions) > 1:
                idx = pos.get("queued_solution_index", 0)
                new_idx = (idx + 1) % len(solutions)
                pos["queued_solution_index"] = new_idx
                pos["queued_target"] = solutions[new_idx]
                self.model_updated.emit()

    def clear_queued_moves(self):
        changed = False
        for pid in self.positioners:
            if self.positioners[pid].get("queued_target") is not None:
                self.positioners[pid]["queued_target"] = None
                self.positioners[pid]["queued_solutions"] = []
                self.positioners[pid]["queued_solution_index"] = 0
                changed = True
        if changed:
            self.model_updated.emit()

    def get_queued_moves(self) -> dict:
        return {pid: pos["queued_target"] for pid, pos in self.positioners.items() if pos["queued_target"] is not None}