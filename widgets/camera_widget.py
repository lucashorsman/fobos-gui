"""Widget for displaying live Vimba camera frames."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Slot
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget


class CameraWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = None
        self._image = None
        self.setMinimumSize(400, 300)
        self.setWindowTitle("Camera View")

    @Slot(object)
    def update_frame(self, frame):
        self._frame = frame.copy() if hasattr(frame, "copy") else frame
        self._image = self._frame_to_qimage(self._frame)
        self.update()
        # print("CameraWidget: Frame updated and widget repainted")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if self._image is None:
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignCenter, "Waiting for camera frame")
            return

        available = self.rect().adjusted(8, 8, -8, -8)
        scaled = self._image.scaled(available.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = available.x() + (available.width() - scaled.width()) // 2
        y = available.y() + (available.height() - scaled.height()) // 2
        painter.drawImage(QPoint(x, y), scaled)

    def _frame_to_qimage(self, frame):
        if frame is None:
            return None

        if frame.ndim == 2:
            height, width = frame.shape
            bytes_per_line = width
            return QImage(frame.data, width, height, bytes_per_line, QImage.Format_Grayscale8).copy()

        if frame.ndim == 3:
            if frame.shape[2] == 3:
                height, width, _ = frame.shape
                bytes_per_line = width * 3
                return QImage(frame.data, width, height, bytes_per_line, QImage.Format_BGR888).copy()
            elif frame.shape[2] == 1:
                height, width, _ = frame.shape
                bytes_per_line = width
                return QImage(frame.data, width, height, bytes_per_line, QImage.Format_Grayscale8).copy()

        return None