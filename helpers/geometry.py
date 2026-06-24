import math
from helpers.constants import SHORT_ARM_LENGTH, LONG_ARM_LENGTH

def get_clicked_positioner(click_x, click_y, positioners_dict, selected_pid):
    """
    Finds the positioner that was clicked.
    Prioritizes the currently selected positioner if the click falls within its reachable annulus.
    Otherwise, returns the closest positioner's ID.
    Returns None if the click is completely outside any positioner's reach.
    """
    if not positioners_dict:
        return None

    outer_radius = SHORT_ARM_LENGTH + LONG_ARM_LENGTH

    # Check if clicked inside the currently selected positioner first
    if selected_pid is not None and selected_pid in positioners_dict:
        cx, cy = positioners_dict[selected_pid].get('center', (0.0, 0.0)) #the 0,0 here is a default in cases where the center isnt set.
        if math.hypot(click_x - cx, click_y - cy) <= outer_radius:
            return selected_pid

    # If not, find the closest positioner
    closest_pid = None
    min_dist = float('inf')
    for pid, pos in positioners_dict.items():
        cx, cy = pos.get('center', (0.0, 0.0))
        dist = math.hypot(click_x - cx, click_y - cy)
        if dist <= outer_radius and dist < min_dist:
            min_dist = dist
            closest_pid = pid

    return closest_pid
