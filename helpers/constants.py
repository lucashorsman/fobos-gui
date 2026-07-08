from enum import StrEnum


class PositionerState(StrEnum):
    """Typed state constants for a positioner.
    Using StrEnum means PositionerState.READY == "ready" is True, so all
    existing string comparisons in widgets remain valid without modification.
    """
    READY   = "ready"
    MOVING  = "moving"
    ERROR   = "error"

#total patrol area should equal 44.8mm diameter.
#so arm1 + arm2 = 22.4mm

# SHORT_ARM_LENGTH =7.0  # in mm
# LONG_ARM_LENGTH = 15.4 # in mm
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