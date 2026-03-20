with open("../.env", "r") as f:
    content = f.read()

if "MINIO_PUBLIC_URL=" not in content:
    with open("../.env", "a") as f:
        f.write("\nMINIO_PUBLIC_URL=http://192.168.1.115:9000\n")
        print("Added MINIO_PUBLIC_URL to .env")
else:
    print("MINIO_PUBLIC_URL already exists")
