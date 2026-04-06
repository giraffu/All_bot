import os
import sys
from minio import Minio

MINIO_ENDPOINT = "minio.aivison.it.com"
MINIO_ACCESS_KEY = "chuzeyu"
MINIO_SECRET_KEY = "@Cv1347968277"
TEST_BUCKET = "bot-data"

def test():
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False  # Intentionally False
    )
    try:
        # 强制求值以触发网络请求
        objects = list(client.list_objects(TEST_BUCKET, recursive=True))
        if len(objects) > 0:
            print(f"Success: {objects[0].object_name}")
        else:
            print("Success, but empty")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
