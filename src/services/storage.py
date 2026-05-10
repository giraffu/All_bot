import asyncio
import io
import logging
from datetime import timedelta

import boto3
from botocore.config import Config as BotoConfig
from minio import Minio

from config import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    MINIO_TEMPLATE_BUCKET,
    R2_ACCESS_KEY,
    R2_BUCKET,
    R2_ENDPOINT,
    R2_SECRET_KEY,
)

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
                secure=MINIO_SECURE,
            )

            # CRITICAL FIX: Inject region mapping to prevent synchronous `?location=` network calls
            # from blocking the event loop when MinIO is slow or overloaded.
            self.client._region_map[MINIO_BUCKET] = "us-east-1"
            if MINIO_TEMPLATE_BUCKET:
                self.client._region_map[MINIO_TEMPLATE_BUCKET] = "us-east-1"

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
                    logger.info(
                        f"Created MinIO template bucket: {MINIO_TEMPLATE_BUCKET}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to create template bucket {MINIO_TEMPLATE_BUCKET}: {e}"
                    )

        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            self.client = None

        # Initialize Cloudflare R2 client
        try:
            if R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY:
                self.r2_client = boto3.client(
                    "s3",
                    endpoint_url=R2_ENDPOINT,
                    aws_access_key_id=R2_ACCESS_KEY,
                    aws_secret_access_key=R2_SECRET_KEY,
                    config=BotoConfig(signature_version="s3v4"),
                    region_name="auto",
                )
                self.r2_bucket = R2_BUCKET
                logger.info("Cloudflare R2 client initialized for gallery")
            else:
                self.r2_client = None
                logger.warning(
                    "R2 configuration missing, gallery upload will be disabled"
                )
        except Exception as e:
            logger.error(f"Failed to init R2 client: {e}")
            self.r2_client = None

    def _sync_upload_to_r2(
        self, bucket_name: str, object_name: str, r2_object_name: str = None
    ):
        """Sync function to copy from MinIO to R2, meant to run in a thread"""
        if not self.r2_client:
            logger.error("R2 client not initialized")
            return

        r2_key = r2_object_name or object_name.split("/")[-1]

        try:
            # Get object from MinIO
            response = self.client.get_object(bucket_name, object_name)
            file_data = response.read()
            content_type = response.headers.get(
                "Content-Type", "application/octet-stream"
            )

            # Upload to R2
            self.r2_client.put_object(
                Bucket=self.r2_bucket,
                Key=r2_key,
                Body=file_data,
                ContentType=content_type,
            )
            logger.info(
                f"Successfully copied {object_name} to R2 bucket {self.r2_bucket} as {r2_key}"
            )
        except Exception as e:
            logger.error(f"Failed to copy {object_name} to R2: {e}")
        finally:
            if "response" in locals():
                response.close()
                response.release_conn()

    async def async_copy_to_r2(
        self, bucket_name: str, object_name: str, r2_object_name: str = None
    ):
        """Async wrapper to copy from MinIO to R2 without blocking"""
        if not self.r2_client:
            return
        await asyncio.to_thread(
            self._sync_upload_to_r2, bucket_name, object_name, r2_object_name
        )

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
            logger.error(
                f"Failed to upload file {file_path} to {object_name} in {bucket}: {e}"
            )
            return ""

    def upload_bytes(
        self,
        data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
        bucket: str = None,
    ) -> str:
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
                content_type=content_type,
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
            logger.error(
                f"Failed to list objects in {bucket} with prefix {prefix}: {e}"
            )
            return []

    def get_presigned_url(
        self,
        object_name: str,
        expires_hours: int = 1,
        bucket: str = None,
        download: bool = False,
    ) -> str:
        """Get a presigned URL for the object"""
        bucket = bucket or MINIO_BUCKET
        if not self.client:
            return ""

        try:
            response_headers = {}
            if download:
                filename = object_name.split("/")[-1]
                response_headers = {
                    "response-content-disposition": f'attachment; filename="{filename}"'
                }

            from config import (
                MINIO_ACCESS_KEY,
                MINIO_PUBLIC_URL,
                MINIO_SECRET_KEY,
            )

            if MINIO_PUBLIC_URL:
                public_host = (
                    MINIO_PUBLIC_URL.replace("https://", "")
                    .replace("http://", "")
                    .rstrip("/")
                )
                secure = MINIO_PUBLIC_URL.startswith("https")

                # Using a fresh client purely for offline signature generation
                public_client = Minio(
                    public_host,
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    secure=secure,
                    region="us-east-1",
                )

                # Force offline signature calculation
                public_client._region_map[bucket] = "us-east-1"

                url = public_client.presigned_get_object(
                    bucket_name=bucket,
                    object_name=object_name,
                    expires=timedelta(hours=expires_hours),
                    response_headers=response_headers if response_headers else None,
                )
            else:
                url = self.client.presigned_get_object(
                    bucket,
                    object_name,
                    expires=timedelta(hours=expires_hours),
                    response_headers=response_headers if response_headers else None,
                )

            return url
        except Exception as e:
            logger.error(
                f"Failed to generate presigned URL for {object_name} in {bucket}: {e}"
            )
            return ""

    def get_presigned_put_url(
        self,
        object_name: str,
        expires_minutes: int = 15,
        bucket: str = None,
        content_type: str = None,
    ) -> str:
        """Get a presigned PUT URL for uploading an object directly to MinIO"""
        bucket = bucket or MINIO_BUCKET
        if not self.client:
            return ""

        try:
            from config import (
                MINIO_ACCESS_KEY,
                MINIO_PUBLIC_URL,
                MINIO_SECRET_KEY,
            )

            # The Ultimate Fix for 403 SignatureDoesNotMatch with MinIO behind Cloudflare/Nginx:
            # 1. The signature MUST be calculated using the EXACT Host header the browser will send.
            # 2. We MUST initialize a temporary Minio client with the public URL to sign it correctly.
            # 3. We MUST avoid using `region` or other params that trigger network calls in older SDKs.

            if MINIO_PUBLIC_URL:
                public_host = MINIO_PUBLIC_URL.replace("https://", "").replace(
                    "http://", ""
                )
                secure = MINIO_PUBLIC_URL.startswith("https")

                # Using a fresh client purely for offline signature generation
                public_client = Minio(
                    public_host,
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    secure=secure,
                    region="us-east-1",
                )

                # CRITICAL FIX for `?location=` network call crashing with 403:
                # The python minio client tries to dynamically discover the bucket's region over the network
                # before signing the URL. Since our public_host is behind a proxy, this internal network
                # request gets rejected. We MUST manually inject the region into its internal cache
                # to force it to do 100% offline signature calculation.
                public_client._region_map[bucket] = "us-east-1"

                url = public_client.presigned_put_object(
                    bucket_name=bucket,
                    object_name=object_name,
                    expires=timedelta(minutes=expires_minutes),
                )
            else:
                url = self.client.presigned_put_object(
                    bucket_name=bucket,
                    object_name=object_name,
                    expires=timedelta(minutes=expires_minutes),
                )

            return url
        except Exception as e:
            logger.error(
                f"Failed to generate presigned PUT URL for {object_name} in {bucket}: {e}"
            )
            return ""


# Global instance
storage = StorageService()
