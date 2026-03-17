import os
import sys
import json
import hashlib
from pathlib import Path
from minio import Minio

# Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "192.168.1.115:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_TEMPLATE_BUCKET = os.getenv("MINIO_TEMPLATE_BUCKET", "bot-template")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

SOURCE_DIR = Path("templates")
PROGRESS_FILE = "template_migration_progress.json"

def calculate_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_minio_client():
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE
    )

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"uploaded_files": []}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f)

def get_content_type(file_path):
    ext = file_path.suffix.lower()
    if ext in ['.jpg', '.jpeg']:
        return 'image/jpeg'
    elif ext == '.png':
        return 'image/png'
    elif ext == '.webp':
        return 'image/webp'
    elif ext == '.mp4':
        return 'video/mp4'
    return 'application/octet-stream'

def migrate_templates():
    client = get_minio_client()

    # Ensure bucket exists
    if not client.bucket_exists(MINIO_TEMPLATE_BUCKET):
        print(f"Bucket {MINIO_TEMPLATE_BUCKET} does not exist. Creating...")
        client.make_bucket(MINIO_TEMPLATE_BUCKET)
    
    progress = load_progress()
    uploaded_set = set(progress["uploaded_files"])
    
    print(f"Scanning {SOURCE_DIR}...")
    files_to_upload = []
    
    if not SOURCE_DIR.exists():
        print(f"Directory {SOURCE_DIR} does not exist.")
        return

    for root, dirs, files in os.walk(SOURCE_DIR):
        for file in files:
            file_path = Path(root) / file
            # Relative path becomes the object key (e.g., templates/penetration/1.jpg -> penetration/1.jpg)
            relative_path = file_path.relative_to(SOURCE_DIR)
            object_name = str(relative_path).replace("\\", "/") # Normalize path for MinIO
            
            if object_name not in uploaded_set:
                files_to_upload.append((file_path, object_name))

    total_files = len(files_to_upload)
    print(f"Found {total_files} new templates to upload.")

    for i, (file_path, object_name) in enumerate(files_to_upload):
        try:
            content_type = get_content_type(file_path)
            client.fput_object(
                MINIO_TEMPLATE_BUCKET,
                object_name,
                str(file_path),
                content_type=content_type
            )
            uploaded_set.add(object_name)
            
            if i % 5 == 0:
                progress["uploaded_files"] = list(uploaded_set)
                save_progress(progress)
                print(f"Progress: {i+1}/{total_files} files uploaded...", end='\r')
                
        except Exception as e:
            print(f"\nError uploading {file_path}: {e}")

    progress["uploaded_files"] = list(uploaded_set)
    save_progress(progress)
    print(f"\nTemplate migration completed.")

    # Verification
    print("\nStarting verification (MD5 check)...")
    verified_count = 0
    error_count = 0
    
    all_local_files = []
    for root, dirs, files in os.walk(SOURCE_DIR):
        for file in files:
            all_local_files.append(Path(root) / file)
            
    total_verify = len(all_local_files)
    
    for i, file_path in enumerate(all_local_files):
        relative_path = file_path.relative_to(SOURCE_DIR)
        object_name = str(relative_path).replace("\\", "/")
        
        try:
            stat = client.stat_object(MINIO_TEMPLATE_BUCKET, object_name)
            local_md5 = calculate_md5(file_path)
            
            # ETag might have quotes
            etag = stat.etag.replace('"', '')
            if etag == local_md5 or '-' in etag: # multipart uploads have '-' in etag
                verified_count += 1
            else:
                print(f"MD5 Mismatch: {object_name} (Local: {local_md5}, Remote: {etag})")
                error_count += 1
                
        except Exception as e:
            print(f"Missing in MinIO: {object_name} ({e})")
            error_count += 1
            
        if i % 10 == 0:
            print(f"Verified {i}/{total_verify}...", end='\r')

    print(f"\nVerification finished: {verified_count} valid, {error_count} errors.")

if __name__ == "__main__":
    migrate_templates()
