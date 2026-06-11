#holds the state of the application, like current alpha/beta of the positioner
#whether the positioner is moving/ready/errored
#other widgets will connect to the signals emitted by this class
#this class emits model_updated() whenever the state changes, and the widgets will update themselves accordingly

from PySide6.QtCore import QObject, Signal

class AppModel(QObject):
    model_updated = Signal()

    def __init__(self):
        super().__init__()
        self.alpha = 0.0
        self.beta = 0.0
        self.positioner_state = "ready"  # can be "ready", "moving", "errored"

    def update_positions(self, new_alpha, new_beta):
        self.alpha = new_alpha
        self.beta = new_beta
        self.model_updated.emit()

    def update_positioner_state(self, new_state):
        self.positioner_state = new_state
        self.model_updated.emit()