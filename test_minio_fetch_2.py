from dotenv import load_dotenv
load_dotenv()
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET
import requests

minio_path = "quick_face/885717731_a899c2bb812a4898ac27ddc5a6febf7b.png"
print(f"Testing object: {minio_path}")
url = storage.get_presigned_url(minio_path, bucket=MINIO_TEMPLATE_BUCKET)
print(f"Presigned URL:\n{url}")

try:
    resp = requests.get(url)
    print(f"Status Code: {resp.status_code}")
except Exception as e:
    print(f"Request failed: {e}")
