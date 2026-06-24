import numpy as np
from skimage import transform as tf
# from skimage import io, util
import matplotlib.pyplot as plt
from astropy.io import ascii
from astropy.table import Table

# image_path = '<INSERT PATH HERE>.tif' #Image path to the one you want to tform
# image = util.img_as_float(io.imread(image_path)) #converts to floating

# ------------
# Makes projective transform
# ------------

pt4_data = ascii.read("4pt_tform_coords.txt") # Change source_x and source_y for every new bg
dest_data = ascii.read("dest_pt.txt") # Destination points only
des_pt = np.column_stack((dest_data['destination_x'], dest_data['destination_y']))

src4_pt = np.column_stack((pt4_data['source_x'], pt4_data['source_y'])) # fits into correct array shape [4,2]
des4_pt = np.column_stack((pt4_data['destination_x'], pt4_data['destination_y'])) 

tform4 = tf.ProjectiveTransform.from_estimate(src4_pt, des4_pt)
if not tform4:
    raise RuntimeError("Failed to estimate transformation.")

#-------------
# Applies transform onto positioner coordinaties
#-------------

src_data = ascii.read("tform_1_pts.txt") # FILE NAME OF SRC POINTS FROM POSITIONER
src_pt = np.column_stack((src_data['fiber_x'], src_data['fiber_y']))

tformed4_src = tform4(src_pt)


#-------------
# Plots it out
#--------------

fig, ax = plt.subplots(nrows=2, figsize=(5, 10))
ax[0].plot(des_pt[:, 0], des_pt[:, 1], '.r', label = 'Destination Pts')
ax[0].plot(tformed4_src[:,0], tformed4_src[:,1], 'b*', label = '4 Pt Transform')

ax[0].legend()

for a in ax:
    a.axis('off')

plt.tight_layout()
plt.savefig('Tformed1.tif') # NAME HERE
plt.show()

