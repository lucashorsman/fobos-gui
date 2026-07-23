import math
from helpers.constants import SHORT_ARM_LENGTH_MM, LONG_ARM_LENGTH_MM
from helpers.annulus import solve_inverse_kinematics




def get_clicked_positioner(click_x, click_y, positioners_dict, selected_pid):
    """
    Finds the positioner that was clicked.
    Prioritizes the currently selected positioner if the click falls within its reachable annulus.
    Otherwise, returns the closest positioner's ID.
    Returns None if the click is completely outside any positioner's reach.
    """
    if not positioners_dict:
        return None

    max_reach = SHORT_ARM_LENGTH_MM + LONG_ARM_LENGTH_MM
    min_reach = abs(LONG_ARM_LENGTH_MM - SHORT_ARM_LENGTH_MM)

    # Check if clicked inside the currently selected positioner first
    if selected_pid is not None and selected_pid in positioners_dict:
        cx, cy = positioners_dict[selected_pid].center
        dist = math.hypot(click_x - cx, click_y - cy)
        if min_reach <= dist <= max_reach:
            return selected_pid

    # If not, find the closest positioner
    closest_pid = None
    min_dist = float('inf')
    for pid, pos in positioners_dict.items():
        cx, cy = pos.center
        dist = math.hypot(click_x - cx, click_y - cy)
        if dist <= max_reach and dist < min_dist:
            min_dist = dist
            closest_pid = pid

    return closest_pid


def resolve_positioner_click(click_x, click_y, positioners_dict, selected_pid):
    """Determine the action for a click at physical coordinates.

    Encapsulates the click-to-queue logic shared by Grid2d and CameraWidget:
    hit-detection, selection change detection, IK resolution.

    Returns:
        ("select", pid, None)       — a different positioner was clicked
        ("queue", pid, solutions)   — the selected positioner was clicked and IK succeeds
        (None, None, None)          — click was outside all positioners or IK failed
    """
    closest_pid = get_clicked_positioner(click_x, click_y, positioners_dict, selected_pid)
    if closest_pid is None:
        return None, None, None

    if closest_pid != selected_pid:
        return "select", closest_pid, None

    cx, cy = positioners_dict[closest_pid].center
    rel_x = click_x - cx
    rel_y = click_y - cy

    # The positioner's kinematic frame is rotated by 180 degrees (inverted X and Y)
    solutions = solve_inverse_kinematics(-rel_x, -rel_y, SHORT_ARM_LENGTH_MM, LONG_ARM_LENGTH_MM)
    if solutions:
        return "queue", closest_pid, solutions

    return None, None, None
