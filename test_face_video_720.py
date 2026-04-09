import os
import time
import requests
from minio import Minio

def main():
    print("Initializing MinIO client...")
    minio_client = Minio(
        "127.0.0.1:9000",
        access_key="chuzeyu",
        secret_key="@Cv1347968277",
        secure=False
    )

    bucket_name = "bot-data"
    
    # Ensure bucket exists
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)

    face_image_path = "/home/hfy/APP/All_bot/test_data/C577ECBD-6492-4D9C-9BE5-5F5679DC5112.jpeg"
    video_path = "/home/hfy/APP/All_bot/test_data/202.mp4"

    face_image_key = f"test_face_video/face_image_{int(time.time())}.jpeg"
    video_key = f"test_face_video/video_{int(time.time())}.mp4"

    print("Uploading face image to MinIO...")
    minio_client.fput_object(bucket_name, face_image_key, face_image_path)
    
    print("Uploading video to MinIO...")
    minio_client.fput_object(bucket_name, video_key, video_path)

    print(f"Uploaded {face_image_key} and {video_key} to MinIO")

    # Call API
    url = "http://127.0.0.1:8003/face_video"
    headers = {
        "Authorization": "Bearer your_secure_token_here",
        "Content-Type": "application/json"
    }

    data = {
        "face_image": face_image_key,
        "video": video_key,
        "resolution": 720,
        "duration": 49,
        "priority": 100
    }

    print("Calling API endpoint /face_video...")
    response = requests.post(url, headers=headers, json=data)
    print("API Response:", response.json())

    task_id = response.json().get("task_id")

    if task_id:
        print(f"Polling task status for {task_id}...")
        while True:
            status_url = f"http://127.0.0.1:8003/status/{task_id}"
            status_res = requests.get(status_url)
            status_data = status_res.json()
            
            status = status_data.get("status")
            progress = status_data.get("progress")
            print(f"Status: {status}, Progress: {progress}%")
            
            if status == "done":
                print(f"Final Status: {status_data}")
                result_path = status_data.get("result_path")
                if result_path:
                    output_file = f"/home/hfy/APP/All_bot/test_data/output_video_{int(time.time())}.mp4"
                    print(f"Downloading result to {output_file}...")
                    try:
                        minio_client.fget_object("comfyui-temp", result_path, output_file)
                        print(f"Download complete: {output_file}")
                    except Exception as e:
                        print(f"Failed to download result: {e}")
                break
            elif status == "error":
                print(f"Final Status: {status_data}")
                break
            time.sleep(3)

if __name__ == "__main__":
    main()
