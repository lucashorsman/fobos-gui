"""Background thread for streaming frames from a Vimba camera."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

_VMBPY_IMPORT_ERROR = None

try:
	from vmbpy import PixelFormat, VmbSystem  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - import/runtime specific
	_VMBPY_IMPORT_ERROR = exc
	PixelFormat = None
	VmbSystem = None


class VimbaWorker(QThread):
	frame_ready = Signal(object)
	error = Signal(str)

	def __init__(self, parent=None):
		super().__init__(parent)
		self._running = False

	def run(self):
		if _VMBPY_IMPORT_ERROR is not None:
			self.error.emit(
				"Vimba camera support is unavailable: install the vmbpy package and the matching Vimba X runtime."
			)
			return

		self._running = True
		try:
			with VmbSystem.get_instance() as vmb:
				cameras = vmb.get_all_cameras()
				if not cameras:
					self.error.emit("No Vimba cameras found.")
					return

				with cameras[0] as cam:
					try:
						cam.set_pixel_format(PixelFormat.Bgr8)
					except Exception:
						cam.set_pixel_format(PixelFormat.Mono8)

					while self._running and not self.isInterruptionRequested():
						frame = cam.get_frame()
						image = frame.as_opencv_image().copy()
						self.frame_ready.emit(image)
						print("VimbaWorker: Frame emitted")
		except Exception as exc:
			self.error.emit(str(exc))
		finally:
			self._running = False

	def stop(self):
		self._running = False
		self.requestInterruption()
		self.wait()