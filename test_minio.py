import sys
import os
sys.path.append("/home/hfy/APP/All_bot")
from config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET, MINIO_TEMPLATE_BUCKET, MINIO_SECURE
from minio import Minio
from datetime import timedelta

client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)
url = client.presigned_get_object(MINIO_TEMPLATE_BUCKET, "temps/7070842447_86038c609bd94a7fa5a233bf1c8ead46.png", expires=timedelta(hours=1))
print(url)
