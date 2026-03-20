from dotenv import load_dotenv
load_dotenv()
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET
import requests

# Get one object to test
objects = storage.list_objects("temps/", bucket=MINIO_TEMPLATE_BUCKET)
if objects:
    obj_name = objects[0]
    print(f"Testing object: {obj_name}")
    url = storage.get_presigned_url(obj_name, bucket=MINIO_TEMPLATE_BUCKET)
    print(f"Presigned URL:\n{url}")
    
    # Try fetching it
    try:
        resp = requests.get(url)
        print(f"Status Code: {resp.status_code}")
    except Exception as e:
        print(f"Request failed: {e}")
