from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QPushButton, QComboBox)
from PySide6.QtCore import Signal
from PySide6.QtGui import QDoubleValidator

class ControlPanel(QWidget):
    # Emits positioner_id, alpha, beta
    move_requested = Signal(int, float, float)
    batch_move_requested = Signal()
    selection_changed = Signal(int)
    swap_views_requested = Signal()
    swap_solution_requested = Signal(int)
    calibrate_requested = Signal()

    def __init__(self):
        super().__init__()

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        # layout.setContentsMargins(16, 16, 16, 16)
        # layout.setSpacing(8)
        # Title
        title = QLabel("<b>Control Panel</b>")
        layout.addWidget(title)

        # Positioner selection
        pid_layout = QHBoxLayout()
        pid_layout.addWidget(QLabel("Positioner ID:"))
        self.pid_combo = QComboBox()
        self.pid_combo.currentIndexChanged.connect(self._on_combo_changed)
        pid_layout.addWidget(self.pid_combo)
        layout.addLayout(pid_layout)

        # Alpha input
        alpha_layout = QHBoxLayout()
        alpha_layout.addWidget(QLabel("Alpha (°):"))
        self.alpha_input = QLineEdit()
        self.alpha_input.setValidator(QDoubleValidator(-9.0, 369.0, 4, self))
        alpha_layout.addWidget(self.alpha_input)
        layout.addLayout(alpha_layout)

        # Beta input
        beta_layout = QHBoxLayout()
        beta_layout.addWidget(QLabel("Beta (°):"))
        self.beta_input = QLineEdit()
        self.beta_input.setValidator(QDoubleValidator(-9.0, 369.0, 4, self))
        beta_layout.addWidget(self.beta_input)
        layout.addLayout(beta_layout)

        # Go To button
        self.go_button = QPushButton("Go To")
        self.go_button.clicked.connect(self._on_go_clicked)
        layout.addWidget(self.go_button)

        # Send Queued Targets button
        self.send_queue_button = QPushButton("No Queued Targets")
        self.send_queue_button.setEnabled(False)
        self.send_queue_button.clicked.connect(self.batch_move_requested.emit)
        layout.addWidget(self.send_queue_button)

        # Swap Solution button
        self.swap_solution_button = QPushButton("Swap Solution")
        self.swap_solution_button.setEnabled(False)
        self.swap_solution_button.clicked.connect(self._on_swap_solution_clicked)
        layout.addWidget(self.swap_solution_button)

        # Swap Views button
        self.swap_button = QPushButton("Swap Views")
        self.swap_button.clicked.connect(self.swap_views_requested.emit)
        layout.addWidget(self.swap_button)
        
        #calibrate button
        self.calibrate_button = QPushButton("Calibrate")
        self.calibrate_button.clicked.connect(self.calibrate_requested.emit)
        layout.addWidget(self.calibrate_button)

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
            alpha = float(alpha_text) if alpha_text else 0.0
            beta = float(beta_text) if beta_text else 0.0
            self.move_requested.emit(pid, alpha, beta)
        except ValueError:
            # Handle invalid input gracefully
            pass

    def update_queue_state(self, positioners_dict):
        queued_count = 0
        has_moving = False
        has_error = False

        for pid, pos in positioners_dict.items():
            if pos.get("queued_target") is not None:
                queued_count += 1
                state = pos.get("state", "ready")
                if state == "moving":
                    has_moving = True
                elif state == "error":
                    has_error = True

        if queued_count == 0:
            self.send_queue_button.setText("No Queued Targets")
            self.send_queue_button.setEnabled(False)
        elif has_moving:
            self.send_queue_button.setText("Moving...")
            self.send_queue_button.setEnabled(False)
        elif has_error:
            self.send_queue_button.setText("Error")
            self.send_queue_button.setEnabled(False)
        else:
            self.send_queue_button.setText(f"Send {queued_count} Target{'s' if queued_count > 1 else ''}")
            self.send_queue_button.setEnabled(True)

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
