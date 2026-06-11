#worker for managing the vimba camera
try:
	from vmbpy import *
except Exception as exc:
	_VMBPY_IMPORT_ERROR = exc

	class VimbaWorkerError(RuntimeError):
		pass

	def _raise_vmbpy_import_error() -> None:
		raise VimbaWorkerError(
			"Vimba camera support is unavailable: the installed VmbC runtime does not match the vmbpy package. "
			"Install the Vimba X SDK version expected by vmbpy 1.2.1 (VmbC 1.3.0), or update the package/runtime pair."
		) from _VMBPY_IMPORT_ERROR
