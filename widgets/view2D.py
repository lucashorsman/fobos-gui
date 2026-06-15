from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QPushButton, QComboBox)
from PySide6.QtCore import Signal
from PySide6.QtGui import QDoubleValidator
#this will show the 2d view of the positioners with the annulus. if the user clicks (and the pos is valid)
#then we will trigger the positioner to move by calculating the alpha and beta from the 2d (x,y) click position.


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
        self.setup_ui()
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.setWindowTitle("Visualization")
        
        self.panel_width = 170
        #set the lengths of the positioner links
        self.link_lengths = (SHORT_ARM_LENGTH, LONG_ARM_LENGTH)

        drawing_width = self.width() - self.panel_width
        self.center = QPoint(drawing_width // 2, self.height() // 2)
        self.target_point = QPoint(self.center.x() + 20, self.center.y() + 50)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.white)  # Clear the background

        # Draw the target point
        painter.setPen(Qt.red)
        painter.setBrush(Qt.red)
        painter.drawEllipse(self.target_point, 5, 5)
        # Draw the annulus representing the reachable workspace
        painter.setBrush(Qt.NoBrush)
        inner_radius = abs(self.link_lengths[0] - self.link_lengths[1])
        painter.drawEllipse(self.center, inner_radius, inner_radius)
        painter.drawEllipse(self.center, self.link_lengths[0] + self.link_lengths[1], self.link_lengths[0] + self.link_lengths[1])

        # Calculate inverse kinematics solutions
        solutions = solve_inverse_kinematics(
            self.target_point.x() - self.center.x(),
            self.target_point.y() - self.center.y(),
            *self.link_lengths
        )

        if solutions:
            for theta1_deg, theta2_deg in solutions:
                # Convert angles to radians for drawing
                theta1_rad = math.radians(theta1_deg)
                theta2_rad = math.radians(theta2_deg)

                # Calculate joint positions
                joint1_x = self.center.x() + self.link_lengths[0] * math.cos(theta1_rad)
                joint1_y = self.center.y() + self.link_lengths[0] * math.sin(theta1_rad)

                joint2_x = joint1_x + self.link_lengths[1] * math.cos(theta1_rad + theta2_rad)
                joint2_y = joint1_y + self.link_lengths[1] * math.sin(theta1_rad + theta2_rad)

                # Draw the links
                painter.setPen(Qt.blue)
                painter.drawLine(self.center, QPoint(joint1_x, joint1_y))
                painter.drawLine(QPoint(joint1_x, joint1_y), QPoint(joint2_x, joint2_y))

        self.draw_angles_panel(painter, solutions)

    def draw_angles_panel(self, painter, solutions):
        panel_x = self.width() - self.panel_width
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
        self.target_point = QPoint(int(round(click.x())), int(round(click.y())))

        self.update()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())