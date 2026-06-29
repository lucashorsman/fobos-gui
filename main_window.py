#assembles all widgets and components for the main window
from widgets.grid2d import Grid2d
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel
from PySide6.QtGui import QFont
from app_model import AppModel
from PySide6.QtCore import Qt, QEvent
from workers.positioner_worker import PositionerWorker
from workers.fps_manager import FPSManager
from workers.vimba_worker import VimbaWorker
from widgets.camera_widget import CameraWidget
from widgets.status_bar import StatusBar
from widgets.control_panel import ControlPanel
from widgets.view2D import View2D
from widgets.grid2d import Grid2d
import qdarkstyle

class MainWindow(QMainWindow):
    @staticmethod
    def _normalize_for_positioner(angle: float) -> float:
        adjusted = float(angle)
        while adjusted < -10.0:
            adjusted += 360.0
        while adjusted > 370.0:
            adjusted -= 360.0
        return adjusted

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fobos GUI")
        self.setGeometry(100, 100, 1800, 1000)
       
        # Instantiate UI components
        self.status_bar = StatusBar()
        self.control_panel = ControlPanel()
        self.grid2D = Grid2d()
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
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(self.status_bar)
        self.right_splitter.addWidget(self.camera_widget)
        self.right_splitter.addWidget(self.control_panel)
        
        # create the main horizontal splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.grid2D)
        self.main_splitter.addWidget(self.right_splitter)
        
        # Set custom proportions
        self.main_splitter.setSizes([700, 300]) 
        self.right_splitter.setSizes([180, 640, 200])
        
        # Set the main splitter as the central widget
        self.setCentralWidget(self.main_splitter)
        
        self.current_main_view = self.grid2D
        self.current_small_view = self.camera_widget
        
        self.current_main_view.swap_button.setVisible(False)
        self.current_small_view.swap_button.setVisible(True)

        self.mouse_coord_label = QLabel("X: --, Y: --")
        self.mouse_coord_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.statusBar().addPermanentWidget(self.mouse_coord_label)

        self.grid2D.installEventFilter(self)
        self.camera_widget.installEventFilter(self)

        self.model = AppModel()
        
        # Wire up UI to model and actions
        self.model.model_updated.connect(self._on_model_updated)
        self.control_panel.move_requested.connect(self.on_move_requested)
        self.grid2D.move_queued.connect(self.model.queue_move)
        self.camera_widget.move_queued.connect(self.model.queue_move)
        self.control_panel.batch_move_requested.connect(self.on_batch_move_requested)
        self.control_panel.selection_changed.connect(self.model.set_selected_positioner)
        self.grid2D.selection_changed.connect(self.model.set_selected_positioner)
        self.camera_widget.selection_changed.connect(self.model.set_selected_positioner)
        self.grid2D.swap_requested.connect(self.on_swap_views_requested)
        self.camera_widget.swap_requested.connect(self.on_swap_views_requested)
        self.control_panel.calibrate_requested.connect(self.camera_widget.start_calibration)
        self.control_panel.swap_solution_requested.connect(self.model.swap_solution)
        
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
        self.vimba_worker.frame_ready.connect(self.camera_widget.update_frame, Qt.QueuedConnection)
        self.vimba_worker.error.connect(self.on_vimba_error)
        self.camera_widget.exposure_changed.connect(self.vimba_worker.set_exposure)
        self.camera_widget.gain_changed.connect(self.vimba_worker.set_gain)
        self.vimba_worker.start()

    def _on_model_updated(self): #called when the model emits model_updated, which happens whenever the positioners dict is updated with new positions or states
        self.status_bar.update_display(self.model.positioners)
        self.grid2D.update_display(self.model.positioners, self.model.selected_positioner_id)
        self.camera_widget.update_display(self.model.positioners, self.model.selected_positioner_id)
        self.control_panel.update_selected_positioner(self.model.selected_positioner_id)
        self.control_panel.update_queue_state(self.model.positioners)

    def on_batch_move_requested(self):
        queued_moves = self.model.get_queued_moves()
        for pid, (alpha, beta) in queued_moves.items():
            self.on_move_requested(pid, alpha, beta)
        self.model.clear_queued_moves()

    def on_move_requested(self, pid: int, alpha: float, beta: float):
        if pid in self.workers:
            alpha = self._normalize_for_positioner(alpha)
            beta = self._normalize_for_positioner(beta)
            self.workers[pid].request_move(alpha, beta)

    def on_swap_views_requested(self):
        view_main = self.current_main_view
        view_small = self.current_small_view
        
        idx_main = self.main_splitter.indexOf(view_main)
        idx_small = self.right_splitter.indexOf(view_small)

        # Use a dummy widget to hold the spot in right_splitter
        dummy = QWidget()
        self.right_splitter.replaceWidget(idx_small, dummy)
        
        # Now view_small is detached. Replace view_main with view_small
        self.main_splitter.replaceWidget(idx_main, view_small)
        
        # Now view_main is detached. Replace dummy with view_main
        self.right_splitter.replaceWidget(idx_small, view_main)
        
        # Clean up dummy widget
        dummy.deleteLater()
        
        # Update references
        self.current_main_view = view_small
        self.current_small_view = view_main
        
        self.current_main_view.swap_button.setVisible(False)
        self.current_small_view.swap_button.setVisible(True)

    def on_fps_ready(self, fps):
        # Discover all connected positioners
        for pid, pos in fps.positioners.items():
            center = getattr(pos, 'center', (0.0, 0.0))
            self.model.register_positioner(pid, center=center)
            
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
        self.grid2D.update_positioners(self.model.positioners.keys())
            
        print(f"FPS initialized, {len(self.workers)} workers started")
        print(f"pids in use: {self.model.positioners.keys()}")

    def on_fps_error(self, err_msg=""):
        print(f"Error initializing FPS: {err_msg}")

    def on_vimba_error(self, err_msg=""):
        print(f"Error initializing Vimba camera: {err_msg}")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove:
            if obj in (self.grid2D, self.camera_widget):
                try:
                    phys_x, phys_y = obj.get_physical_click_coords(event)
                    self.mouse_coord_label.setText(f"X: {int(phys_x)}, Y: {int(phys_y)}")
                except Exception:
                    pass
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        if self.vimba_worker:
            self.vimba_worker.stop()
        if self.poller:
            self.poller.stop()
        for worker in self.workers.values():
            worker.stop()

        #also kill the vimba worker when we get there.
        event.accept()

