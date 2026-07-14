from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QPushButton, QComboBox)
from PySide6.QtCore import Signal
from PySide6.QtGui import QDoubleValidator

class ControlPanel(QWidget):
    # Angle mode: emits positioner_id, alpha, beta
    move_requested = Signal(int, float, float)
    # XY mode: emits positioner_id, abs_x, abs_y. IK + center handled by MainWindow
    xy_move_requested = Signal(int, float, float)
    batch_move_requested = Signal()
    selection_changed = Signal(int)
    swap_solution_requested = Signal(int)
    calibrate_requested = Signal()

    def __init__(self):
        super().__init__()
        self.AngleMode = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        # layout.setContentsMargins(16, 16, 16, 16)
        # layout.setSpacing(8)
        # Title and Positioner selection on one row
        top_layout = QHBoxLayout()
        title = QLabel("<b>Control Panel</b>")
        top_layout.addWidget(title)
        
        top_layout.addStretch()
        
        top_layout.addWidget(QLabel("PID:"))
        self.pid_combo = QComboBox()
        self.pid_combo.currentIndexChanged.connect(self._on_combo_changed)
        top_layout.addWidget(self.pid_combo)
        
        layout.addLayout(top_layout)

        # Manual Entry Toggle
        self.manual_toggle_btn = QPushButton("▶ Manual Entry")
        self.manual_toggle_btn.setCheckable(True)
        self.manual_toggle_btn.setStyleSheet("text-align: left; padding: 4px; font-weight: bold;")
        self.manual_toggle_btn.toggled.connect(self._on_manual_toggle_toggled)
        layout.addWidget(self.manual_toggle_btn)

        # Manual Entry Container
        self.manual_container = QWidget()
        manual_layout = QVBoxLayout(self.manual_container)
        manual_layout.setContentsMargins(10, 0, 0, 0)

        # Alpha input
        alpha_layout = QHBoxLayout()
        if self.AngleMode:
            alpha_layout.addWidget(QLabel("Alpha (°):"))
        else:
            alpha_layout.addWidget(QLabel("X (mm):"))
        self.alpha_input = QLineEdit()
        # self.alpha_input.setValidator(QDoubleValidator(-9.0, 369.0, 4, self))
        alpha_layout.addWidget(self.alpha_input)
        manual_layout.addLayout(alpha_layout)

        # Beta input
        beta_layout = QHBoxLayout()
        if self.AngleMode:
            beta_layout.addWidget(QLabel("Beta (°):"))
        else:
            beta_layout.addWidget(QLabel("Y (mm):"))
        self.beta_input = QLineEdit()
        # self.beta_input.setValidator(QDoubleValidator(-9.0, 369.0, 4, self))
        beta_layout.addWidget(self.beta_input)
        manual_layout.addLayout(beta_layout)

        # Go To button
        self.go_button = QPushButton("Go To")
        self.go_button.setObjectName("go_button")
        self.go_button.clicked.connect(self._on_go_clicked)
        manual_layout.addWidget(self.go_button)

        layout.addWidget(self.manual_container)
        self.manual_container.setVisible(False)

        # Send Queued Targets button
        self.send_queue_button = QPushButton("No Queued Targets")
        self.send_queue_button.setObjectName("send_queue_button")
        self.send_queue_button.setEnabled(False)
        self.send_queue_button.clicked.connect(self.batch_move_requested.emit)
        layout.addWidget(self.send_queue_button)

        # Swap Solution button
        self.swap_solution_button = QPushButton("Swap Solution")
        self.swap_solution_button.setObjectName("swap_solution_button")
        self.swap_solution_button.setEnabled(False)
        self.swap_solution_button.clicked.connect(self._on_swap_solution_clicked)
        layout.addWidget(self.swap_solution_button)

        #calibrate button
        self.calibrate_button = QPushButton("Calibrate")
        self.calibrate_button.setObjectName("calibrate_button")
        self.calibrate_button.clicked.connect(self.calibrate_requested.emit)
        layout.addWidget(self.calibrate_button)
        
        layout.addStretch()

    def on_calibration_completed(self):
        self.calibrate_button.setText("Re-Calibrate")
        self.calibrate_button.setObjectName("recalibrate_button")
        self.calibrate_button.style().unpolish(self.calibrate_button)
        self.calibrate_button.style().polish(self.calibrate_button)

    def _on_manual_toggle_toggled(self, checked):
        self.manual_container.setVisible(checked)
        self.manual_toggle_btn.setText("▼ Manual Entry" if checked else "▶ Manual Entry")

    def update_positioners(self, pids):
        current_pid = self.pid_combo.currentText()
        self.pid_combo.blockSignals(True)
        self.pid_combo.clear()
        for pid in sorted(pids):
            self.pid_combo.addItem(str(pid), userData=pid)
        
        # Restore selection if it still exists
        idx = self.pid_combo.findText(current_pid)
        if idx >= 0:
            self.pid_combo.setCurrentIndex(idx)
        self.pid_combo.blockSignals(False)

    def _on_combo_changed(self, index):
        if index >= 0:
            pid = self.pid_combo.itemData(index)
            self.selection_changed.emit(pid)

    def update_selected_positioner(self, pid: int):
        if pid is None:
            return
        idx = self.pid_combo.findData(pid)
        if idx >= 0 and self.pid_combo.currentIndex() != idx:
            self.pid_combo.blockSignals(True)
            self.pid_combo.setCurrentIndex(idx)
            self.pid_combo.blockSignals(False)

    def _on_go_clicked(self):

        if self.pid_combo.count() == 0:
            return
            
        pid = self.pid_combo.currentData()
        alpha_text = self.alpha_input.text()
        beta_text = self.beta_input.text()

        try:
            val1 = float(alpha_text) if alpha_text else 0.0
            val2 = float(beta_text) if beta_text else 0.0
        except ValueError:
            return

        if not self.AngleMode:
            # Emit absolute physical coords; MainWindow resolves the positioner
            # center from AppModel, subtracts it, and runs IK — keeping this
            # widget free of domain knowledge.
            self.xy_move_requested.emit(pid, val1, val2)
        else:
            self.move_requested.emit(pid, val1, val2)

    def update_queue_state(self, positioners_dict):
        queued_count = 0
        has_moving = False
        has_error = False

        for pid, pos in positioners_dict.items():
            state = pos.get("state", "ready")
            if state == "moving":
                has_moving = True
                
            if pos.get("queued_target") is not None:
                queued_count += 1
                if state == "error":
                    has_error = True

        if has_moving:
            self.send_queue_button.setText("Moving...")
            self.send_queue_button.setEnabled(False)
            self.go_button.setEnabled(False)
        elif queued_count == 0:
            self.send_queue_button.setText("No Queued Targets")
            self.send_queue_button.setEnabled(False)
            self.go_button.setEnabled(True)
        elif has_error:
            self.send_queue_button.setText("Error")
            self.send_queue_button.setEnabled(False)
            self.go_button.setEnabled(True)
        else:
            self.send_queue_button.setText(f"Send {queued_count} Target{'s' if queued_count > 1 else ''}")
            self.send_queue_button.setEnabled(True)
            self.go_button.setEnabled(True)

        current_pid = self.pid_combo.currentData()
        if current_pid is not None and current_pid in positioners_dict:
            pos = positioners_dict[current_pid]
            if len(pos.get("queued_solutions", [])) > 1:
                self.swap_solution_button.setEnabled(True)
            else:
                self.swap_solution_button.setEnabled(False)
        else:
            self.swap_solution_button.setEnabled(False)

    def _on_swap_solution_clicked(self):
        current_pid = self.pid_combo.currentData()
        if current_pid is not None:
            self.swap_solution_requested.emit(current_pid)
