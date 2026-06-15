import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QWidget

from helpers.annulus import solve_inverse_kinematics
import math
from helpers.constants import SHORT_ARM_LENGTH, LONG_ARM_LENGTH


class View2D(QWidget):
    def __init__(self):
        super().__init__()
        self.panel_width = 170
        self.margin = 24
        self.link_lengths = (SHORT_ARM_LENGTH, LONG_ARM_LENGTH)
        self.target_offset = None

        self.setMinimumSize(400, 300)
        self.setWindowTitle("Visualization")

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

        painter.drawText(panel_x + 12, 56, f"alpha: {alpha_1:.2f} deg")
        painter.drawText(panel_x + 12, 112, f"alpha: {alpha_2:.2f} deg")
        painter.drawText(panel_x + 12, 80, f"beta: {beta_1:.2f} deg")
        painter.drawText(panel_x + 12, 136, f"beta: {beta_2:.2f} deg")

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        click = event.position()
        _, _, panel_x = self._drawing_geometry()
        if click.x() >= panel_x:
            return

        center, scale, _ = self._drawing_geometry()
        self.target_offset = self._point_to_offset(center, click.toPoint(), scale)

        self.update()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = View2D()
    window.show()
    sys.exit(app.exec())