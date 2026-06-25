import numpy as np
from skimage.transform import ProjectiveTransform
from PySide6.QtGui import QTransform
from typing import Optional, List, Tuple


class PositionerProjection:
    def __init__(self):
        self._tform: Optional[ProjectiveTransform] = None

    def calibrate(self, physical_pts: List[Tuple[float, float]], camera_pts: List[Tuple[float, float]]):
        """
        Estimate the transformation from physical positioner coordinates to camera pixel coordinates.
        Requires at least 4 point pairs.
        """
        src = np.array(physical_pts)
        dst = np.array(camera_pts)
        self._tform = ProjectiveTransform()
        if not self._tform.estimate(src, dst):
            self._tform = None
            raise RuntimeError("Failed to estimate transformation.")

    def reset(self):
        self._tform = None

    @property
    def is_calibrated(self) -> bool:
        return self._tform is not None

    def physical_to_camera(self, x: float, y: float) -> Tuple[float, float]:
        if not self.is_calibrated:
            return x, y
        pt = np.array([[x, y]])
        res = self._tform(pt)
        return float(res[0, 0]), float(res[0, 1])

    def camera_to_physical(self, x: float, y: float) -> Tuple[float, float]:
        if not self.is_calibrated:
            return x, y
        pt = np.array([[x, y]])
        res = self._tform.inverse(pt)
        return float(res[0, 0]), float(res[0, 1])

    def get_qtransform(self) -> QTransform:
        """
        Returns a QTransform that maps physical coordinates to camera pixel coordinates,
        ready to be applied to a QPainter.
        """
        if not self.is_calibrated:
            return QTransform()

        T = self._tform.params
        # skimage uses column vectors, QTransform uses row vectors
        return QTransform(
            T[0, 0], T[1, 0], T[2, 0],
            T[0, 1], T[1, 1], T[2, 1],
            T[0, 2], T[1, 2], T[2, 2]
        )
