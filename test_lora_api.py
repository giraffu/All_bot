import os
import requests
from minio import Minio
import time

minio_client = Minio(
    "192.168.1.115:9000",
    access_key="chuzeyu",
    secret_key="@Cv1347968277",
    secure=False
)

bucket_name = "bot-data"
file_path = "/home/hfy/APP/All_bot/test_data/C577ECBD-6492-4D9C-9BE5-5F5679DC5112.jpeg"
object_name = "test_lora_image.jpeg"

print(f"Uploading {file_path} to MinIO bucket {bucket_name} as {object_name}...")
minio_client.fput_object(bucket_name, object_name, file_path)
print("Upload successful.")

api_url = "http://127.0.0.1:8003/comfy_img2img_lora"
headers = {"Authorization": "Bearer your_secure_token_here"}

prompt = "用原本的背景，是个高中生样子。雙馬尾，大長腿。显示全身。女主躺在地上，双腿张开抬起，高筒蕾絲黑絲襪，呈现m字腿样子，，用手臂勾著，臉 表情髮型保持原本內容，畫質一致，眼角有泪水，胸口用奇異筆寫著聖凱大人的馬桶，露出超級大乳房超大，下半身露出阴部，沒有陰毛。男人雙腿之間的陰莖完全插入陰道，阴道流出白色精液，脸上也被射满精液，衣服破损。身上沾滿半透明精液。像是被强奸完丢在垃圾堆里。保证画面是真实的摄影风 巨乳，日式學生服"

payload1 = {
    "image": object_name,
    "prompt": prompt,
    "lora_name": "",
    "priority": 0
}

payload2 = {
    "image": object_name,
    "prompt": prompt,
    "lora_name": "qwen/YARN_1.0.safetensors",
    "lora_strength": 1.0,
    "priority": 0
}

print("\n--- Testing API ---")
try:
    r1 = requests.post(api_url, headers=headers, json=payload1)
    print("Request 1 (No LoRA) Response:", r1.json())
except Exception as e:
    print("Request 1 failed:", e)

time.sleep(1)

try:
    r2 = requests.post(api_url, headers=headers, json=payload2)
    print("Request 2 (With LoRA) Response:", r2.json())
except Exception as e:
    print("Request 2 failed:", e)

