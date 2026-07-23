from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
from PySide6.QtCore import Signal
from helpers.annulus import solve_forward_kinematics
from helpers.constants import SHORT_ARM_LENGTH_MM, LONG_ARM_LENGTH_MM

class StatusBar(QWidget):
    reconnect_fps_requested = Signal()
    reconnect_camera_requested = Signal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        
        # Connection status layout
        conn_layout = QHBoxLayout()
        
        self.fps_status_label = QLabel("FPS")
        self.fps_status_indicator = QLabel("OFFLINE")
        self.fps_status_indicator.setObjectName("status_offline")
        self.btn_reconnect_fps = QPushButton("Reconnect FPS")
        self.btn_reconnect_fps.clicked.connect(self.reconnect_fps_requested.emit)
        
        self.camera_status_label = QLabel("Camera")
        self.camera_status_indicator = QLabel("OFFLINE")
        self.camera_status_indicator.setObjectName("status_offline")
        self.btn_reconnect_camera = QPushButton("Reconnect Camera")
        self.btn_reconnect_camera.clicked.connect(self.reconnect_camera_requested.emit)
        
        conn_layout.addWidget(self.fps_status_label)
        conn_layout.addWidget(self.fps_status_indicator)
        conn_layout.addWidget(self.btn_reconnect_fps)
        conn_layout.addStretch()
        conn_layout.addWidget(self.camera_status_label)
        conn_layout.addWidget(self.camera_status_indicator)
        conn_layout.addWidget(self.btn_reconnect_camera)
        
        layout.addLayout(conn_layout)
        
        title = QLabel("<b>Status Readout</b>")
        layout.addWidget(title)
        
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        # Use a monospaced font for better alignment
        # self.text_display.setStyleSheet("font-family: monospace;")
        layout.addWidget(self.text_display)

    def _set_indicator(self, indicator: QLabel, connected: bool):
        if connected:
            indicator.setText("CONNECTED")
            indicator.setObjectName("status_connected")
        else:
            indicator.setText("OFFLINE")
            indicator.setObjectName("status_offline")
        # Force QSS re-evaluation after objectName change
        indicator.style().unpolish(indicator)
        indicator.style().polish(indicator)

    def update_connections(self, fps_connected: bool, camera_connected: bool):
        self._set_indicator(self.fps_status_indicator, fps_connected)
        self.btn_reconnect_fps.setVisible(not fps_connected)

        self._set_indicator(self.camera_status_indicator, camera_connected)
        self.btn_reconnect_camera.setVisible(not camera_connected)

    def update_display(self, positioners_dict):
        lines = []
        for pid in sorted(positioners_dict.keys()):
            pos = positioners_dict[pid]
            
            x, y = solve_forward_kinematics(pos.alpha, pos.beta, pos.center[0], pos.center[1], SHORT_ARM_LENGTH_MM, LONG_ARM_LENGTH_MM)
            
            #| α: {alpha:>7.2f}° | β: {beta:>7.2f}° 
            line = f"PID {pid:03d} | "
            line += f"State: {pos.state.upper()} | Location (mm): ({x:.2f}, {y:.2f})"
            
            lines.append(line)
            
        if not lines:
            self.text_display.setText("Waiting for positioners...")
        else:
            self.text_display.setText("\n".join(lines))
