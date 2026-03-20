from dotenv import load_dotenv
load_dotenv()
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET
import requests

minio_path = "temps/1394805370_03721554d8a447f0a6d92dec9acfb64d.png"
url = storage.get_presigned_url(minio_path, bucket=MINIO_TEMPLATE_BUCKET)
print(f"URL: {url}")
