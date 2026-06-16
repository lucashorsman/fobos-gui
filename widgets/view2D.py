import sys

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from helpers.annulus import solve_inverse_kinematics
import math
from helpers.constants import SHORT_ARM_LENGTH, LONG_ARM_LENGTH


class View2D(QWidget):
    # Emits positioner_id, alpha, beta
    move_requested = Signal(int, float, float)

    def __init__(self):
        super().__init__()
        self.validSolutionExists = False
        self._selected_positioner_state = "ready"
        self.panel_width = 170
        self.margin = 24
        self.link_lengths = (SHORT_ARM_LENGTH, LONG_ARM_LENGTH)
        self.target_offset = None
        self._positioner_ids = []
        self._selected_pid = None

        self.setMinimumSize(400, 300)
        self.setWindowTitle("Visualization")
        # Create panel button once and position it during paint
        self.button = QPushButton("Send Target", self)
        self.button.resize(100, 40)
        self.button.clicked.connect(self.on_button_click)

    def update_positioners(self, pids):
        self._positioner_ids = sorted(pids)

    def _drawing_geometry(self):
        panel_x = max(0, self.width() - self.panel_width)
        canvas_width = max(1, panel_x - 2 * self.margin)
        canvas_height = max(1, self.height() - 2 * self.margin)

        center = QPoint(
            self.margin + canvas_width // 2,
            self.margin + canvas_height // 2,
        )

        workspace_radius = self.link_lengths[0] + self.link_lengths[1]
        max_display_radius = max(1, min(canvas_width, canvas_height) // 2)
        scale = min(1.0, max_display_radius / workspace_radius) if workspace_radius else 1.0

        return center, scale, panel_x

    def _offset_to_point(self, center, offset_x, offset_y, scale):
        return QPoint(
            int(round(center.x() + offset_x * scale)),
            int(round(center.y() + offset_y * scale)),
        )

    def _point_to_offset(self, center, point, scale):
        if scale == 0:
            return 0.0, 0.0
        return (point.x() - center.x()) / scale, (point.y() - center.y()) / scale

    def _normalize_for_positioner(self, angle_deg):
        adjusted = float(angle_deg)
        while adjusted < -10.0:
            adjusted += 360.0
        while adjusted > 370.0:
            adjusted -= 360.0
        return adjusted

    def _refresh_button_state(self):
        if self._selected_pid is None:
            self.button.setText("Send Target")
            self.button.setEnabled(False)
            return

        if self._selected_positioner_state == "moving":
            self.button.setText("Moving...")
            self.button.setEnabled(False)
        elif self._selected_positioner_state == "error":
            self.button.setText("Error")
            self.button.setEnabled(False)
        elif not self.validSolutionExists:
            self.button.setText("No Solution")
            self.button.setEnabled(False)
        else:
            self.button.setText("Send Target")
            self.button.setEnabled(True)

    def paintEvent(self, event):
        center, scale, panel_x = self._drawing_geometry()

        if self.target_offset is None:
            self.target_offset = (20.0, 50.0)

        target_point = self._offset_to_point(center, self.target_offset[0], self.target_offset[1], scale)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.white)  # Clear the background

        # Draw the target point
        painter.setPen(Qt.red)
        painter.setBrush(Qt.red)
        painter.drawEllipse(target_point, 5, 5)

        # Draw the annulus representing the reachable workspace
        painter.setBrush(Qt.NoBrush)
        display_short = self.link_lengths[0] * scale
        display_long = self.link_lengths[1] * scale
        inner_radius = abs(display_short - display_long)
        outer_radius = display_short + display_long
        painter.drawEllipse(center, int(round(inner_radius)), int(round(inner_radius)))
        painter.drawEllipse(center, int(round(outer_radius)), int(round(outer_radius)))

        # Calculate inverse kinematics solutions
        target_dx, target_dy = self._point_to_offset(center, target_point, scale)
        solutions = solve_inverse_kinematics(
            target_dx,
            target_dy,
            *self.link_lengths
        )

        self.validSolutionExists = bool(solutions)
        if solutions:
            for theta1_deg, theta2_deg in solutions:
                # Convert angles to radians for drawing
                theta1_rad = math.radians(theta1_deg)
                theta2_rad = math.radians(theta2_deg)

                # Calculate joint positions
                joint1_x = center.x() + display_short * math.cos(theta1_rad)
                joint1_y = center.y() + display_short * math.sin(theta1_rad)

                joint2_x = joint1_x + display_long * math.cos(theta1_rad + theta2_rad)
                joint2_y = joint1_y + display_long * math.sin(theta1_rad + theta2_rad)

                # Draw the links
                painter.setPen(Qt.blue)
                painter.drawLine(center, QPoint(int(round(joint1_x)), int(round(joint1_y))))
                painter.drawLine(
                    QPoint(int(round(joint1_x)), int(round(joint1_y))),
                    QPoint(int(round(joint2_x)), int(round(joint2_y))),
                )

        self.draw_angles_panel(painter, solutions, panel_x)

    def draw_angles_panel(self, painter, solutions, panel_x):
        painter.fillRect(panel_x, 0, self.panel_width, self.height(), Qt.lightGray)

        painter.setPen(Qt.black)
        painter.drawText(panel_x + 12, 28, "IK Angles")

        if not solutions:
            painter.drawText(panel_x + 12, 56, "No solution")
            return

        alpha_1, beta_1 = solutions[0]
        if len(solutions) > 1:
            alpha_2, beta_2 = solutions[1]
        else:
            alpha_2, beta_2 = alpha_1, beta_1

        alpha_1 = self._normalize_for_positioner(alpha_1)
        beta_1 = self._normalize_for_positioner(beta_1)
        alpha_2 = self._normalize_for_positioner(alpha_2)
        beta_2 = self._normalize_for_positioner(beta_2)

        painter.drawText(panel_x + 12, 56, f"alpha: {alpha_1:.2f} deg")
        painter.drawText(panel_x + 12, 112, f"alpha: {alpha_2:.2f} deg")
        painter.drawText(panel_x + 12, 80, f"beta: {beta_1:.2f} deg")
        painter.drawText(panel_x + 12, 136, f"beta: {beta_2:.2f} deg")
        # Position the button inside the panel
        btn_x = panel_x + 12
        btn_y = 160
        self.button.move(btn_x, btn_y)
        self.button.show()

    def on_button_click(self):
        if self._selected_pid is None:
            return

        center, scale, _ = self._drawing_geometry()
        target_dx, target_dy = self._point_to_offset(center, self._offset_to_point(center, self.target_offset[0], self.target_offset[1], scale), scale)
        solutions = solve_inverse_kinematics(
            target_dx,
            target_dy,
            *self.link_lengths
        )
        if solutions: # later on we can make a decision on which solution to use based on some criteria (e.g. closest to current position)
            alpha_1, beta_1 = solutions[0]
            alpha_1 = self._normalize_for_positioner(alpha_1)
            beta_1 = self._normalize_for_positioner(beta_1)
            self.move_requested.emit(self._selected_pid, alpha_1, beta_1)
            self.validSolutionExists = True
        else:
            self.validSolutionExists = False
            print("No valid IK solution found for the target point.")   

        self._refresh_button_state()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        click = event.position()
        _, _, panel_x = self._drawing_geometry()
        if click.x() >= panel_x:
            return

        center, scale, _ = self._drawing_geometry()
        self.target_offset = self._point_to_offset(center, click.toPoint(), scale)

        # Recompute IK for the clicked target and cache whether a valid solution exists.
        target_dx, target_dy = self.target_offset
        solutions = solve_inverse_kinematics(
            target_dx,
            target_dy,
            *self.link_lengths
        )
        self.validSolutionExists = bool(solutions)
        self._refresh_button_state()

        self.update()
    def update_display(self, positioners_dict, selected_pid=None):
        self._selected_pid = selected_pid
        #if moving, make the button say "Moving..." and disable it, otherwise say "Send Target" and enable it
        if self._selected_pid is not None:
            self._selected_positioner_state = positioners_dict.get(self._selected_pid, {}).get("state", "ready")
        else:
            self._selected_positioner_state = "ready"

        self._refresh_button_state()
        

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = View2D()
    window.show()
    sys.exit(app.exec())