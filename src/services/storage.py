import asyncio
import logging
from types import SimpleNamespace

import boto3
from botocore.config import Config as BotoConfig
import urllib3

from config import (
    LEGACY_MINIO_ACCESS_KEY,
    LEGACY_MINIO_BUCKET,
    LEGACY_MINIO_ENDPOINT,
    LEGACY_MINIO_PUBLIC_URL,
    LEGACY_MINIO_RESULT_BUCKET,
    LEGACY_MINIO_SECRET_KEY,
    LEGACY_MINIO_SECURE,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_PUBLIC_URL,
    MINIO_RESULT_BUCKET,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    MINIO_TEMPLATE_BUCKET,
    R2_ACCESS_KEY,
    R2_BUCKET,
    R2_ENDPOINT,
    R2_EXISTS_CACHE_MAX_ENTRIES,
    R2_EXISTS_NEGATIVE_TTL_SECONDS,
    R2_EXISTS_POSITIVE_TTL_SECONDS,
    R2_HEAD_CONNECT_TIMEOUT_SECONDS,
    R2_HEAD_MAX_ATTEMPTS,
    R2_HEAD_READ_TIMEOUT_SECONDS,
    R2_HEAD_SEMAPHORE_LIMIT,
    R2_MAX_POOL_CONNECTIONS,
    R2_PUBLIC_DOMAIN,
    R2_SECRET_KEY,
)
from src.database.core import AsyncSessionLocal
from src.services.storage_r2_cleanup import (
    async_delete_r2_objects as async_delete_r2_objects_impl,
    async_prune_user_web_history_r2_cache as async_prune_user_web_history_r2_cache_impl,
    build_history_r2_cleanup_keys as build_history_r2_cleanup_keys_impl,
    sync_delete_r2_object as sync_delete_r2_object_impl,
)
from src.services.storage_minio_client import (
    build_configured_bucket_names,
    build_minio_client,
    build_public_minio_client,
    ensure_bucket_exists,
)

# Stable facade only: bootstrap, object IO, and R2 transfer details should stay in helper modules.
from src.services.storage_presign import (
    generate_presigned_get_url,
    generate_presigned_put_url,
)
from src.services.storage_minio_objects import (
    async_object_exists as async_object_exists_impl,
    download_file as download_file_impl,
    get_file_bytes as get_file_bytes_impl,
    list_objects as list_objects_impl,
    object_exists as object_exists_impl,
    upload_bytes as upload_bytes_impl,
    upload_file as upload_file_impl,
)
from src.services.storage_r2_transfer import (
    async_copy_to_r2 as async_copy_to_r2_impl,
    get_r2_public_url as get_r2_public_url_impl,
    sync_upload_to_r2 as sync_upload_to_r2_impl,
)
from src.services.storage_r2_exists import (
    async_r2_object_exists as async_r2_object_exists_impl,
    async_r2_object_exists_uncached as async_r2_object_exists_uncached_impl,
    attach_r2_inflight_cleanup as attach_r2_inflight_cleanup_impl,
    ensure_r2_async_primitives as ensure_r2_async_primitives_impl,
    get_r2_exists_cache as get_r2_exists_cache_impl,
    get_r2_exists_cache_entry_locked as get_r2_exists_cache_entry_locked_impl,
    has_newer_positive_r2_exists_cache as has_newer_positive_r2_exists_cache_impl,
    init_r2_runtime_state as init_r2_runtime_state_impl,
    invalidate_r2_exists_cache as invalidate_r2_exists_cache_impl,
    mark_r2_object_exists as mark_r2_object_exists_impl,
    remove_r2_inflight_task as remove_r2_inflight_task_impl,
    r2_object_exists_with_cache_hint as r2_object_exists_with_cache_hint_impl,
    set_r2_exists_cache as set_r2_exists_cache_impl,
    trim_r2_exists_cache_locked as trim_r2_exists_cache_locked_impl,
)

logger = logging.getLogger(__name__)


