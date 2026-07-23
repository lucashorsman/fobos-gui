"""Utilities for persisting camera-to-physical calibration data.

Calibration is stored as a JSON file in the project root (calibration.json).
The file records the four physical reference point coordinates and the four
corresponding camera pixel coordinates collected during the calibration workflow.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional, Tuple

# Default path: config directory (one level above this helpers/ directory)
DEFAULT_CALIBRATION_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "calibration.json")
)


def save_calibration(
    physical_pts: List[Tuple[float, float]],
    camera_pts: List[Tuple[float, float]],
    path: str = DEFAULT_CALIBRATION_PATH,
) -> None:
    """Persist calibration point pairs to a JSON file.

    Args:
        physical_pts: Four (x, y) coordinates in physical/positioner space.
        camera_pts:   Corresponding four (x, y) coordinates in camera pixels.
        path:         Destination file path (defaults to project root).
    """
    data = {
        "physical_pts": [list(p) for p in physical_pts],
        "camera_pts": [list(p) for p in camera_pts],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_calibration(
    path: str = DEFAULT_CALIBRATION_PATH,
) -> Optional[Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]]:
    """Load calibration point pairs from a JSON file.

    Returns:
        (physical_pts, camera_pts) if the file exists and is valid, else None.
    """
    try:
        with open(path, "r") as f:
            data = json.load(f)
        physical_pts = [tuple(p) for p in data["physical_pts"]]
        camera_pts = [tuple(p) for p in data["camera_pts"]]
        if len(physical_pts) == 4 and len(camera_pts) == 4:
            return physical_pts, camera_pts
    except Exception:
        pass
    return None


def is_valid_calibration_quad(pts: List[Tuple[float, float]]) -> bool:
    """Check that 4 camera points (in TL, TR, BL, BR collection order) form a
    non-degenerate quadrilateral.

    The shoelace formula is applied on the properly-wound polygon (TL, TR, BR, BL).
    Returns False if the enclosed area is less than 10,000 square pixels — a
    threshold that catches accidentally near-collinear or duplicate points.

    Args:
        pts: Four (x, y) pixel coordinates in TL, TR, BL, BR order.
    """
    if len(pts) != 4:
        return False
    tl, tr, bl, br = pts
    # Re-order to clockwise winding: TL → TR → BR → BL
    quad = [tl, tr, br, bl]
    area = 0.0
    for i in range(4):
        x1, y1 = quad[i]
        x2, y2 = quad[(i + 1) % 4]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2 > 10_000
