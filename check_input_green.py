import cv2
import numpy as np

cap = cv2.VideoCapture('/home/hfy/APP/All_bot/test_data/202.mp4')
ret, frame = cap.read()
if ret:
    h, w, _ = frame.shape
    right_side = frame[:, -20:, :]
    avg_color = np.mean(right_side, axis=(0, 1))
    print(f"Input video right side avg color (BGR): {avg_color}")
cap.release()