class StorageService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StorageService, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_r2_runtime_state(self):
        init_r2_runtime_state_impl(
            self,
            positive_ttl=R2_EXISTS_POSITIVE_TTL_SECONDS,
            negative_ttl=R2_EXISTS_NEGATIVE_TTL_SECONDS,
            max_entries=R2_EXISTS_CACHE_MAX_ENTRIES,
            semaphore_limit=R2_HEAD_SEMAPHORE_LIMIT,
        )

    def _ensure_r2_async_primitives(self):
        ensure_r2_async_primitives_impl(self)

    def _trim_r2_exists_cache_locked(self):
        trim_r2_exists_cache_locked_impl(self)

    def _get_r2_exists_cache_entry_locked(
        self, object_name: str, now: float
    ) -> tuple[bool, float, float] | None:
        return get_r2_exists_cache_entry_locked_impl(self, object_name, now)

    def _get_r2_exists_cache(self, object_name: str):
        return get_r2_exists_cache_impl(self, object_name)

    def _set_r2_exists_cache(self, object_name: str, exists: bool):
        set_r2_exists_cache_impl(self, object_name, exists)

    def _has_newer_positive_r2_exists_cache(
        self, object_name: str, probe_started_at: float
    ) -> bool:
        return has_newer_positive_r2_exists_cache_impl(
            self, object_name, probe_started_at
        )

    def invalidate_r2_exists_cache(self, object_name: str):
        invalidate_r2_exists_cache_impl(self, object_name)

    def mark_r2_object_exists(self, object_name: str):
        mark_r2_object_exists_impl(self, object_name)

    async def _remove_r2_inflight_task(self, object_name: str, task: asyncio.Task):
        await remove_r2_inflight_task_impl(self, object_name, task)

    def _attach_r2_inflight_cleanup(self, object_name: str, task: asyncio.Task):
        attach_r2_inflight_cleanup_impl(self, object_name, task)

    def _init_client(self):
        self._init_r2_runtime_state()
        self.legacy_client = None
        self.legacy_public_client = None
        try:
            self._minio_http_client = urllib3.PoolManager(
                maxsize=100,
                num_pools=100,
                retries=False,
            )
            configured_buckets = build_configured_bucket_names(
                MINIO_BUCKET,
                MINIO_TEMPLATE_BUCKET,
                MINIO_RESULT_BUCKET,
            )
            self.client = build_minio_client(
                endpoint=MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE,
                bucket_names=configured_buckets,
                http_client=self._minio_http_client,
            )

            if MINIO_PUBLIC_URL:
                self.public_client = build_public_minio_client(
                    public_url=MINIO_PUBLIC_URL,
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    bucket_names=configured_buckets,
                    http_client=self._minio_http_client,
                )
            else:
                self.public_client = None

            ensure_bucket_exists(
                self.client,
                bucket_name=MINIO_BUCKET,
                logger=logger,
                label="main",
            )
            ensure_bucket_exists(
                self.client,
                bucket_name=MINIO_TEMPLATE_BUCKET,
                logger=logger,
                label="template",
            )
            ensure_bucket_exists(
                self.client,
                bucket_name=MINIO_RESULT_BUCKET,
                logger=logger,
                label="result",
            )

        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            self.client = None
            self.public_client = None

        self._init_legacy_minio_client()

        # Initialize Cloudflare R2 client
        try:
            if R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY:
                self.r2_client = boto3.client(
                    "s3",
                    endpoint_url=R2_ENDPOINT,
                    aws_access_key_id=R2_ACCESS_KEY,
                    aws_secret_access_key=R2_SECRET_KEY,
                    config=BotoConfig(
                        signature_version="s3v4",
                        max_pool_connections=R2_MAX_POOL_CONNECTIONS,
                    ),
                    region_name="auto",
                )
                self.r2_head_client = boto3.client(
                    "s3",
                    endpoint_url=R2_ENDPOINT,
                    aws_access_key_id=R2_ACCESS_KEY,
                    aws_secret_access_key=R2_SECRET_KEY,
                    config=BotoConfig(
                        signature_version="s3v4",
                        max_pool_connections=R2_MAX_POOL_CONNECTIONS,
                        connect_timeout=R2_HEAD_CONNECT_TIMEOUT_SECONDS,
                        read_timeout=R2_HEAD_READ_TIMEOUT_SECONDS,
                        retries={"max_attempts": R2_HEAD_MAX_ATTEMPTS},
                    ),
                    region_name="auto",
                )
                self.r2_bucket = R2_BUCKET
                logger.info("Cloudflare R2 client initialized for gallery")
            else:
                self.r2_client = None
                self.r2_head_client = None
                logger.warning(
                    "R2 configuration missing, gallery upload will be disabled"
                )
        except Exception as e:
            logger.error(f"Failed to init R2 client: {e}")
            self.r2_client = None
            self.r2_head_client = None

    def _init_legacy_minio_client(self):
        if not (
            LEGACY_MINIO_ENDPOINT
            and LEGACY_MINIO_ACCESS_KEY
            and LEGACY_MINIO_SECRET_KEY
        ):
            return

        try:
            self._legacy_minio_http_client = urllib3.PoolManager(
                maxsize=32,
                num_pools=32,
                retries=False,
            )
            legacy_buckets = build_configured_bucket_names(
                LEGACY_MINIO_BUCKET,
                LEGACY_MINIO_RESULT_BUCKET,
            )
            self.legacy_client = build_minio_client(
                endpoint=LEGACY_MINIO_ENDPOINT,
                access_key=LEGACY_MINIO_ACCESS_KEY,
                secret_key=LEGACY_MINIO_SECRET_KEY,
                secure=LEGACY_MINIO_SECURE,
                bucket_names=legacy_buckets,
                http_client=self._legacy_minio_http_client,
            )
            if LEGACY_MINIO_PUBLIC_URL:
                self.legacy_public_client = build_public_minio_client(
                    public_url=LEGACY_MINIO_PUBLIC_URL,
                    access_key=LEGACY_MINIO_ACCESS_KEY,
                    secret_key=LEGACY_MINIO_SECRET_KEY,
                    bucket_names=legacy_buckets,
                    http_client=self._legacy_minio_http_client,
                )
            logger.info("Legacy MinIO read-only fallback initialized")
        except Exception as e:
            logger.error(f"Failed to initialize legacy MinIO client: {e}")
            self.legacy_client = None
            self.legacy_public_client = None

    def _sync_upload_to_r2(
        self, bucket_name: str, object_name: str, r2_object_name: str = None
    ):
        return sync_upload_to_r2_impl(
            self,
            bucket_name=bucket_name,
            object_name=object_name,
            r2_object_name=r2_object_name,
            logger=logger,
        )

    async def async_copy_to_r2(
        self, bucket_name: str, object_name: str, r2_object_name: str = None
    ):
        return await async_copy_to_r2_impl(
            self,
            bucket_name=bucket_name,
            object_name=object_name,
            r2_object_name=r2_object_name,
            logger=logger,
        )

    def _sync_copy_legacy_to_r2(
        self,
        bucket_name: str,
        object_name: str,
        r2_object_name: str = None,
    ) -> bool:
        if not self.legacy_client or not self.r2_client or not self.r2_bucket:
            return False

        target_name = r2_object_name or object_name
        response = None
        try:
            response = self.legacy_client.get_object(bucket_name, object_name)
            self.r2_client.upload_fileobj(response, self.r2_bucket, target_name)
            self.mark_r2_object_exists(target_name)
            return True
        except Exception as exc:
            logger.error(
                "Failed to copy legacy object %s/%s to R2 %s/%s: %s",
                bucket_name,
                object_name,
                self.r2_bucket,
                target_name,
                exc,
            )
            return False
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    async def async_copy_legacy_to_r2(
        self,
        bucket_name: str,
        object_name: str,
        r2_object_name: str = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._sync_copy_legacy_to_r2,
            bucket_name,
            object_name,
            r2_object_name,
        )

    def _sync_delete_r2_object(self, object_name: str) -> bool:
        return sync_delete_r2_object_impl(self, object_name)

    async def async_delete_r2_objects(self, object_names: list[str]) -> int:
        return await async_delete_r2_objects_impl(self, object_names)

    def _build_history_r2_cleanup_keys(
        self, task_id: str, output_file: str, history_type: str | None
    ) -> set[str]:
        return build_history_r2_cleanup_keys_impl(task_id, output_file, history_type)

    async def async_prune_user_web_history_r2_cache(
        self, user_id: int, keep_recent: int = 8
    ) -> None:
        await async_prune_user_web_history_r2_cache_impl(
            self,
            user_id,
            keep_recent,
            async_session_factory=AsyncSessionLocal,
            async_delete_r2_objects_func=lambda service, object_names: service.async_delete_r2_objects(
                object_names
            ),
        )

    def upload_file(
        self,
        file_path: str,
        object_name: str,
        bucket_name: str = None,
        *,
        bucket: str = None,
    ) -> bool:
        """Upload a local file to MinIO."""
        return upload_file_impl(
            self,
            file_path=file_path,
            object_name=object_name,
            bucket_name=bucket_name,
            bucket=bucket,
            logger=logger,
        )

    def upload_bytes(
        self,
        data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
        bucket: str = None,
    ) -> str:
        """Upload bytes to MinIO."""
        return upload_bytes_impl(
            self,
            data=data,
            object_name=object_name,
            content_type=content_type,
            bucket=bucket,
            logger=logger,
        )

    def get_file_bytes(self, object_name: str, bucket: str = None) -> bytes:
        """Download file content as bytes."""
        return get_file_bytes_impl(
            self,
            object_name=object_name,
            bucket=bucket,
            logger=logger,
        )

    def list_objects(self, prefix: str, bucket: str = None) -> list:
        """List objects in a bucket with a specific prefix."""
        return list_objects_impl(
            self,
            prefix=prefix,
            bucket=bucket,
            logger=logger,
        )

    def object_exists(self, bucket_name: str, object_name: str) -> bool:
        """检查对象是否存在."""
        return object_exists_impl(
            self,
            bucket_name=bucket_name,
            object_name=object_name,
            logger=logger,
        )

    async def async_object_exists(self, bucket_name: str, object_name: str) -> bool:
        return await async_object_exists_impl(
            self,
            bucket_name=bucket_name,
            object_name=object_name,
            logger=logger,
        )

    def has_legacy_storage_configured(self) -> bool:
        return bool(self.legacy_client)

    def legacy_object_exists(self, bucket_name: str, object_name: str) -> bool:
        if not self.legacy_client:
            return False
        legacy_service = SimpleNamespace(client=self.legacy_client)
        return object_exists_impl(
            legacy_service,
            bucket_name=bucket_name,
            object_name=object_name,
            logger=logger,
        )

    async def async_legacy_object_exists(
        self,
        bucket_name: str,
        object_name: str,
    ) -> bool:
        return await asyncio.to_thread(
            self.legacy_object_exists,
            bucket_name,
            object_name,
        )

    def get_legacy_presigned_url(
        self,
        object_name: str,
        expires_hours: float = 1,
        bucket: str = None,
        download: bool = False,
    ) -> str:
        if not self.legacy_client:
            return ""
        if not bucket:
            bucket = LEGACY_MINIO_BUCKET

        try:
            legacy_service = SimpleNamespace(
                client=self.legacy_client,
                public_client=self.legacy_public_client,
            )
            return generate_presigned_get_url(
                legacy_service,
                bucket_name=bucket,
                object_name=object_name,
                expires_hours=expires_hours,
                download=download,
            )
        except Exception as e:
            logger.error(
                "Failed to generate legacy presigned URL for %s in %s: %s",
                object_name,
                bucket,
                e,
            )
            return ""

    def _r2_object_exists_with_cache_hint(self, object_name: str) -> tuple[bool, bool]:
        return r2_object_exists_with_cache_hint_impl(self, object_name, logger=logger)

    def r2_object_exists(self, object_name: str) -> bool:
        exists, _ = self._r2_object_exists_with_cache_hint(object_name)
        return exists

    async def _async_r2_object_exists_uncached(self, object_name: str) -> bool:
        return await async_r2_object_exists_uncached_impl(
            self, object_name, logger=logger
        )

    async def async_r2_object_exists(self, object_name: str) -> bool:
        return await async_r2_object_exists_impl(self, object_name, logger=logger)

    def get_r2_public_url(self, object_name: str) -> str:
        return get_r2_public_url_impl(
            object_name=object_name,
            public_domain=R2_PUBLIC_DOMAIN,
        )
            
    def download_file(self, bucket_name: str, object_name: str, file_path: str):
        """将对象下载到本地文件."""
        download_file_impl(
            self,
            bucket_name=bucket_name,
            object_name=object_name,
            file_path=file_path,
        )

    def get_presigned_url(
        self,
        object_name: str,
        expires_hours: float = 1,
        bucket: str = None,
        download: bool = False,
    ) -> str:
        """Generate a presigned URL for downloading an object."""
        bucket_name = bucket or MINIO_BUCKET
        if not self.client:
            logger.error("MinIO client not initialized")
            return ""

        try:
            return generate_presigned_get_url(
                self,
                bucket_name=bucket_name,
                object_name=object_name,
                expires_hours=expires_hours,
                download=download,
            )
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {object_name} in {bucket_name}: {e}")
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
            _ = content_type
            return generate_presigned_put_url(
                self,
                bucket_name=bucket,
                object_name=object_name,
                expires_minutes=expires_minutes,
            )
        except Exception as e:
            logger.error(
                f"Failed to generate presigned PUT URL for {object_name} in {bucket}: {e}"
            )
            return ""


# Global instance
storage = StorageService()
