from PIL import Image
import os

img_path = "/home/hfy/APP/All_bot/test_data/C577ECBD-6492-4D9C-9BE5-5F5679DC5112.jpeg"
if os.path.exists(img_path):
    img = Image.open(img_path)
    print(f"Face Image Size: {img.size}")
else:
    print("Face image not found")

