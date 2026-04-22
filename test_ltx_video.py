import os
import time
import requests
from minio import Minio

# Config
MINIO_ENDPOINT = "192.168.1.115:9000"
MINIO_ACCESS_KEY = "chuzeyu"
MINIO_SECRET_KEY = "@Cv1347968277"
MINIO_BUCKET = "bot-data"
API_URL = "http://localhost:8003"
API_TOKEN = "your_secure_token_here"

FILE_PATH = "/home/hfy/APP/All_bot/test_data/C577ECBD-6492-4D9C-9BE5-5F5679DC5112.jpeg"
OBJECT_KEY = "test_data/C577ECBD-6492-4D9C-9BE5-5F5679DC5112.jpeg"

def upload_to_minio():
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    print(f"Uploading {FILE_PATH} to {MINIO_BUCKET}/{OBJECT_KEY}...")
    client.fput_object(MINIO_BUCKET, OBJECT_KEY, FILE_PATH)
    print("Upload complete.")

def submit_task():
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    payload = {
        "image": OBJECT_KEY,
        "prompt": 'Selfie-style closeup video of a young chinese woman The girl in the picture slowly takes off her clothes and is completely naked. the camera slowly zooms in to a low angle extreme close-up on her detailed pussy and anus and wet vaginal opening from behind as he ass is exposed. she playfully says "is this what you want to eat?"',
        "length": 10,
        "width": 704,
        "height": 1280,
        "priority": 10
    }
    print("Submitting task...")
    resp = requests.post(f"{API_URL}/api/v1/ltx_video", json=payload, headers=headers)
    resp.raise_for_status()
    task_id = resp.json()["task_id"]
    print(f"Task submitted successfully! Task ID: {task_id}")
    return task_id

def poll_task(task_id):
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    print("Polling task status...")
    while True:
        resp = requests.get(f"{API_URL}/api/v1/tasks/{task_id}", headers=headers)
        resp.raise_for_status()
        data = resp.json()
        status = data["status"]
        progress = data.get("progress", 0)
        
        print(f"Status: {status} | Progress: {progress} | Queue pos: {data.get('queue_pos')}")
        
        if status == "done":
            print(f"Task completed successfully!")
            print(f"Result Path: {data.get('result_path')}")
            break
        elif status == "error":
            print(f"Task failed! Error: {data.get('error')}")
            break
        elif status == "cancelled":
            print("Task was cancelled.")
            break
            
        time.sleep(5)

if __name__ == "__main__":
    upload_to_minio()
    task_id = submit_task()
    poll_task(task_id)