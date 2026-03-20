from dotenv import load_dotenv
load_dotenv()
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET

objects = storage.list_objects("temps/", bucket=MINIO_TEMPLATE_BUCKET)
print(f"Total objects in temps/: {len(objects)}")
if objects:
    print(objects[:5])
