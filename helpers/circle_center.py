import numpy as np

from calibration_io import load_calibration
from projection import PositionerProjection


def fit_circle(points):
    x = points[:, 0]
    y = points[:, 1]
    a_matrix = np.column_stack([2 * x, 2 * y, np.ones(len(x))])
    b_vector = x**2 + y**2
    params, _, _, _ = np.linalg.lstsq(a_matrix, b_vector, rcond=None)
    center_x, center_y = params[0], params[1]
    radius = np.sqrt(params[2] + center_x**2 + center_y**2)
    return center_x, center_y, radius


def analyze_positioner(name, physical_points):
    center_x, center_y, radius = fit_circle(physical_points)
    
    print(
        f"Positioner {name}: center = ({center_x:.5f}, {center_y:.5f}), "
        f"radius = {radius:.5f} mm"
    )


if __name__ == "__main__":
    # print("Replace these arrays with TRUE MM points read from the GUI grid (bottom right)")
    
    # Example true mm points (replace with actual measurements)
    positioner_points_1403 = np.array([
        [-24,-5],
        [-13,-23],
        [7,-25],
        [20,-9],
        [10,11],
        [-12,13]


        # ... add true mm points here
    ])
    positioner_points_967 = np.array([
        [-21,31],
        [-11,12],
        [11,13],
        [21,32],
        [10,52],
        [-12,51]
    ])
    analyze_positioner(1403, positioner_points_1403)
    analyze_positioner(967, positioner_points_967)