from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QPushButton, QComboBox,
                               QDialog, QTableWidget, QTableWidgetItem,
                               QHeaderView, QDialogButtonBox)
from PySide6.QtCore import Signal, QTimer, Qt
from PySide6.QtGui import QDoubleValidator
from helpers.constants import PositionerState, SHORT_ARM_LENGTH_MM, LONG_ARM_LENGTH_MM
from helpers.annulus import solve_forward_kinematics

class ControlPanel(QWidget):
    # Angle mode: emits positioner_id, alpha, beta
    move_requested = Signal(int, float, float)
    # XY mode: emits positioner_id, abs_x, abs_y. IK + center handled by MainWindow
    xy_move_requested = Signal(int, float, float)
    batch_move_requested = Signal()
    selection_changed = Signal(int)
    swap_solution_requested = Signal(int)
    calibrate_requested = Signal()
    verify_requested = Signal()

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

        layout.addWidget(QLabel("Manual Entry"))

        # Alpha / X input row
        main_inputs_layout = QHBoxLayout()
        alpha_layout = QHBoxLayout()
        alpha_layout.addWidget(QLabel("Alpha (°):"))
        self.alpha_input = QLineEdit()
        self.alpha_input.installEventFilter(self)
        alpha_layout.addWidget(self.alpha_input)
        main_inputs_layout.addLayout(alpha_layout)

        x_layout = QHBoxLayout()
        x_layout.addWidget(QLabel("X (mm):"))
        self.x_input = QLineEdit()
        self.x_input.installEventFilter(self)
        x_layout.addWidget(self.x_input)
        main_inputs_layout.addLayout(x_layout)

        layout.addLayout(main_inputs_layout)

        # Beta / Y input row
        second_inputs_layout = QHBoxLayout()
        beta_layout = QHBoxLayout()
        beta_layout.addWidget(QLabel("Beta (°):"))
        self.beta_input = QLineEdit()
        self.beta_input.installEventFilter(self)
        beta_layout.addWidget(self.beta_input)
        second_inputs_layout.addLayout(beta_layout)

        y_layout = QHBoxLayout()
        y_layout.addWidget(QLabel("Y (mm):"))
        self.y_input = QLineEdit()
        self.y_input.installEventFilter(self)
        y_layout.addWidget(self.y_input)
        second_inputs_layout.addLayout(y_layout)
        layout.addLayout(second_inputs_layout)

        # Go To button
        self.go_button = QPushButton("Go To")
        self.go_button.setObjectName("go_button")
        self.go_button.clicked.connect(self._on_go_clicked)
        layout.addWidget(self.go_button)

        # Input validation
        angle_validator = QDoubleValidator(-10.0, 370.0, 3)
        self.alpha_input.setValidator(angle_validator)
        self.beta_input.setValidator(angle_validator)

        xy_validator = QDoubleValidator()
        xy_validator.setDecimals(3)
        self.x_input.setValidator(xy_validator)
        self.y_input.setValidator(xy_validator)

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

        # Verify button
        self.verify_button = QPushButton("Verify Positions")
        self.verify_button.setObjectName("verify_button")
        self.verify_button.setEnabled(False)
        self.verify_button.clicked.connect(self.verify_requested.emit)
        layout.addWidget(self.verify_button)
        
        # Explicit tab order: Alpha→Beta→X→Y→Go
        self.setTabOrder(self.alpha_input, self.beta_input)
        self.setTabOrder(self.beta_input, self.x_input)
        self.setTabOrder(self.x_input, self.y_input)
        self.setTabOrder(self.y_input, self.go_button)

        layout.addStretch()
    def eventFilter(self, obj, event):
        # Check if a text box was clicked into (gained focus)
        if event.type() == event.Type.FocusIn:
            if obj in [self.alpha_input, self.beta_input]:
                self.AngleMode = True
                self.set_exclusive_state(active=self.alpha_input, inactive=self.x_input)
                self.set_exclusive_state(active=self.beta_input, inactive=self.y_input)
            elif obj in [self.x_input, self.y_input]:
                self.AngleMode = False
                self.set_exclusive_state(active=self.x_input, inactive=self.alpha_input)
                self.set_exclusive_state(active=self.y_input, inactive=self.beta_input)
        return super().eventFilter(obj, event)
    

    def set_exclusive_state(self, active, inactive):
        # Make active box editable and normal style
        active.setReadOnly(False)
        active.setStyleSheet("")
        
        # Freeze inactive box and make it look dimmed within the dark theme
        inactive.setReadOnly(True)
        inactive.setStyleSheet(
            "background-color: #1a1a20; color: #686878; border: 1px solid #3a3a45;"
        )

    def on_calibration_completed(self):
        self.calibrate_button.setText("Re-Calibrate")
        self.calibrate_button.setObjectName("recalibrate_button")
        self.calibrate_button.style().unpolish(self.calibrate_button)
        self.calibrate_button.style().polish(self.calibrate_button)

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
        x_text = self.x_input.text()
        y_text = self.y_input.text()

        try:
            alpha = float(alpha_text) if alpha_text else 0.0
            beta = float(beta_text) if beta_text else 0.0
            x = float(x_text) if x_text else 0.0
            y = float(y_text) if y_text else 0.0
        except ValueError:
            return

        if not self.AngleMode:
            # Emit absolute physical coords; MainWindow resolves the positioner
            # center from AppModel, subtracts it, and runs IK — keeping this
            # widget free of domain knowledge.
            self.xy_move_requested.emit(pid, x, y)
            
        else:
            self.move_requested.emit(pid, alpha, beta)

    def update_queue_state(self, positioners_dict):
        queued_count = 0
        has_moving = False
        has_error = False

        for pid, pos in positioners_dict.items():
            if pos.state == PositionerState.MOVING:
                has_moving = True
                
            if pos.queued_target is not None:
                queued_count += 1
                if pos.state == PositionerState.ERROR:
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
            if len(pos.queued_solutions) > 1:
                self.swap_solution_button.setEnabled(True)
            else:
                self.swap_solution_button.setEnabled(False)
        else:
            self.swap_solution_button.setEnabled(False)

    def update_angles(self, alpha: float, beta: float):
        """Populate the alpha/beta fields with the given angles.

        Called by MainWindow after resolving an XY goto through IK, so the
        operator can see which angles correspond to the requested position.
        Values are formatted to 3 decimal places.
        """
        self.alpha_input.setText(f"{alpha:.3f}")
        self.beta_input.setText(f"{beta:.3f}")

    def update_current_positioner_data(self, pos):
        """Fill all input fields with the settled state of the selected positioner.

        Called only when the selected PID changes or a move completes
        (MOVING → READY), so it is always safe to overwrite the fields.
        Uses forward kinematics to derive the XY display from alpha/beta.

        Args:
            pos: PositionerData for the currently selected positioner, or None.
        """
        if pos is None:
            return

        self.alpha_input.setText(f"{pos.alpha:.3f}")
        self.beta_input.setText(f"{pos.beta:.3f}")

        try:
            cx, cy = pos.center
            x, y = solve_forward_kinematics(
                pos.alpha, pos.beta, cx, cy, SHORT_ARM_LENGTH_MM, LONG_ARM_LENGTH_MM
            )
            self.x_input.setText(f"{x:.3f}")
            self.y_input.setText(f"{y:.3f}")
        except Exception:
            pass

    def flash_invalid_position(self, duration_ms: int = 800):
        """Briefly change the Go button label to signal an unreachable position.

        Called by MainWindow when IK returns no solutions for the requested
        XY coordinate (i.e. outside the reachable annulus).
        """
        self.go_button.setText("Invalid Position")
        self.go_button.setStyleSheet("background-color: #ef4444;")
        self.go_button.setEnabled(False)
        QTimer.singleShot(duration_ms, self._reset_go_button)

    def _reset_go_button(self):
        self.go_button.setText("Go To")
        self.go_button.setStyleSheet("")
        self.go_button.setEnabled(True)


    def _on_swap_solution_clicked(self):
        current_pid = self.pid_combo.currentData()
        if current_pid is not None:
            self.swap_solution_requested.emit(current_pid)

    # -- Verify feature ------------------------------------------------------

    def update_verify_state(self, verify_enabled: bool, verify_in_progress: bool):
        """Enable/disable the Verify button based on system readiness.

        Called by MainWindow whenever model state changes.  The button is
        enabled only when:
        - The laser mapping interpolator is loaded
        - Camera and FPS are connected
        - No move or verify is in progress
        """
        if verify_in_progress:
            self.verify_button.setText("Verifying...")
            self.verify_button.setEnabled(False)
        elif verify_enabled:
            self.verify_button.setText("Verify Positions")
            self.verify_button.setEnabled(True)
        else:
            self.verify_button.setText("Verify Positions")
            self.verify_button.setEnabled(False)

    def show_verify_results(self, results: dict, unmatched: list | None = None):
        """Pop a modal dialog showing the per-positioner verify results."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Verify Results")
        dialog.setMinimumWidth(600)

        layout = QVBoxLayout(dialog)

        # Summary label
        n_total = len(results)
        n_pass = sum(1 for r in results.values() if r.get("pass"))
        n_found = sum(1 for r in results.values() if r.get("found"))
        summary_color = "#4ade80" if n_pass == n_total else "#f87171"
        summary = QLabel(
            f"<b style='color: {summary_color};'>"
            f"{n_pass}/{n_total} PASSED</b> &nbsp; "
            f"({n_found}/{n_total} detected)"
        )
        layout.addWidget(summary)

        # Results table
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "PID", "Expected (px)", "Measured (px)", "Error (px)", "Flux", "Result"
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setRowCount(n_total)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, (fid, r) in enumerate(sorted(results.items())):
            table.setItem(row, 0, QTableWidgetItem(str(fid)))

            ex, ey = r.get("expected_px", (0, 0))
            table.setItem(row, 1, QTableWidgetItem(f"({ex:.1f}, {ey:.1f})"))

            if r.get("measured_px"):
                mx, my = r["measured_px"]
                table.setItem(row, 2, QTableWidgetItem(f"({mx:.1f}, {my:.1f})"))
            else:
                table.setItem(row, 2, QTableWidgetItem("—"))

            if r.get("error_px") is not None:
                table.setItem(row, 3, QTableWidgetItem(f"{r['error_px']:.2f}"))
            else:
                table.setItem(row, 3, QTableWidgetItem("—"))

            table.setItem(row, 4, QTableWidgetItem(f"{r.get('flux', 0):.0f}"))

            if r.get("pass"):
                result_item = QTableWidgetItem("✓ PASS")
                result_item.setForeground(Qt.green)
            elif r.get("found"):
                result_item = QTableWidgetItem("✗ FAIL")
                result_item.setForeground(Qt.red)
            else:
                result_item = QTableWidgetItem("NOT FOUND")
                result_item.setForeground(Qt.yellow)
            table.setItem(row, 5, result_item)

        layout.addWidget(table)

        # Unmatched blobs info
        if unmatched:
            unmatched_label = QLabel(
                f"<i>{len(unmatched)} unmatched blob(s) detected "
                f"(stray light / unexpected spots)</i>"
            )
            unmatched_label.setStyleSheet("color: #facc15;")
            layout.addWidget(unmatched_label)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()
