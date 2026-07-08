from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
from PySide6.QtCore import Signal

class StatusBar(QWidget):
    reconnect_fps_requested = Signal()
    reconnect_camera_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Connection status layout
        conn_layout = QHBoxLayout()
        
        self.fps_status_label = QLabel("🔴 FPS Offline")
        self.btn_reconnect_fps = QPushButton("Reconnect FPS")
        self.btn_reconnect_fps.clicked.connect(self.reconnect_fps_requested.emit)
        
        self.camera_status_label = QLabel("🔴 Camera Offline")
        self.btn_reconnect_camera = QPushButton("Reconnect Camera")
        self.btn_reconnect_camera.clicked.connect(self.reconnect_camera_requested.emit)
        
        conn_layout.addWidget(self.fps_status_label)
        conn_layout.addWidget(self.btn_reconnect_fps)
        conn_layout.addStretch()
        conn_layout.addWidget(self.camera_status_label)
        conn_layout.addWidget(self.btn_reconnect_camera)
        
        layout.addLayout(conn_layout)
        
        title = QLabel("<b>Status Readout</b>")
        layout.addWidget(title)
        
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        # Use a monospaced font for better alignment
        # self.text_display.setStyleSheet("font-family: monospace;")
        layout.addWidget(self.text_display)

    def update_connections(self, fps_connected: bool, camera_connected: bool):
        if fps_connected:
            self.fps_status_label.setText("🟢 FPS Connected")
            self.btn_reconnect_fps.setVisible(False)
        else:
            self.fps_status_label.setText("🔴 FPS Offline")
            self.btn_reconnect_fps.setVisible(True)
            
        if camera_connected:
            self.camera_status_label.setText("🟢 Camera Connected")
            self.btn_reconnect_camera.setVisible(False)
        else:
            self.camera_status_label.setText("🔴 Camera Offline")
            self.btn_reconnect_camera.setVisible(True)

    def update_display(self, positioners_dict):
        lines = []
        for pid in sorted(positioners_dict.keys()):
            state = positioners_dict[pid]
            alpha = state.get("alpha", 0.0)
            beta = state.get("beta", 0.0)
            status = state.get("state", "unknown")
            
            line = f"PID {pid:03d} | α: {alpha:>7.2f}° | β: {beta:>7.2f}° | "
            line += f"State: {status.upper()} | Center: {state.get('center', (0.0, 0.0))}"
            
            lines.append(line)
            
        if not lines:
            self.text_display.setText("Waiting for positioners...")
        else:
            self.text_display.setText("\n".join(lines))
