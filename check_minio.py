import os
from minio import Minio

def main():
    client = Minio(
        "192.168.1.115:9000",
        access_key="chuzeyu",
        secret_key="@Cv1347968277",
        secure=False
    )
    buckets = client.list_buckets()
    for b in buckets:
        print(b.name)
    
if __name__ == "__main__":
    main()
