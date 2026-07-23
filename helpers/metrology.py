"""Metrology verification helpers — blob detection, global fiber matching,
and laser mapping interpolation.

Used by the Verify feature to confirm positioners reached their commanded
targets by detecting laser spots in camera frames and comparing measured
positions against expected positions derived from the laser mapping.
"""

from __future__ import annotations

import json
import math
import os
from typing import Optional

import numpy as np
from scipy import ndimage
from scipy.interpolate import griddata
from scipy.optimize import linear_sum_assignment

from helpers.annulus import solve_forward_kinematics
from helpers.constants import (
    SHORT_ARM_LENGTH_MM,
    LONG_ARM_LENGTH_MM,
    VERIFY_ROI_SIZE,
    VERIFY_TOLERANCE_PX,
)


# ---------------------------------------------------------------------------
# Blob detection
# ---------------------------------------------------------------------------

def detect_all_blobs(ref_frame, check_frame, thresh, min_pixels=3):
    """Full-frame diff + threshold + connected components.

    Returns a list of blob dicts: ``{'centroid': (x, y), 'flux': float,
    'peak_flux': float, 'size': int}``.

    Uses vectorized ndimage calls (center_of_mass, sum, maximum) so that
    cost scales with the *number* of surviving blobs, not with the product
    of blob-count × image-size.
    """
    diff = check_frame.astype(np.float32) - ref_frame.astype(np.float32)
    diff[diff < 0] = 0
    mask = diff > thresh

    labeled, n = ndimage.label(mask)
    blobs = []
    if n == 0:
        return blobs

    sizes = ndimage.sum(mask, labeled, index=range(1, n + 1))
    survivors = [i for i, size in enumerate(sizes, start=1) if size >= min_pixels]
    if not survivors:
        return blobs

    # Vectorized centroid + flux computation for all surviving blobs.
    centroids = ndimage.center_of_mass(diff, labeled, survivors)
    total_fluxes = ndimage.sum(diff, labeled, survivors)
    peak_fluxes = ndimage.maximum(diff, labeled, survivors)
    sizes_by_label = {i: int(s) for i, s in zip(range(1, n + 1), sizes)}

    # Scipy ndimage functions return a list when index is a list,
    # even if it only contains one element. No need to wrap.

    for label_id, (cy, cx), tflux, pflux in zip(
        survivors, centroids, total_fluxes, peak_fluxes
    ):
        blobs.append({
            "centroid": (float(cx), float(cy)),
            "flux": float(tflux),
            "peak_flux": float(pflux),
            "size": sizes_by_label[label_id],
        })
    return blobs


# ---------------------------------------------------------------------------
# Global (collision-safe) fiber verification
# ---------------------------------------------------------------------------

