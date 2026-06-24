import math
from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QPen, QColor, QPainterPath
from helpers.constants import SHORT_ARM_LENGTH, LONG_ARM_LENGTH

def draw_positioner(painter, pid, pos_info, is_selected, draw_arms=True):
    inner_radius = abs(SHORT_ARM_LENGTH - LONG_ARM_LENGTH)
    outer_radius = SHORT_ARM_LENGTH + LONG_ARM_LENGTH

    cx, cy = pos_info.get('center', (0.0, 0.0))
    
    painter.save()
    painter.translate(cx, cy)

    if is_selected:
        pen = QPen(Qt.green)
        pen.setWidthF(0.5)
        pen.setCosmetic(True)
        painter.setPen(pen)

        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), outer_radius, outer_radius)
        path.addEllipse(QPointF(0, 0), inner_radius, inner_radius)
        painter.setBrush(QColor(0, 255, 0, 50))
        painter.drawPath(path)
    else:
        pen = QPen(QColor(0, 150, 0, 100))
        pen.setWidthF(0.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawEllipse(QPointF(0, 0), inner_radius, inner_radius)
        painter.drawEllipse(QPointF(0, 0), outer_radius, outer_radius)

    if draw_arms:
        alpha_deg = pos_info.get('alpha', 0.0)
        beta_deg = pos_info.get('beta', 0.0)
        
        alpha_rad = math.radians(alpha_deg)
        beta_rad = math.radians(alpha_deg + beta_deg) 
        
        joint_x = SHORT_ARM_LENGTH * math.cos(alpha_rad)
        joint_y = SHORT_ARM_LENGTH * math.sin(alpha_rad)
        
        end_x = joint_x + LONG_ARM_LENGTH * math.cos(beta_rad)
        end_y = joint_y + LONG_ARM_LENGTH * math.sin(beta_rad)
        
        arm_pen = QPen(Qt.yellow if is_selected else Qt.gray)
        arm_pen.setWidthF(1.0)
        arm_pen.setCosmetic(True)
        painter.setPen(arm_pen)
        
        painter.drawLine(QPointF(0, 0), QPointF(joint_x, joint_y))
        painter.drawLine(QPointF(joint_x, joint_y), QPointF(end_x, end_y))

    queued_target = pos_info.get('queued_target')
    if queued_target is not None:
        queued_alpha_deg, queued_beta_deg = queued_target
        queued_alpha_rad = math.radians(queued_alpha_deg)
        queued_beta_rad = math.radians(queued_alpha_deg + queued_beta_deg) 
        
        queued_joint_x = SHORT_ARM_LENGTH * math.cos(queued_alpha_rad)
        queued_joint_y = SHORT_ARM_LENGTH * math.sin(queued_alpha_rad)
        
        queued_end_x = queued_joint_x + LONG_ARM_LENGTH * math.cos(queued_beta_rad)
        queued_end_y = queued_joint_y + LONG_ARM_LENGTH * math.sin(queued_beta_rad)
        
        queued_arm_pen = QPen(Qt.cyan)
        queued_arm_pen.setWidthF(1.0)
        queued_arm_pen.setCosmetic(True)
        queued_arm_pen.setStyle(Qt.DashLine)
        painter.setPen(queued_arm_pen)
        
        painter.drawLine(QPointF(0, 0), QPointF(queued_joint_x, queued_joint_y))
        painter.drawLine(QPointF(queued_joint_x, queued_joint_y), QPointF(queued_end_x, queued_end_y))

    # Draw center point
    painter.setPen(Qt.white)
    painter.setBrush(Qt.white)
    painter.drawEllipse(QPointF(0, 0), 2, 2)

    # Draw PID text
    font = painter.font()
    font.setPixelSize(40)
    painter.setFont(font)
    if is_selected:
        painter.setPen(Qt.white)
    else:
        painter.setPen(QColor(200, 200, 200, 150))
    rect = QRectF(-50, -50, 100, 100)
    painter.drawText(rect, Qt.AlignCenter, str(pid))

    painter.restore()

def draw_coordinate_grid(painter, rect, spacing=100.0):
    """
    Draws a coordinate grid within the given physical rectangle.
    rect: QRectF indicating the visible physical bounds.
    spacing: Distance between grid lines.
    """
    painter.save()
    
    start_x = math.floor(rect.left() / spacing)
    end_x = math.ceil(rect.right() / spacing)
    start_y = math.floor(rect.top() / spacing)
    end_y = math.ceil(rect.bottom() / spacing)

    grid_pen = QPen(QColor(255, 255, 255, 40))
    grid_pen.setCosmetic(True)
    
    axis_pen = QPen(QColor(255, 255, 255, 120))
    axis_pen.setWidthF(2.0)
    axis_pen.setCosmetic(True)

    for i in range(start_x, end_x + 1):
        x = i * spacing
        painter.setPen(axis_pen if i == 0 else grid_pen)
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

    for i in range(start_y, end_y + 1):
        y = i * spacing
        painter.setPen(axis_pen if i == 0 else grid_pen)
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        
    painter.restore()
