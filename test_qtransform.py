from PySide6.QtGui import QTransform, QVector2D
import numpy as np
from skimage.transform import ProjectiveTransform

# create fake points
src = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
dst = np.array([[0, 0], [20, 0], [15, 15], [0, 20]])

tform = ProjectiveTransform()
tform.estimate(src, dst)
T = tform.params
print("skimage params:\n", T)

# skimage transform
test_pt = np.array([[5, 5]])
res_ski = tform(test_pt)
print("skimage output:", res_ski)

qt_form = QTransform(
    T[0,0], T[1,0], T[2,0],
    T[0,1], T[1,1], T[2,1],
    T[0,2], T[1,2], T[2,2]
)
res_qt = qt_form.map(5.0, 5.0)
print("qt output:", res_qt)
