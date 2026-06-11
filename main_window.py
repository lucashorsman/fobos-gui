#assembles all widgets and components for the main window
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from app_model import AppModel
import workers.positioner_worker as pos_worker
from constants import POSITIONER_ID 
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fobos GUI")
        self.setGeometry(100, 100, 1200, 800)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout()
        
        self.central_widget.setLayout(self.layout)
        self.model = AppModel()
        self.positioner_worker = pos_worker.PositionerWorker(positioner_id=POSITIONER_ID)
        self.positioner_worker.position_updated.connect(self.model.update_positions)
        self.positioner_worker.move_started.connect(
            lambda: self.model.update_positioner_state("moving")
        )
        self.positioner_worker.move_done.connect(
            lambda: self.model.update_positioner_state("ready")
        )
        self.positioner_worker.error.connect(
            lambda e: self.model.update_positioner_state("error")
        )
        self.positioner_worker.start()