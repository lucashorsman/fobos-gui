
import math
#given a target point (x, y) and the lengths of two links (l1, l2), calculate the two possible joint angle solutions (theta1, theta2) to reach that point. The function should return the angles in degrees and handle cases where the point is unreachable due to being outside the annulus defined by the link lengths.
def solve_inverse_kinematics(x, y, l1, l2):
    """
    Calculates the two possible joint angle solutions (theta1, theta2) 
    to reach a target (x, y) coordinate.
    
    Parameters:
    x, y : float -> Target coordinates
    l1   : float -> Length of the first link
    l2   : float -> Length of the second link
    
    Returns:
    tuple -> (sol1, sol2) where each solution is (theta1_deg, theta2_deg),
             or None if the point is unreachable.
    """
    # 1. Calculate squared distance to target
    r_sq = x**2 + y**2
    r = math.sqrt(r_sq)
    
    # 2. Check if the point is inside the reachable annulus
    max_radius = l1 + l2
    min_radius = abs(l1 - l2)
    
    if r > max_radius or r < min_radius:
        print(f"Point ({x}, {y}) is outside the reachable annulus.")
        return None

    # 3. Calculate cos(theta2) using the Law of Cosines
    cos_theta2 = (r_sq - l1**2 - l2**2) / (2 * l1 * l2)
    
    # Clamp cos_theta2 to avoid floating-point inaccuracies at boundaries
    cos_theta2 = max(-1.0, min(1.0, cos_theta2))
    
    # 4. Calculate both options for sin(theta2)
    sin_theta2_sol1 = math.sqrt(1.0 - cos_theta2**2)  # Elbow down configuration
    sin_theta2_sol2 = -sin_theta2_sol1               # Elbow up configuration
    
    # 5. Solve for both configurations
    solutions = []
    for sin_theta2 in [sin_theta2_sol1, sin_theta2_sol2]:
        # Joint 2 angle
        theta2 = math.atan2(sin_theta2, cos_theta2)
        
        # Joint 1 angle
        alpha = math.atan2(y, x)
        beta = math.atan2(l2 * sin_theta2, l1 + l2 * cos_theta2)
        theta1 = alpha - beta
        
        # Convert to degrees and normalize to (-180, 180] or [0, 360) if preferred
        theta1_deg = math.degrees(theta1)
        theta2_deg = math.degrees(theta2)
        
        solutions.append((round(theta1_deg, 2), round(theta2_deg, 2)))
        
    return solutions

def solve_forward_kinematics(alpha: float, beta: float,xc: float, yc: float, l1: float, l2: float) -> tuple[float, float]:
    """Compute the global XY tip position of a positioner from its current angles.

    Args:
        alpha: angle of the first link relative to the x-axis in degrees
        beta: angle of the second link relative to the first link in degrees
        xc: x coordinate of the center of the positioner
        yc: y coordinate of the center of the positioner
        l1: length of the first link
        l2: length of the second link

    Returns:
        tuple: (x, y) coordinates of the tip in the same coordinate space as xc, yc
    """
    alpha_rad = math.radians(alpha)
    beta_rad = math.radians(alpha + beta)

    # Local tip offset in the positioner's own frame
    local_x = l1 * math.cos(alpha_rad) + l2 * math.cos(beta_rad)
    local_y = l1 * math.sin(alpha_rad) + l2 * math.sin(beta_rad)

    # Invert into global frame (kinematic frame is rotated 180 °)
    global_x = xc - local_x
    global_y = yc - local_y

    return global_x, global_y


# --- Example Usage ---

if __name__ == "__main__":
    # Define link lengths (e.g., Inner boundary = 2, Outer boundary = 8)
    link1_length = 5.0
    link2_length = 3.0
    
    # Target point inside the annulus
    target_x = 4.0
    target_y = 4.0
    
    results = solve_inverse_kinematics(target_x, target_y, link1_length, link2_length)
    
    if results:
        sol1, sol2 = results
        print(f"Target Point: ({target_x}, {target_y})")
        print(f"Solution 1 (Elbow Down): Joint 1 = {sol1[0]}°, Joint 2 = {sol1[1]}°")
        print(f"Solution 2 (Elbow Up)  : Joint 1 = {sol2[0]}°, Joint 2 = {sol2[1]}°")