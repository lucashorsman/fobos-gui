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


def project_points(points, projection):
    return np.array([projection.camera_to_physical(x, y) for x, y in points], dtype=float)


def analyze_positioner(name, pixel_points, projection):
    print(f"Positioner {name}: raw pixel points = {pixel_points.tolist()}")
    physical_points = project_points(pixel_points, projection)
    center_x, center_y, radius = fit_circle(physical_points)
    pixel_center_x, pixel_center_y = projection.physical_to_camera(center_x, center_y)

    print(
        f"Positioner {name}: center in physical space = ({center_x:.5f}, {center_y:.5f}), "
        f"radius = {radius:.5f}"
    )
    print(
        f"Positioner {name}: center projected back to pixel space = "
        f"({pixel_center_x:.5f}, {pixel_center_y:.5f})"
    )
    print("Positioner radius in pixel space = {:.5f}".format(np.linalg.norm(pixel_points[0] - np.array([pixel_center_x, pixel_center_y]))))


if __name__ == "__main__":
    loaded_calibration = load_calibration()
    if loaded_calibration is None:
        raise RuntimeError("No valid calibration found. Cannot project pixel points to physical space.")

    physical_pts, camera_pts = loaded_calibration
    projection = PositionerProjection()
    projection.calibrate(physical_pts, camera_pts)

    positioner_points_1403 = np.array([
        [-55, -455],
        [269, -118],
        [-41, 179],
        [-342, -118],
        [-245, -333],
        [177, -329],
    ])
    analyze_positioner(1403, positioner_points_1403, projection)

    positioner_points_967 = np.array([
        [-333, 500],
        [0, 167],
        [-237, 267],
        [236, 261],
        [332, 500],
        [239, 732],
        [0, 833],
    ])
    analyze_positioner(967, positioner_points_967, projection)

