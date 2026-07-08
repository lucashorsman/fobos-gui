import numpy as np

def fit_circle(points):
    x = points[:, 0]
    y = points[:, 1]
    A = np.column_stack([2*x, 2*y, np.ones(len(x))])
    b = x**2 + y**2
    p, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = p[0], p[1]
    r = np.sqrt(p[2] + cx**2 + cy**2)
    return cx, cy, r


positioner_points_1403 = np.array([[-55,-455],[269,-118],[-41,179],[-342,-118],[-245,-333],[177,-329]])
fit_circle_1403 = fit_circle(positioner_points_1403)
print(f"Positioner 1403: Center = ({fit_circle_1403[0]:.5f}, {fit_circle_1403[1]:.5f}), Radius = {fit_circle_1403[2]:.5f}")

# positioner_points_967 = np.array([[122,232],[284,636],[-118,793],[-280,386],[-106,225],[292,415],[177,-329]])
positioner_points_967 = np.array([[-333,500],[0,167],[-237,267],[236,261],[332,500],[239,732],[0,833]])
fit_circle_967 = fit_circle(positioner_points_967)
print(f"Positioner 967: Center = ({fit_circle_967[0]:.5f}, {fit_circle_967[1]:.5f}), Radius = {fit_circle_967[2]:.5f}")