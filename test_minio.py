import os
import sys
from minio import Minio

MINIO_ENDPOINT = "minio.aivison.it.com"
MINIO_ACCESS_KEY = "chuzeyu"
MINIO_SECRET_KEY = "@Cv1347968277"
TEST_BUCKET = "bot-data"

def test_minio_connection():
    print(f"[*] 正在尝试连接 MinIO...")
    
    # 模拟 agent_main.py 的连接方式 (secure=True)
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=True
    )
    
    try:
        objects = client.list_objects(TEST_BUCKET, recursive=True)
        count = 0
        test_object = None
        for obj in objects:
            if count == 0:
                test_object = obj.object_name
            count += 1
            if count >= 1:
                break
                
        if test_object:
            print(f"    [成功] 获取到测试对象: {test_object}")
            client.fget_object(TEST_BUCKET, test_object, "test_download_file.tmp")
            print("    [成功] 下载成功！")
            os.remove("test_download_file.tmp")
            
    except Exception as err:
        print(f"\n[失败] 异常: {err}")

if __name__ == "__main__":
    test_minio_connection()