def verify_fibers_global(
    ref_frame,
    check_frame,
    expected_positions,
    roi_size=VERIFY_ROI_SIZE,
    thresh=15.0,
    tolerance_px=VERIFY_TOLERANCE_PX,
    min_pixels=3,
):
    """Collision-safe verification: detect all blobs once, then assign
    fibers to blobs one-to-one via the Hungarian algorithm, disallowing
    any pairing farther apart than *roi_size*.

    Parameters
    ----------
    ref_frame : ndarray
        Background frame (laser OFF), grayscale float32 or uint8.
    check_frame : ndarray
        Check frame (laser ON), same dtype/shape as ref_frame.
    expected_positions : dict
        ``{fiber_id: (expected_x, expected_y)}`` in full-frame pixel coords.
    roi_size : int
        Maximum distance (px) from expected position to search for a blob.
    thresh : float
        Minimum intensity difference to count as signal.
    tolerance_px : float
        Pass/fail threshold — a fiber passes if its measured position is
        within this many pixels of the expected position.
    min_pixels : int
        Minimum blob size to consider (filters noise).

    Returns
    -------
    results : dict
        ``{fiber_id: result_dict}`` with keys: expected_px, measured_px,
        error_px, flux, found, pass, roi.
    unmatched_blobs : list
        Blobs detected but not claimed by any fiber (stray light, ghost, etc.).
    """
    blobs = detect_all_blobs(ref_frame, check_frame, thresh, min_pixels)
    fids = list(expected_positions.keys())

    results = {
        fid: {
            "expected_px": expected_positions[fid],
            "measured_px": None,
            "error_px": None,
            "flux": 0.0,
            "found": False,
            "pass": False,
            "roi": (
                expected_positions[fid][0] - roi_size,
                expected_positions[fid][1] - roi_size,
                expected_positions[fid][0] + roi_size,
                expected_positions[fid][1] + roi_size,
            ),
        }
        for fid in fids
    }

    if not blobs or not fids:
        return results, blobs

    n_fibers, n_blobs = len(fids), len(blobs)
    big_cost = roi_size * 100.0
    size = max(n_fibers, n_blobs)
    cost = np.full((size, size), big_cost, dtype=np.float64)

    for i, fid in enumerate(fids):
        ex, ey = expected_positions[fid]
        for j, blob in enumerate(blobs):
            bx, by = blob["centroid"]
            dist = float(np.hypot(bx - ex, by - ey))
            if dist <= roi_size:
                cost[i, j] = dist

    row_idx, col_idx = linear_sum_assignment(cost)

    claimed_blob_idxs = set()
    for i, j in zip(row_idx, col_idx):
        if i >= n_fibers or j >= n_blobs:
            continue
        if cost[i, j] >= big_cost:
            continue
        fid = fids[i]
        blob = blobs[j]
        bx, by = blob["centroid"]
        ex, ey = expected_positions[fid]
        error_px = float(np.hypot(bx - ex, by - ey))
        results[fid].update({
            "measured_px": (bx, by),
            "error_px": error_px,
            "flux": blob["flux"],
            "found": True,
            "pass": error_px <= tolerance_px,
        })
        claimed_blob_idxs.add(j)

    unmatched_blobs = [b for j, b in enumerate(blobs) if j not in claimed_blob_idxs]
    return results, unmatched_blobs


# ---------------------------------------------------------------------------
# Laser mapping interpolator
# ---------------------------------------------------------------------------

