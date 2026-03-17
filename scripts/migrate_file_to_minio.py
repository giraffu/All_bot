import os
import sys
import json
import asyncio
from minio import Minio
from pathlib import Path

# Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "192.168.1.115:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "bot-data")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

SOURCE_DIR = Path("user_data")
PROGRESS_FILE = "migration_progress.json"

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

import hashlib

def calculate_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def migrate_files():
    client = get_minio_client()

    # Ensure bucket exists
    if not client.bucket_exists(MINIO_BUCKET):
        print(f"Bucket {MINIO_BUCKET} does not exist. Creating...")
        client.make_bucket(MINIO_BUCKET)
    
    progress = load_progress()
    uploaded_set = set(progress["uploaded_files"])
    
    print(f"Scanning {SOURCE_DIR}...")
    files_to_upload = []
    for root, dirs, files in os.walk(SOURCE_DIR):
        for file in files:
            file_path = Path(root) / file
            relative_path = file_path.relative_to(SOURCE_DIR)
            object_name = str(relative_path)
            
            # Check if file needs upload (even if in set, verify MD5?)
            # For resume, we trust the set. Verification is separate.
            if object_name not in uploaded_set:
                files_to_upload.append((file_path, object_name))

    total_files = len(files_to_upload)
    print(f"Found {total_files} new files to upload.")

    for i, (file_path, object_name) in enumerate(files_to_upload):
        try:
            client.fput_object(
                MINIO_BUCKET,
                object_name,
                str(file_path),
            )
            uploaded_set.add(object_name)
            
            if i % 10 == 0:
                progress["uploaded_files"] = list(uploaded_set)
                save_progress(progress)
                print(f"Progress: {i}/{total_files} files uploaded...", end='\r')
                
        except Exception as e:
            print(f"\nError uploading {file_path}: {e}")

    progress["uploaded_files"] = list(uploaded_set)
    save_progress(progress)
    print(f"\nFile migration completed.")

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
        object_name = str(relative_path)
        
        try:
            stat = client.stat_object(MINIO_BUCKET, object_name)
            local_md5 = calculate_md5(file_path)
            
            # MinIO ETag is usually MD5 hex
            if stat.etag.replace('"', '') == local_md5:
                verified_count += 1
            else:
                print(f"MD5 Mismatch: {object_name} (Local: {local_md5}, Remote: {stat.etag})")
                error_count += 1
                
        except Exception as e:
            print(f"Missing in MinIO: {object_name} ({e})")
            error_count += 1
            
        if i % 100 == 0:
            print(f"Verified {i}/{total_verify}...", end='\r')

    print(f"\nVerification finished: {verified_count} valid, {error_count} errors.")

if __name__ == "__main__":
    migrate_files()
