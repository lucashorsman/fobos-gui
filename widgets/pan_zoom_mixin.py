from PySide6.QtCore import QPointF, Qt

class PanZoomMixin:
    def init_pan_zoom(self):
        self._scale = 1.0
        self._offset = QPointF(0, 0)
        self._pan_start = None
        self._pan_offset_start = None

    def apply_wheel_zoom(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15

        cursor_pos = QPointF(event.position())
        img_point = (cursor_pos - self._offset) / self._scale

        self._scale *= factor
        self._scale = max(0.1, min(self._scale, 20.0))

        self._offset = cursor_pos - img_point * self._scale

    def start_pan(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_start = QPointF(event.position())
            self._pan_offset_start = QPointF(self._offset)
            return True
        return False

    def do_pan(self, event):
        if self._pan_start is not None:
            delta = QPointF(event.position()) - self._pan_start
            self._offset = self._pan_offset_start + delta
            return True
        return False

    def end_pan(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_start = None
            return True
        return False

    def get_physical_click_coords(self, event):
        click = event.position()
        phys_x = (click.x() - self._offset.x()) / self._scale
        phys_y = (click.y() - self._offset.y()) / self._scale
        return phys_x, phys_y
