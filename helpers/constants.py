from enum import StrEnum


class PositionerState(StrEnum):
    """Typed state constants for a positioner.
    Using StrEnum means PositionerState.READY == "ready" is True, so all
    existing string comparisons in widgets remain valid without modification.
    """
    READY   = "ready"
    MOVING  = "moving"
    ERROR   = "error"

#total patrol area should equal 44.8mm diameter. 300ish in pixel space, as given from the circle fit functions
#Positioner 1403: raw pixel points = [[-55, -455], [269, -118], [-41, 179], [-342, -118], [-245, -333], [177, -329]]
#Positioner 1403: center in physical space = (-237.26984, -511.06269), radius = 727.96675
#Positioner 1403: center projected back to pixel space = (-39.33774, -153.62794)
#Positioner radius in pixel space = 301.77877
#Positioner 967: raw pixel points = [[-333, 500], [0, 167], [-237, 267], [236, 261], [332, 500], [239, 732], [0, 833]]
#Positioner 967: center in physical space = (-94.28893, 914.89488), radius = 653.65651
#Positioner 967: center projected back to pixel space = (-0.22011, 478.72307)
#Positioner radius in pixel space = 333.45938
#so arm1 + arm2 = 22.4mm

# SHORT_ARM_LENGTH =7.0  # in mm
# LONG_ARM_LENGTH = 15.4 # in mm
# SHORT_ARM_LENGTH = 100.0  # actually in pixel space
# LONG_ARM_LENGTH = 150.0
SHORT_ARM_LENGTH = 100.0
LONG_ARM_LENGTH = 230.0

GRID_SPACING = 100.0  # in mm


def normalize_for_positioner(angle: float) -> float:
    """Normalize an angle (degrees) into the positioner's accepted range [-10°, 370°]."""
    adjusted = float(angle)
    while adjusted < -10.0:
        adjusted += 360.0
    while adjusted > 370.0:
        adjusted -= 360.0
    return adjusted