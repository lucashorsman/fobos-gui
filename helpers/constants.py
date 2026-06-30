POSITIONER_READY = "ready"
POSITIONER_MOVING = "moving"
POSITIONER_ERROR = "error"
SHORT_ARM_LENGTH = 100.0  # in mm
LONG_ARM_LENGTH = 150.0
GRID_SPACING = 100.0  # in mm


def normalize_for_positioner(angle: float) -> float:
    """Normalize an angle (degrees) into the positioner's accepted range [-10°, 370°]."""
    adjusted = float(angle)
    while adjusted < -10.0:
        adjusted += 360.0
    while adjusted > 370.0:
        adjusted -= 360.0
    return adjusted