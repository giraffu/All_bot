import os
import sys
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import MINIO_TEMPLATE_BUCKET
from src.services.storage import storage

def verify_bot_template_access():
    print(f"Verifying bot access to templates in bucket: {MINIO_TEMPLATE_BUCKET}")
    
    # Check 'penetration' templates
    print("\n1. Testing penetration templates...")
    pen_templates = storage.list_objects("penetration/", bucket=MINIO_TEMPLATE_BUCKET)
    print(f"Found {len(pen_templates)} penetration templates.")
    if pen_templates:
        sample = pen_templates[0]
        data = storage.get_file_bytes(sample, bucket=MINIO_TEMPLATE_BUCKET)
        print(f"Successfully downloaded {sample} ({len(data)} bytes).")
    else:
        print("WARNING: No penetration templates found!")

    # Check 'quick_face' templates
    print("\n2. Testing quick_face templates...")
    face_templates = storage.list_objects("quick_face/", bucket=MINIO_TEMPLATE_BUCKET)
    print(f"Found {len(face_templates)} quick_face templates.")
    if face_templates:
        sample = face_templates[0]
        data = storage.get_file_bytes(sample, bucket=MINIO_TEMPLATE_BUCKET)
        print(f"Successfully downloaded {sample} ({len(data)} bytes).")
    else:
        print("WARNING: No quick_face templates found!")
        
    print("\nVerification complete. If bytes were successfully downloaded, the bot can access the templates.")

if __name__ == "__main__":
    verify_bot_template_access()
