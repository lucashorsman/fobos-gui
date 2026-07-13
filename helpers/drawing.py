import math
from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QPen, QColor, QPainterPath
from helpers.constants import GRID_SPACING, SHORT_ARM_LENGTH, LONG_ARM_LENGTH

def draw_positioner(painter, pid, pos_info, is_selected, draw_arms=True):
    inner_radius = abs(SHORT_ARM_LENGTH - LONG_ARM_LENGTH)
    outer_radius = SHORT_ARM_LENGTH + LONG_ARM_LENGTH

    cx, cy = pos_info.get('center', (0.0, 0.0))
    
    painter.save()
    painter.translate(cx, cy)
    # The physical hardware's local kinematic X and Y axes are inverted relative to the global axes.
    #  this is setup-dependent
    painter.scale(-1, -1)

    if is_selected:
        pen = QPen(Qt.green)
        pen.setWidthF(1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)

        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), outer_radius, outer_radius)
        path.addEllipse(QPointF(0, 0), inner_radius, inner_radius)
        painter.setBrush(QColor(0, 255, 0, 50))
        painter.drawPath(path)
    else:
        pen = QPen(QColor(0, 150, 0, 100))
        pen.setWidthF(1.5)
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
        arm_pen.setWidthF(3.0)
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
        
        queued_arm_pen = QPen(QColor("#3b82f6"))
        queued_arm_pen.setWidthF(3.0)
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
        
    painter.save()
    t = painter.transform()
    scale_x = -1 if t.m11() < 0 else 1
    scale_y = -1 if t.m22() < 0 else 1
    if scale_x != 1 or scale_y != 1:
        painter.scale(scale_x, scale_y)
    rect = QRectF(-50, -50, 100, 100)
    painter.drawText(rect, Qt.AlignCenter, str(pid))
    painter.restore()

    painter.restore()

def draw_coordinate_grid(painter, rect, spacing=GRID_SPACING):
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

    # Safety limits to prevent infinite loops from bad projections (e.g. bowtie)
    MAX_LINES = 10000
    if (end_x - start_x) > MAX_LINES or (end_y - start_y) > MAX_LINES:
        # Just draw a basic crosshair instead of millions of lines
        start_x, end_x = 0, 0
        start_y, end_y = 0, 0

    grid_pen = QPen(QColor(255, 255, 255, 40))
    grid_pen.setCosmetic(True)
    
    axis_pen = QPen(QColor(255, 255, 255, 120))
    axis_pen.setWidthF(2.0)
    axis_pen.setCosmetic(True)

    font = painter.font()
    font.setPixelSize(int(spacing * 0.3) if spacing > 10 else 12)
    painter.setFont(font)
    text_pen = QPen(QColor(255, 255, 255, 200))

    scale_factor = abs(painter.transform().m11())
    screen_spacing = spacing * scale_factor
    raw_step = 150 / screen_spacing if screen_spacing > 0 else 2
    
    def get_nice_step(s):
        if s <= 2: return 2
        if s <= 5: return 5
        if s <= 10: return 10
        if s <= 20: return 20
        if s <= 50: return 50
        return int(math.ceil(s / 50.0)) * 50
        
    step = get_nice_step(raw_step)

    def draw_axis_text(text, px, py, align=Qt.AlignCenter, x_offset=0, y_offset=0):
        painter.save()
        painter.translate(px, py)
        if painter.transform().m22() < 0:
            painter.scale(1, -1)
        painter.setPen(text_pen)
        
        rect_w = spacing * 2
        rect_h = spacing
        tr = QRectF(-rect_w/2 + x_offset, -rect_h/2 + y_offset, rect_w, rect_h)
        painter.drawText(tr, align, text)
        painter.restore()

    for i in range(start_x, end_x + 1):
        x = i * spacing
        painter.setPen(axis_pen if i == 0 else grid_pen)
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        if i != 0 and i % step == 0:
            draw_axis_text(str(int(x)), x, 0, align=Qt.AlignTop | Qt.AlignHCenter, y_offset=5)

    for i in range(start_y, end_y + 1):
        y = i * spacing
        painter.setPen(axis_pen if i == 0 else grid_pen)
        painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if i != 0 and i % step == 0:
            draw_axis_text(str(int(y)), 0, y, align=Qt.AlignRight | Qt.AlignVCenter, x_offset=-5)
            
    # Draw +x and +y labels
    if end_x > 0:
        draw_axis_text("+x", rect.right() - spacing*0.5, 0, align=Qt.AlignBottom | Qt.AlignHCenter, y_offset=-5)
    if end_y > 0:
        draw_axis_text("+y", 0, rect.bottom() - spacing*0.5, align=Qt.AlignLeft | Qt.AlignVCenter, x_offset=5)

    painter.restore()