class LaserMappingInterpolator:
    """Wraps ``laser_mapping.json`` and provides interpolated pixel
    coordinates for arbitrary (alpha, beta) angles.

    Uses ``scipy.interpolate.griddata`` (linear) on the empirically measured
    ``(alpha, beta) → (pixel_x, pixel_y)`` scatter data from the metrology
    sweep.

    Coverage notes
    --------------
    The current sweep uses 3α × 5β = 15 ground-truth points per positioner.
    Mathematical analysis (piecewise-linear error bound on the FK function's
    second derivatives) shows:

        ============================================
        Grid         Points  Worst-case error (px)
        --------------------------------------------
        3α × 5β       15       ~60
        6α × 6β       36       ~22
        9α × 9β       81       ~10
        12α × 12β    144        ~6
        ============================================

    A 6×6 (36-point) resweep is the minimum before Verify is considered
    reliable. A 9×9 (81-point) sweep is recommended for production use.

    Fallback: when the requested (alpha, beta) is outside the convex hull of
    the sampled grid (scipy returns NaN), the interpolator falls back to a
    kinematic projection via forward kinematics + PositionerProjection.
    """

    def __init__(
        self,
        mapping_path: str,
        projection=None,
        phys_centers: Optional[dict] = None,
    ):
        """
        Parameters
        ----------
        mapping_path : str
            Path to ``laser_mapping.json``.
        projection : PositionerProjection, optional
            Calibrated projection for the kinematic fallback.  If None,
            the fallback is disabled and NaN-extrapolation returns None.
        phys_centers : dict, optional
            ``{pid_int: (cx_mm, cy_mm)}`` from ``positioner_centers.json``.
            Required for the kinematic fallback.
        """
        self._projection = projection
        self._phys_centers = phys_centers or {}

        # Per-PID data for griddata interpolation:
        #   _grid_points[pid] = np.ndarray of shape (N, 2) — (alpha, beta) in degrees
        #   _grid_values_x[pid] = np.ndarray of shape (N,)  — pixel X
        #   _grid_values_y[pid] = np.ndarray of shape (N,)  — pixel Y
        self._grid_points: dict[int, np.ndarray] = {}
        self._grid_values_x: dict[int, np.ndarray] = {}
        self._grid_values_y: dict[int, np.ndarray] = {}

        self._load(mapping_path)

    @property
    def is_loaded(self) -> bool:
        return len(self._grid_points) > 0

    @property
    def positioner_ids(self) -> list[int]:
        return list(self._grid_points.keys())

    def _load(self, path: str):
        if not os.path.isfile(path):
            print(f"LaserMappingInterpolator: {path} not found — verify disabled")
            return

        with open(path, "r") as f:
            raw = json.load(f)

        for pid_str, entries in raw.items():
            pid = int(pid_str)
            points = []
            vals_x = []
            vals_y = []
            for ab_key, (px, py) in entries.items():
                alpha, beta = map(float, ab_key.split(","))
                points.append((alpha, beta))
                vals_x.append(px)
                vals_y.append(py)
            self._grid_points[pid] = np.array(points)
            self._grid_values_x[pid] = np.array(vals_x)
            self._grid_values_y[pid] = np.array(vals_y)

        print(
            f"LaserMappingInterpolator: loaded {len(self._grid_points)} "
            f"positioner(s), "
            + ", ".join(
                f"PID {pid}: {len(pts)} pts"
                for pid, pts in self._grid_points.items()
            )
        )

    def get_expected_pixel(
        self, pid: int, alpha: float, beta: float
    ) -> tuple[float, float] | None:
        """Return the interpolated (pixel_x, pixel_y) for the given pose.

        Falls back to kinematic projection if the point is outside the
        convex hull of the sampled grid (griddata returns NaN).
        Returns None if no data exists for this PID and no fallback is
        available.
        """
        if pid in self._grid_points:
            query = np.array([[alpha, beta]])
            px = griddata(
                self._grid_points[pid],
                self._grid_values_x[pid],
                query,
                method="linear",
            )[0]
            py = griddata(
                self._grid_points[pid],
                self._grid_values_y[pid],
                query,
                method="linear",
            )[0]
            if not (np.isnan(px) or np.isnan(py)):
                return (float(px), float(py))
            # Fall through to kinematic fallback

        return self._kinematic_fallback(pid, alpha, beta)

    def _kinematic_fallback(
        self, pid: int, alpha: float, beta: float
    ) -> tuple[float, float] | None:
        """Use FK + camera projection as a best-effort fallback.

        Less accurate than the empirical mapping (doesn't account for fiber
        offsets or mechanical flexure), but prevents hard failure when the
        requested angle is outside the interpolation domain.
        """
        print(
            f"LaserMappingInterpolator: WARNING - PID {pid} at "
            f"(α={alpha:.1f}°, β={beta:.1f}°) is outside the metrology sweep "
            f"hull. Using kinematic fallback."
        )
        if self._projection is None or not self._projection.is_calibrated:
            return None
        if pid not in self._phys_centers:
            return None

        cx, cy = self._phys_centers[pid]
        tip_x, tip_y = solve_forward_kinematics(
            alpha, beta, cx, cy, SHORT_ARM_LENGTH_MM, LONG_ARM_LENGTH_MM
        )
        cam_x, cam_y = self._projection.physical_to_camera(tip_x, tip_y)

        # Convert from centered Cartesian camera coords to top-left image coords.
        # The laser_mapping.json values are in top-left pixel coords (as produced
        # by analyze_sweep.py: cx_local + x1, cy_local + y1), so the fallback
        # must also produce top-left coords.
        #
        # The projection returns centered Cartesian coords (origin at image center,
        # Y-up).  analyze_sweep.py converts to top-left via:
        #   top_left_x = cam_x + img_w / 2
        #   top_left_y = -cam_y + img_h / 2
        #
        # We use the same image dimensions as the Vimba camera (2448 × 2050).
        # TODO: read actual image dimensions from the camera worker instead of
        # hardcoding.  For now this matches the sweep capture resolution.
        img_w, img_h = 2448, 2050
        tl_x = cam_x + img_w / 2.0
        tl_y = -cam_y + img_h / 2.0
        return (tl_x, tl_y)
