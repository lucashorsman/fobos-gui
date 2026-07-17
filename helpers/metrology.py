import numpy as np
import ndimage
from scipy.optimize import linear_sum_assignment



def detect_all_blobs(ref_frame, check_frame, thresh, min_pixels=3):
    """
    Full-frame diff + threshold + connected components. Returns a list
    of blob dicts: {'centroid': (x, y), 'flux': float, 'size': int}.
    Cheap even at full-frame scale since it's a single label() call.
    """
    diff = check_frame.astype(np.float32) - ref_frame.astype(np.float32)
    diff[diff < 0] = 0
    mask = diff > thresh

    labeled, n = ndimage.label(mask)
    blobs = []
    if n == 0:
        return blobs

    sizes = ndimage.sum(mask, labeled, range(1, n + 1))
    ys, xs = np.indices(diff.shape)
    for i, size in enumerate(sizes, start=1):
        if size < min_pixels:
            continue
        blob_mask = labeled == i
        weights = diff * blob_mask
        total = weights.sum()
        if total <= 0:
            continue
        cx = (xs * weights).sum() / total
        cy = (ys * weights).sum() / total
        blobs.append({"centroid": (float(cx), float(cy)),
                       "flux": float(diff[blob_mask].max()),
                       "size": int(size)})
    return blobs

def verify_fibers_global(ref_frame, check_frame, expected_positions, roi_size=25,
                          thresh=15.0, tolerance_px=2.0, min_pixels=3):
    """
    Collision-safe verification: detect all blobs once, then assign
    fibers to blobs one-to-one via the Hungarian algorithm, disallowing
    any pairing farther apart than roi_size.

    Returns (results, unmatched_blobs). results has the same shape as
    verify_fibers()'s output. unmatched_blobs is a list of blobs that
    were detected but not claimed by any fiber (stray light, a ghost
    fiber, etc.) — worth surfacing to the operator, not just discarding.
    """
    blobs = detect_all_blobs(ref_frame, check_frame, thresh, min_pixels)
    fids = list(expected_positions.keys())

    results = {fid: {"expected_px": expected_positions[fid], "measured_px": None,
                      "error_px": None, "flux": 0.0, "found": False, "pass": False,
                      "roi": (expected_positions[fid][0] - roi_size,
                              expected_positions[fid][1] - roi_size,
                              expected_positions[fid][0] + roi_size,
                              expected_positions[fid][1] + roi_size)}
               for fid in fids}

    if not blobs or not fids:
        return results, blobs

    n_fibers, n_blobs = len(fids), len(blobs)
    # Cost matrix padded to square with a large "no-match" cost, so the
    # Hungarian solver can leave fibers or blobs unassigned when nothing
    # is within range, instead of being forced to pick something.
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
            continue  # padding slot, not a real fiber or blob
        if cost[i, j] >= big_cost:
            continue  # nothing within roi_size -> stays "not found"
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
