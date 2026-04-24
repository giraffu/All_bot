import time
import requests
import os
from minio import Minio

api_url = "http://127.0.0.1:8003/status/{}"

tasks = ["3ff16fef-eaa0-4dad-8152-fcf6bb04bb9d", "f60b3f2a-86fe-42cf-8768-1eef5f76b9c9"]
output_dir = "/home/hfy/APP/All_bot/test_data"

minio_client = Minio(
    "192.168.1.115:9000",
    access_key="chuzeyu",
    secret_key="@Cv1347968277",
    secure=False
)
bucket_name = "comfyui-temp"

for idx, task in enumerate(tasks):
    while True:
        try:
            r = requests.get(api_url.format(task))
            data = r.json()
            print(f"Task {task} status: {data['status']}, progress: {data.get('progress')}")
            if data['status'] in ['done', 'error']:
                result_path = data.get('result_path')
                print(f"Result for {task}: {result_path} {data.get('error')}")
                
                if data['status'] == 'done' and result_path:
                    lora_status = "no_lora" if idx == 0 else "with_lora"
                    save_path = os.path.join(output_dir, f"output_{lora_status}_{result_path}")
                    print(f"Downloading from MinIO to {save_path}...")
                    minio_client.fget_object(bucket_name, result_path, save_path)
                    print("Download complete.")
                break
        except Exception as e:
            print("Error checking status:", e)
            break
        time.sleep(2)
