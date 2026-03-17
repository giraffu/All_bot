
import os
import sys
from minio import Minio
from minio.commonconfig import CopySource

# Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "192.168.1.115:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "bot-data")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

def fix_paths():
    print(f"Connecting to MinIO at {MINIO_ENDPOINT}...", file=sys.stderr)
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE
    )
    
    if not client.bucket_exists(MINIO_BUCKET):
        print(f"Bucket {MINIO_BUCKET} does not exist!", file=sys.stderr)
        return

    # List all objects starting with user_data/
    prefix = "user_data/"
    # If a user ID is provided as arg, use it
    if len(sys.argv) > 1:
        target_user = sys.argv[1]
        prefix = f"user_data/{target_user}/"
        print(f"Targeting specific prefix: {prefix}", file=sys.stderr)
    else:
        print(f"Scanning for ALL objects with prefix '{prefix}'...", file=sys.stderr)
    
    objects = client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True)
    
    count = 0
    moved_count = 0
    error_count = 0
    skipped_count = 0
    
    print("Starting iteration over objects...", file=sys.stderr)

    for obj in objects:
        old_key = obj.object_name
        
        if not old_key.startswith("user_data/"):
            # This shouldn't happen if prefix is user_data/, but just in case
            continue
            
        new_key = old_key[len("user_data/"):]
        
        # Skip if new_key is empty or just a directory slash
        if not new_key or new_key == "/":
            continue
            
        # Check if target already exists to avoid unnecessary work (optional, but safer)
        try:
            client.stat_object(MINIO_BUCKET, new_key)
            # Target exists, maybe we should just delete the old one?
            # Let's be safe and overwrite for now, or skip if size matches?
            # For now, let's just log and continue (overwrite)
            # print(f"Target {new_key} already exists. Overwriting...", file=sys.stderr)
            pass
        except Exception:
            # Target doesn't exist, proceed
            pass

        try:
            # Copy object
            client.copy_object(
                MINIO_BUCKET,
                new_key,
                CopySource(MINIO_BUCKET, old_key)
            )
            
            # Remove old object
            client.remove_object(MINIO_BUCKET, old_key)
            
            moved_count += 1
            if moved_count % 10 == 0:
                 print(f"Moved {moved_count} files...", file=sys.stderr)

        except Exception as e:
            print(f"Error moving {old_key} -> {new_key}: {e}", file=sys.stderr)
            error_count += 1
            
        count += 1
        if count % 100 == 0:
            print(f"Scanned {count} objects...", file=sys.stderr)

    print(f"\nFinished. Scanned: {count}, Moved: {moved_count}, Errors: {error_count}, Skipped: {skipped_count}", file=sys.stderr)

if __name__ == "__main__":
    try:
        fix_paths()
    except Exception as e:
        print(f"Script crashed: {e}", file=sys.stderr)
