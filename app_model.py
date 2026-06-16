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

    def register_positioner(self, positioner_id: int):
        if positioner_id not in self.positioners:
            self.positioners[positioner_id] = {
                "alpha": 0.0,
                "beta": 0.0,
                "state": "ready"
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