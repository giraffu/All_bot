import cv2
import numpy as np

cap = cv2.VideoCapture('/home/hfy/APP/All_bot/test_data/output_video_1775723195.mp4')
ret, frame = cap.read()
if ret:
    cv2.imwrite('frame.png', frame)
    # Check if there is a strong green color on the right side
    h, w, _ = frame.shape
    right_side = frame[:, -20:, :]
    # Green in BGR is roughly (0, 255, 0)
    # Let's just print the average color of the right side
    avg_color = np.mean(right_side, axis=(0, 1))
    print(f"Avg color on right side (BGR): {avg_color}")
cap.release()
