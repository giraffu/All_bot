import os
import hashlib
import boto3
import psycopg2
import time
import csv
import logging
from datetime import datetime, timezone
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

# Configuration
SRC_DIR = "/home/hfy/APP/All_bot/user_data"
BUCKET_NAME = "bot-data"
REPORT_FILE = "file_migration_report.csv"

# MinIO Config
MINIO_ENDPOINT = "192.168.1.115:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"

# Postgres Config
PG_HOST = "192.168.1.115"
PG_PORT = "5432"
PG_DB = "bot_db"
PG_USER = "postgres"
PG_PASS = "postgrespassword"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("file_migration.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_pg_connection():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASS
    )

def setup_db():
    """Create necessary tables in PostgreSQL."""
    conn = get_pg_connection()
    cur = conn.cursor()
    try:
        # Create file_checksum table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_checksum (
                file_path VARCHAR(512) PRIMARY KEY,
                md5 VARCHAR(32),
                size BIGINT,
                uploaded_at TIMESTAMPTZ
            );
        """)
        
        # Create upload_fail_log table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS upload_fail_log (
                id SERIAL PRIMARY KEY,
                file_path TEXT,
                error_message TEXT,
                failed_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        conn.commit()
        logger.info("Database tables created/verified.")
    except Exception as e:
        logger.error(f"Error setting up database: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def calculate_md5(file_path):
    """Calculate MD5 checksum of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def upload_file_to_minio(s3_client, file_path, object_name):
    """Upload file to MinIO with retry logic."""
    config = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,  # 64 MiB
        multipart_chunksize=16 * 1024 * 1024,  # 16 MiB
        max_concurrency=8
    )
    
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            s3_client.upload_file(file_path, BUCKET_NAME, object_name, Config=config)
            return True
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Upload failed for {file_path}, retrying ({attempt+1}/{max_retries})... Error: {e}")
                time.sleep(1)  # Simple backoff
            else:
                logger.error(f"Upload failed for {file_path} after {max_retries} retries. Error: {e}")
                return False

def record_success(conn, file_path, md5_hash, size):
    """Record successful upload to DB."""
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO file_checksum (file_path, md5, size, uploaded_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (file_path) DO UPDATE 
            SET md5 = EXCLUDED.md5, size = EXCLUDED.size, uploaded_at = EXCLUDED.uploaded_at;
        """, (file_path, md5_hash, size))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to record success for {file_path}: {e}")
        conn.rollback()
    finally:
        cur.close()

def record_failure(conn, file_path, error_message):
    """Record failure to DB."""
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO upload_fail_log (file_path, error_message)
            VALUES (%s, %s);
        """, (file_path, str(error_message)))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to record failure for {file_path}: {e}")
        conn.rollback()
    finally:
        cur.close()

def main():
    start_time = time.time()
    setup_db()
    
    # Initialize MinIO client
    s3_client = boto3.client(
        's3',
        endpoint_url=f"http://{MINIO_ENDPOINT}",
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=boto3.session.Config(signature_version='s3v4')
    )
    
    # Ensure bucket exists
    try:
        s3_client.head_bucket(Bucket=BUCKET_NAME)
    except ClientError:
        try:
            s3_client.create_bucket(Bucket=BUCKET_NAME)
            logger.info(f"Bucket {BUCKET_NAME} created.")
        except Exception as e:
            logger.error(f"Failed to create bucket: {e}")
            return

    conn = get_pg_connection()
    
    success_count = 0
    fail_count = 0
    total_bytes = 0
    
    # Walk directory
    for root, dirs, files in os.walk(SRC_DIR):
        for file in files:
            abs_path = os.path.join(root, file)
            # Calculate relative path for object key (must start with /user_data)
            rel_path = os.path.relpath(abs_path, os.path.dirname(SRC_DIR))
            # Ensure it starts with /user_data (relpath might strip leading slash)
            object_name = "/" + rel_path if not rel_path.startswith("/") else rel_path
            
            file_size = os.path.getsize(abs_path)
            
            logger.info(f"Processing {abs_path} -> {object_name}")
            
            try:
                # 1. Calculate MD5
                md5_hash = calculate_md5(abs_path)
                
                # 2. Upload
                if upload_file_to_minio(s3_client, abs_path, object_name):
                    # 3. Record Success
                    record_success(conn, abs_path, md5_hash, file_size)
                    success_count += 1
                    total_bytes += file_size
                else:
                    # 4. Record Failure
                    record_failure(conn, abs_path, "Max retries exceeded")
                    fail_count += 1
            except Exception as e:
                logger.error(f"Unexpected error processing {abs_path}: {e}")
                record_failure(conn, abs_path, str(e))
                fail_count += 1

    conn.close()
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Generate CSV Report
    with open(REPORT_FILE, 'w', newline='') as csvfile:
        fieldnames = ['metric', 'value']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({'metric': 'success_count', 'value': success_count})
        writer.writerow({'metric': 'failure_count', 'value': fail_count})
        writer.writerow({'metric': 'total_time_seconds', 'value': f"{total_time:.2f}"})
        writer.writerow({'metric': 'total_bytes', 'value': total_bytes})
    
    logger.info(f"Migration completed. Report saved to {REPORT_FILE}")
    print(f"Migration completed.\nSuccess: {success_count}\nFailed: {fail_count}\nTime: {total_time:.2f}s\nBytes: {total_bytes}")

if __name__ == "__main__":
    main()
