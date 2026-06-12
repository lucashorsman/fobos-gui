#assembles all widgets and components for the main window
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from app_model import AppModel
from workers.positioner_worker import PositionerWorker
from workers.fps_manager import FPSManager
from widgets.status_bar import StatusBar
from widgets.control_panel import ControlPanel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fobos GUI")
        self.setGeometry(100, 100, 800, 600)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout()
        
        self.central_widget.setLayout(self.layout)
        
        # Instantiate UI components
        self.status_bar = StatusBar()
        self.control_panel = ControlPanel()
        
        self.layout.addWidget(self.status_bar)
        self.layout.addWidget(self.control_panel)

        self.model = AppModel()
        
        # Wire up UI to model and actions
        self.model.model_updated.connect(self._on_model_updated)
        self.control_panel.move_requested.connect(self.on_move_requested)
        
        self.poller = None
        self.workers = {}
        
        # Start the poller which will initialize the FPS instance
        self.poller = FPSManager()
        self.poller.ready.connect(self.on_fps_ready)
        self.poller.positions_updated.connect(self.model.update_positions)
        self.poller.error.connect(self.on_fps_error)
        self.poller.start()

    def _on_model_updated(self):
        self.status_bar.update_display(self.model.positioners)

    def on_move_requested(self, pid: int, alpha: float, beta: float):
        if pid in self.workers:
            self.workers[pid].request_move(alpha, beta)

    def on_fps_ready(self, fps):
        # Discover all connected positioners
        for pid in list(fps.positioners.keys()):
            self.model.register_positioner(pid)
            
            worker = PositionerWorker(fps, self.poller._loop, positioner_id=pid)
            
            # Use default argument lambda id=pid to correctly capture the variable in the loop
            worker.move_started.connect(
                lambda id=pid: self.model.update_positioner_state(id, "moving")
            )
            worker.move_done.connect(
                lambda id=pid: self.model.update_positioner_state(id, "ready")
            )
            worker.error.connect(
                lambda id=pid, e="": self.model.update_positioner_state(id, "error")
            )
            
            self.workers[pid] = worker
            
        # Update dropdown
        self.control_panel.update_positioners(self.model.positioners.keys())
            
        print(f"FPS initialized, {len(self.workers)} workers started")
        print(f"pids in use: {self.model.positioners.keys()}")

    def on_fps_error(self, err_msg=""):
        print(f"Error initializing FPS: {err_msg}")
