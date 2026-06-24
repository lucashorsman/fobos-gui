import cv2

def main():
    # Use 0 for webcam, or replace with a video file path (e.g., 'video.mp4')
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("Error: Could not open video source.")
        return

    # Configuration Parameters
    scale = 1.0           # 1.0 is default (no zoom). > 1.0 is zoomed in.
    scale_step = 0.2      # How much to zoom in/out per key press
    pan_x = 0             # X-axis offset from center
    pan_y = 0             # Y-axis offset from center
    pan_step = 20         # Pixels to pan per key press

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        H, W = frame.shape[:2]
        
        # 1. Calculate the size of the Region of Interest (ROI) based on scale
        w = int(W / scale)
        h = int(H / scale)
        
        # 2. Calculate the maximum allowable pan to prevent crashing at the edges
        max_pan_x = (W - w) // 2
        max_pan_y = (H - h) // 2
        
        # Clamp the pan values within the allowable boundaries
        pan_x = max(-max_pan_x, min(max_pan_x, pan_x))
        pan_y = max(-max_pan_y, min(max_pan_y, pan_y))
        
        # 3. Calculate the top-left and bottom-right coordinates of the crop
        x1 = (W - w) // 2 + pan_x
        y1 = (H - h) // 2 + pan_y
        x2 = x1 + w
        y2 = y1 + h
        
        # 4. Crop the frame and resize it back to the original window size
        cropped_frame = frame[y1:y2, x1:x2]
        zoomed_frame = cv2.resize(cropped_frame, (W, H))
        
        # Overlay HUD text
        cv2.putText(
            zoomed_frame, 
            f"Zoom: {scale:.1f}x | Pan: ({pan_x}, {pan_y})", 
            (10, 30), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.7, 
            (0, 255, 0), 
            2
        )
        
        cv2.imshow("OpenCV Pan & Zoom", zoomed_frame)
        
        # Keyboard controls
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q') or key == 27: # 'q' or 'ESC' to quit
            break
        elif key == ord('='):            # '=' (or '+') to Zoom In
            scale += scale_step
        elif key == ord('-'):            # '-' to Zoom Out
            scale = max(1.0, scale - scale_step)
            # Reset pan strictly to center if we zoom all the way out
            if scale == 1.0:
                pan_x, pan_y = 0, 0
                
        # WASD Panning Controls
        elif key == ord('w'): pan_y -= pan_step  # Up
        elif key == ord('s'): pan_y += pan_step  # Down
        elif key == ord('a'): pan_x -= pan_step  # Left
        elif key == ord('d'): pan_x += pan_step  # Right
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()