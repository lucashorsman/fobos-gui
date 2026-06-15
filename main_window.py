#assembles all widgets and components for the main window
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter
from app_model import AppModel
from PySide6.QtCore import Qt
from workers.positioner_worker import PositionerWorker
from workers.fps_manager import FPSManager
from workers.vimba_worker import VimbaWorker
from widgets.camera_widget import CameraWidget
from widgets.status_bar import StatusBar
from widgets.control_panel import ControlPanel
from widgets.view2D import View2D
import qdarkstyle

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fobos GUI")
        self.setGeometry(100, 100, 1800, 1000)
       
        # Instantiate UI components
        self.status_bar = StatusBar()
        self.control_panel = ControlPanel()
        self.view2D = View2D()
        self.camera_widget = CameraWidget()
        #i guess we can use CSS
        # self.setStyleSheet("""
        #     QSplitter::handle {
        #         background-color: #555555;  /* Color of the handle line */
        #         margin: 2px;               /* Adds a bit of padding around the line */
        #         border-radius: 2px;        /* Softens the handle edges */
        #     }

        #     QSplitter::handle:horizontal {
        #         width: 6px;                 /* Thickness of the vertical divider line */
        #     }
        #     QSplitter::handle:vertical {
        #         height: 6px;                /* Thickness of the horizontal divider line */
        #     }
        # """)
        self.setStyleSheet(qdarkstyle.load_stylesheet())
        # create the right-side vertical splitter for Status and Control
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.status_bar)
        right_splitter.addWidget(self.control_panel)
        # create the main horizontal splitter to separate View2D and the right side
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(self.view2D)
        main_splitter.addWidget(self.camera_widget)
        main_splitter.addWidget(right_splitter)  # Nest the right splitter inside the main one
        # Set custom proportions
        # Gives 70% width to View2D and 30% to the right side initially
        main_splitter.setSizes([520, 520, 240]) 
        # Gives 30% height to Status Bar and 70% to Control Panel initially
        right_splitter.setSizes([180, 420])
        
        # Set the main splitter as the central widget
        self.setCentralWidget(main_splitter)

        self.model = AppModel()
        
        # Wire up UI to model and actions
        self.model.model_updated.connect(self._on_model_updated)
        self.control_panel.move_requested.connect(self.on_move_requested)
        
        self.poller = None
        self.vimba_worker = None
        self.workers = {}
        
        # Start the poller which will initialize the FPS instance
        self.poller = FPSManager()
        #get the move_requested signal from the control panel and connect it to the on_move_requested slot in this class, which will forward the request to the appropriate worker 
        #now, when the control panel emits move_requested, the main window will receive it and call on_move_requested, which will then call request_move on the appropriate PositionerWorker instance, which will call goto.
        self.poller.ready.connect(self.on_fps_ready)
        self.poller.positions_updated.connect(self.model.update_positions)
        self.poller.error.connect(self.on_fps_error)
        self.poller.start()

        self.vimba_worker = VimbaWorker(self)
        self.vimba_worker.frame_ready.connect(self.camera_widget.update_frame)
        self.vimba_worker.error.connect(self.on_vimba_error)
        self.vimba_worker.start()

    def _on_model_updated(self): #called when the model emits model_updated, which happens whenever the positioners dict is updated with new positions or states
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

    def on_vimba_error(self, err_msg=""):
        print(f"Error initializing Vimba camera: {err_msg}")

    def closeEvent(self, event):
        if self.vimba_worker:
            self.vimba_worker.stop()
        if self.poller:
            self.poller.stop()
        for worker in self.workers.values():
            worker.stop()

        #also kill the vimba worker when we get there.
        event.accept()

