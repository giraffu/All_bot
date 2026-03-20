from dotenv import load_dotenv
load_dotenv()
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET

minio_path = "temps/7070842447_86038c609bd94a7fa5a233bf1c8ead46.png"
print(f"Testing object: {minio_path}")
try:
    stat = storage.client.stat_object(MINIO_TEMPLATE_BUCKET, minio_path)
    print(f"Object exists! Size: {stat.size}, Last Modified: {stat.last_modified}")
    url = storage.get_presigned_url(minio_path, bucket=MINIO_TEMPLATE_BUCKET)
    print(f"Presigned URL:\n{url}")
except Exception as e:
    print(f"Error checking object: {e}")
