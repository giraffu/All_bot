from dotenv import load_dotenv
load_dotenv()
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET

objects = storage.list_objects("", bucket=MINIO_TEMPLATE_BUCKET)
print(f"Total objects in bucket: {len(objects)}")
