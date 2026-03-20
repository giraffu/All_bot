import subprocess
import os
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET
from dotenv import load_dotenv

load_dotenv()

# Get all missing files by reading the text file
with open('container_files.txt', 'r') as f:
    container_files = f.read().splitlines()

# For each file, check if it's in MinIO
uploaded = 0
os.makedirs("templates_extracted", exist_ok=True)

for p in container_files:
    filename = os.path.basename(p)
    # The container files are like /app/templates/temps/filename or /app/templates/quick_face/filename
    # We map them to MinIO path
    if "/temps/" in p:
        minio_path = f"temps/{filename}"
    elif "/quick_face/" in p:
        minio_path = f"quick_face/{filename}"
    elif "/video_nice/" in p:
        minio_path = f"video_nice/{filename}"
    elif "/penetration/" in p:
        minio_path = f"penetration/{filename}"
    else:
        continue
        
    try:
        storage.client.stat_object(MINIO_TEMPLATE_BUCKET, minio_path)
        # Exists, skip
    except Exception:
        print(f"Missing in MinIO: {minio_path}")
        local_p = "templates_extracted/" + filename
        
        # Copy from tg-bot
        try:
            subprocess.run(f"docker cp tg-bot:{p} {local_p}", shell=True, check=True, stderr=subprocess.DEVNULL)
            # Upload to MinIO
            storage.upload_file(local_p, minio_path, bucket=MINIO_TEMPLATE_BUCKET)
            uploaded += 1
            print(f"  -> Uploaded successfully")
        except Exception as e:
            print(f"  -> Failed to extract or upload: {e}")

print(f"Uploaded {uploaded} files to MinIO.")
