import os
import sys
from minio import Minio

MINIO_ENDPOINT = "minio.aivison.it.com"
MINIO_ACCESS_KEY = "chuzeyu"
MINIO_SECRET_KEY = "@Cv1347968277"
TEST_BUCKET = "bot-data"

def test_minio_connection():
    print(f"[*] 正在尝试连接外部 MinIO...")
    print(f"    Endpoint: {MINIO_ENDPOINT}")
    
    # 外部服务器通常配置了域名和 HTTPS，所以我们使用 secure=True
    # 或者如果遇到证书问题可以尝试 secure=False
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=True  # 先尝试 HTTPS
    )
    
    try:
        # 测试读取对象
        print(f"\n[*] 正在测试读取 Bucket '{TEST_BUCKET}' 的内容...")
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
            print(f"\n[*] 正在测试下载该文件...")
            client.fget_object(TEST_BUCKET, test_object, "test_download_file.tmp")
            print("    [成功] 下载成功！外部服务器访问 MinIO 的权限已经生效。")
            os.remove("test_download_file.tmp")
            
    except Exception as err:
        print(f"\n[失败] 异常: {err}")
        print("如果提示证书错误或类似 ssl 错误，可能是 HTTPS 配置问题。")
        print("如果提示 AccessDenied，说明权限还是没配置好。")

if __name__ == "__main__":
    test_minio_connection()
