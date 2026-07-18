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
		self._cam = None  # set while camera context is open

	@Slot(int)
	def set_exposure(self, exposure_us: int):
		if self._cam is None:
			return
		try:
			self._cam.ExposureTime.set(float(exposure_us))
		except Exception:
			try:
				self._cam.ExposureTimeAbs.set(float(exposure_us))
			except Exception as e:
				print(f"VimbaWorker: failed to set exposure: {e}")

	@Slot(float)
	def set_gain(self, gain_db: float):
		if self._cam is None:
			return
		try:
			self._cam.Gain.set(gain_db)
		except Exception:
			try:
				self._cam.GainRaw.set(gain_db)
			except Exception as e:
				print(f"VimbaWorker: failed to set gain: {e}")

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

					# Disable auto modes so slider values take effect immediately.
					for feat_name in ("ExposureAuto", "GainAuto"):
						try:
							getattr(cam, feat_name).set("Off")
						except Exception:
							pass

					self._cam = cam
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
			self._cam = None
			self._running = False
			if not self._shutdown:
				self.connection_status.emit(False)

	def stop(self):
		self._shutdown = True
		self._running = False
		self.requestInterruption()
		self.wait()