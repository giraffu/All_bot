import io
import logging
from datetime import timedelta
from minio import Minio
from config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET, MINIO_TEMPLATE_BUCKET, MINIO_SECURE

logger = logging.getLogger(__name__)

class StorageService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StorageService, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self):
        try:
            self.client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE
            )
            # Check main bucket
            if not self.client.bucket_exists(MINIO_BUCKET):
                try:
                    self.client.make_bucket(MINIO_BUCKET)
                    logger.info(f"Created MinIO bucket: {MINIO_BUCKET}")
                except Exception as e:
                    logger.error(f"Failed to create bucket {MINIO_BUCKET}: {e}")
            
            # Check template bucket
            if not self.client.bucket_exists(MINIO_TEMPLATE_BUCKET):
                try:
                    self.client.make_bucket(MINIO_TEMPLATE_BUCKET)
                    logger.info(f"Created MinIO template bucket: {MINIO_TEMPLATE_BUCKET}")
                except Exception as e:
                    logger.error(f"Failed to create template bucket {MINIO_TEMPLATE_BUCKET}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            self.client = None

    def upload_file(self, file_path: str, object_name: str, bucket: str = None) -> str:
        """Upload a local file to MinIO"""
        bucket = bucket or MINIO_BUCKET
        if not self.client:
            logger.error("MinIO client not initialized")
            return ""
        
        try:
            self.client.fput_object(bucket, object_name, file_path)
            return object_name
        except Exception as e:
            logger.error(f"Failed to upload file {file_path} to {object_name} in {bucket}: {e}")
            return ""

    def upload_bytes(self, data: bytes, object_name: str, content_type: str = "application/octet-stream", bucket: str = None) -> str:
        """Upload bytes to MinIO"""
        bucket = bucket or MINIO_BUCKET
        if not self.client:
            logger.error("MinIO client not initialized")
            return ""

        try:
            self.client.put_object(
                bucket, 
                object_name, 
                io.BytesIO(data), 
                len(data),
                content_type=content_type
            )
            return object_name
        except Exception as e:
            logger.error(f"Failed to upload bytes to {object_name} in {bucket}: {e}")
            return ""

    def get_file_bytes(self, object_name: str, bucket: str = None) -> bytes:
        """Download file content as bytes"""
        bucket = bucket or MINIO_BUCKET
        if not self.client:
            logger.error("MinIO client not initialized")
            return None

        try:
            response = self.client.get_object(bucket, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception as e:
            logger.error(f"Failed to download {object_name} from {bucket}: {e}")
            return None

    def list_objects(self, prefix: str, bucket: str = None) -> list:
        """List objects in a bucket with a specific prefix"""
        bucket = bucket or MINIO_BUCKET
        if not self.client:
            logger.error("MinIO client not initialized")
            return []
            
        try:
            objects = self.client.list_objects(bucket, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects if not obj.is_dir]
        except Exception as e:
            logger.error(f"Failed to list objects in {bucket} with prefix {prefix}: {e}")
            return []

    def get_presigned_url(self, object_name: str, expires_hours: int = 1, bucket: str = None) -> str:
        """Get a presigned URL for the object"""
        bucket = bucket or MINIO_BUCKET
        if not self.client:
            return ""
        
        try:
            return self.client.presigned_get_object(bucket, object_name, expires=timedelta(hours=expires_hours))
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {object_name} in {bucket}: {e}")
            return ""

    def get_presigned_put_url(self, object_name: str, expires_minutes: int = 15, bucket: str = None) -> str:
        """Get a presigned PUT URL for uploading an object directly to MinIO"""
        bucket = bucket or MINIO_BUCKET
        if not self.client:
            return ""
        
        try:
            return self.client.presigned_put_object(bucket, object_name, expires=timedelta(minutes=expires_minutes))
        except Exception as e:
            logger.error(f"Failed to generate presigned PUT URL for {object_name} in {bucket}: {e}")
            return ""

# Global instance
storage = StorageService()
