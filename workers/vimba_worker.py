"""Background thread for streaming frames from a Vimba camera."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal, Slot

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
	connection_status = Signal(bool)

	def __init__(self, parent=None):
		super().__init__(parent)
		self._running = False
		self._shutdown = False

	@Slot(int)
	def set_exposure(self, exposure_us: int):
		print(f"VimbaWorker stub: setting exposure to {exposure_us} µs")
		# TODO: implement actual vmbpy camera exposure setting here

	@Slot(float)
	def set_gain(self, gain_db: float):
		print(f"VimbaWorker stub: setting gain to {gain_db} dB")
		# TODO: implement actual vmbpy camera gain setting here

	def run(self):
		if _VMBPY_IMPORT_ERROR is not None:
			self.error.emit(
				"Vimba camera support is unavailable: install the vmbpy package and the matching Vimba X runtime."
			)
			self.connection_status.emit(False)
			return

		self._running = True
		try:
			with VmbSystem.get_instance() as vmb:
				cameras = vmb.get_all_cameras()
				if not cameras:
					self.error.emit("No Vimba cameras found.")
					self.connection_status.emit(False)
					return

				with cameras[0] as cam:
					try:
						cam.set_pixel_format(PixelFormat.Bgr8)
					except Exception:
						cam.set_pixel_format(PixelFormat.Mono8)

					self.connection_status.emit(True)
					while self._running and not self.isInterruptionRequested():
						frame = cam.get_frame()
						image = frame.as_opencv_image().copy()
						self.frame_ready.emit(image)
						# print("VimbaWorker: Frame emitted")
		except Exception as exc:
			self.error.emit(str(exc))
			self.connection_status.emit(False)
		finally:
			self._running = False
			if not self._shutdown:
				self.connection_status.emit(False)

	def stop(self):
		self._shutdown = True
		self._running = False
		self.requestInterruption()
		self.wait()