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

# Using the circle fit radii to determine a pixel scale factor:
# Average radius in px = (301.77877 + 333.45938) / 2 = 317.619075
# This corresponds to the physical radius of 22.4 mm (from 44.8mm diameter)
MM_TO_PX = ((301.77877 + 333.45938) / 2.0) / 22.4

SHORT_ARM_LENGTH_MM = 7.6
LONG_ARM_LENGTH_MM = 15.0

# -- Verify feature constants ------------------------------------------------
# Pass/fail tolerance for metrology verification (pixels).
# At ~14 px/mm this is roughly 0.7 mm positional accuracy.
VERIFY_TOLERANCE_PX = 30.0

# Half-width (pixels) of the search window around the expected laser position.
# Generous at 75 px to compensate for interpolation error with the current
# sparse (3α × 5β = 15-point) sweep.  After a denser resweep (recommended:
# 6×6 = 36 pts minimum, 9×9 = 81 pts ideal) this can be tightened to ~25 px.
VERIFY_ROI_SIZE = 75

# Detection threshold — minimum intensity difference (laser ON − laser OFF)
# to count as signal in the frame-subtraction step.
VERIFY_THRESH = 15.0


GRID_SPACING = 6.35  # in mm (4 squares per inch)


def normalize_for_positioner(angle: float) -> float:
    """Normalize an angle (degrees) into the positioner's accepted range [-10°, 370°]."""
    adjusted = float(angle)
    while adjusted < -10.0:
        adjusted += 360.0
    while adjusted > 370.0:
        adjusted -= 360.0
    return adjusted