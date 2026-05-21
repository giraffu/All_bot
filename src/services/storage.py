import asyncio
import io
import logging
import threading
import time
from datetime import timedelta

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from minio import Minio
from sqlalchemy import select
import urllib3

from config import (
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
    R2_HEAD_SEMAPHORE_LIMIT,
    R2_MAX_POOL_CONNECTIONS,
    R2_PUBLIC_DOMAIN,
    R2_SECRET_KEY,
)
from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_legacy_r2_key,
    build_thumbnail_object_name,
    get_media_type_from_history,
    resolve_storage_object,
)
from src.database.core import AsyncSessionLocal
from src.database.models import History

logger = logging.getLogger(__name__)


class StorageService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StorageService, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_r2_runtime_state(self):
        self._r2_exists_cache = {}
        self._r2_exists_cache_lock = threading.Lock()
        self._r2_exists_positive_ttl = max(1, R2_EXISTS_POSITIVE_TTL_SECONDS)
        self._r2_exists_negative_ttl = max(1, R2_EXISTS_NEGATIVE_TTL_SECONDS)
        self._r2_exists_cache_max_entries = max(100, R2_EXISTS_CACHE_MAX_ENTRIES)
        self._r2_head_semaphore_limit = max(1, R2_HEAD_SEMAPHORE_LIMIT)
        self._r2_head_semaphore = None
        self._r2_exists_inflight_lock = None
        self._r2_exists_inflight = {}
        self._r2_async_primitives_loop = None

    def _ensure_r2_async_primitives(self):
        loop = asyncio.get_running_loop()
        if self._r2_async_primitives_loop is loop:
            return

        self._r2_async_primitives_loop = loop
        self._r2_head_semaphore = asyncio.Semaphore(self._r2_head_semaphore_limit)
        self._r2_exists_inflight_lock = asyncio.Lock()
        self._r2_exists_inflight = {}

    def _trim_r2_exists_cache_locked(self):
        if len(self._r2_exists_cache) <= self._r2_exists_cache_max_entries:
            return

        now = time.monotonic()
        expired_keys = [
            key
            for key, (_, expires_at, _) in self._r2_exists_cache.items()
            if expires_at <= now
        ]
        for key in expired_keys:
            self._r2_exists_cache.pop(key, None)

        while len(self._r2_exists_cache) > self._r2_exists_cache_max_entries:
            oldest_key = next(iter(self._r2_exists_cache))
            self._r2_exists_cache.pop(oldest_key, None)

    def _get_r2_exists_cache_entry_locked(
        self, object_name: str, now: float
    ) -> tuple[bool, float, float] | None:
        entry = self._r2_exists_cache.get(object_name)
        if not entry:
            return None

        exists, expires_at, updated_at = entry
        if expires_at <= now:
            self._r2_exists_cache.pop(object_name, None)
            return None

        return exists, expires_at, updated_at

    def _get_r2_exists_cache(self, object_name: str):
        if not object_name:
            return None

        now = time.monotonic()
        with self._r2_exists_cache_lock:
            entry = self._get_r2_exists_cache_entry_locked(object_name, now)
            if not entry:
                return None
            return entry[0]

    def _set_r2_exists_cache(self, object_name: str, exists: bool):
        if not object_name:
            return

        ttl = (
            self._r2_exists_positive_ttl
            if exists
            else self._r2_exists_negative_ttl
        )
        updated_at = time.monotonic()
        expires_at = updated_at + ttl
        with self._r2_exists_cache_lock:
            self._r2_exists_cache[object_name] = (exists, expires_at, updated_at)
            self._trim_r2_exists_cache_locked()

    def _has_newer_positive_r2_exists_cache(
        self, object_name: str, probe_started_at: float
    ) -> bool:
        now = time.monotonic()
        with self._r2_exists_cache_lock:
            entry = self._get_r2_exists_cache_entry_locked(object_name, now)
            if not entry:
                return False

            exists, _, updated_at = entry
            return exists is True and updated_at > probe_started_at

    def invalidate_r2_exists_cache(self, object_name: str):
        if not object_name:
            return
        with self._r2_exists_cache_lock:
            self._r2_exists_cache.pop(object_name, None)

    def mark_r2_object_exists(self, object_name: str):
        self._set_r2_exists_cache(object_name, True)

    async def _remove_r2_inflight_task(self, object_name: str, task: asyncio.Task):
        if self._r2_exists_inflight_lock is None:
            return

        async with self._r2_exists_inflight_lock:
            if self._r2_exists_inflight.get(object_name) is task:
                self._r2_exists_inflight.pop(object_name, None)

    def _attach_r2_inflight_cleanup(self, object_name: str, task: asyncio.Task):
        def _cleanup(done_task: asyncio.Task):
            loop = done_task.get_loop()
            if loop.is_closed():
                return
            loop.create_task(self._remove_r2_inflight_task(object_name, done_task))

        task.add_done_callback(_cleanup)

    def _init_client(self):
        self._init_r2_runtime_state()
        try:
            self._minio_http_client = urllib3.PoolManager(
                maxsize=100,
                num_pools=100,
                retries=False,
            )
            self.client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE,
                http_client=self._minio_http_client,
            )

            # CRITICAL FIX: Inject region mapping to prevent synchronous `?location=` network calls
            # from blocking the event loop when MinIO is slow or overloaded.
            self.client._region_map[MINIO_BUCKET] = "us-east-1"
            if MINIO_TEMPLATE_BUCKET:
                self.client._region_map[MINIO_TEMPLATE_BUCKET] = "us-east-1"
            if MINIO_RESULT_BUCKET:
                self.client._region_map[MINIO_RESULT_BUCKET] = "us-east-1"
            
            # 必须补充新增的桶映射，防止签名时触发同步网络阻塞
            self.client._region_map["comfyui-temp"] = "us-east-1"
            self.client._region_map["bot-data"] = "us-east-1"

            if MINIO_PUBLIC_URL:
                public_host = MINIO_PUBLIC_URL.replace("https://", "").replace("http://", "")
                secure = MINIO_PUBLIC_URL.startswith("https")
                self.public_client = Minio(
                    public_host,
                    access_key=MINIO_ACCESS_KEY,
                    secret_key=MINIO_SECRET_KEY,
                    secure=secure,
                    region="us-east-1",
                    http_client=self._minio_http_client,
                )
                self.public_client._region_map[MINIO_BUCKET] = "us-east-1"
                if MINIO_TEMPLATE_BUCKET:
                    self.public_client._region_map[MINIO_TEMPLATE_BUCKET] = "us-east-1"
                if MINIO_RESULT_BUCKET:
                    self.public_client._region_map[MINIO_RESULT_BUCKET] = "us-east-1"
                self.public_client._region_map["comfyui-temp"] = "us-east-1"
                self.public_client._region_map["bot-data"] = "us-east-1"
            else:
                self.public_client = None

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

            if MINIO_RESULT_BUCKET and not self.client.bucket_exists(MINIO_RESULT_BUCKET):
                try:
                    self.client.make_bucket(MINIO_RESULT_BUCKET)
                    logger.info(f"Created MinIO result bucket: {MINIO_RESULT_BUCKET}")
                except Exception as e:
                    logger.error(
                        f"Failed to create result bucket {MINIO_RESULT_BUCKET}: {e}"
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
                    config=BotoConfig(
                        signature_version="s3v4",
                        max_pool_connections=R2_MAX_POOL_CONNECTIONS,
                    ),
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
            return False

        r2_key = r2_object_name or object_name.split("/")[-1]

        try:
            # Get object from MinIO
            response = self.client.get_object(bucket_name, object_name)
            content_type = response.headers.get(
                "Content-Type", "application/octet-stream"
            )

            # Stream the MinIO response to R2 to avoid loading large media files fully into memory.
            extra_args = {"ContentType": content_type} if content_type else None
            self.r2_client.upload_fileobj(
                response,
                self.r2_bucket,
                r2_key,
                ExtraArgs=extra_args,
            )
            self.mark_r2_object_exists(r2_key)
            logger.info(
                f"Successfully copied {object_name} to R2 bucket {self.r2_bucket} as {r2_key}"
            )
            return True
        except Exception as e:
            self.invalidate_r2_exists_cache(r2_key)
            logger.error(f"Failed to copy {object_name} to R2: {e}")
            return False
        finally:
            if "response" in locals():
                response.close()
                response.release_conn()

    async def async_copy_to_r2(
        self, bucket_name: str, object_name: str, r2_object_name: str = None
    ):
        """Async wrapper to copy from MinIO to R2 without blocking"""
        if not self.r2_client:
            return False
        return await asyncio.to_thread(
            self._sync_upload_to_r2, bucket_name, object_name, r2_object_name
        )

    def _sync_delete_r2_object(self, object_name: str) -> bool:
        if not self.r2_client or not self.r2_bucket or not object_name:
            return False

        try:
            self.r2_client.delete_object(Bucket=self.r2_bucket, Key=object_name)
            self.invalidate_r2_exists_cache(object_name)
            logger.info("Deleted R2 object: %s", object_name)
            return True
        except ClientError as exc:
            error = exc.response.get("Error", {}) if exc.response else {}
            code = str(error.get("Code", ""))
            status_code = (
                exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if exc.response
                else None
            )
            if code in {"404", "NoSuchKey", "NotFound"} or status_code == 404:
                self.invalidate_r2_exists_cache(object_name)
                logger.info("R2 object already absent, skip delete: %s", object_name)
                return True

            logger.warning("Failed to delete R2 object %s: %s", object_name, exc)
            return False
        except Exception as exc:
            logger.warning("Failed to delete R2 object %s: %s", object_name, exc)
            return False

    async def async_delete_r2_objects(self, object_names: list[str]) -> int:
        if not object_names or not self.r2_client or not self.r2_bucket:
            return 0

        deleted_count = 0
        seen = set()
        for object_name in object_names:
            if not object_name or object_name in seen:
                continue
            seen.add(object_name)
            if await asyncio.to_thread(self._sync_delete_r2_object, object_name):
                deleted_count += 1
        return deleted_count

    def _build_history_r2_cleanup_keys(
        self, task_id: str, output_file: str, history_type: str | None
    ) -> set[str]:
        if not task_id or not output_file:
            return set()

        media_type = get_media_type_from_history(history_type)
        _, object_name = resolve_storage_object(output_file)
        thumb_object_name = build_thumbnail_object_name(object_name, media_type)

        return {
            key
            for key in {
                build_history_r2_media_key(task_id, output_file),
                build_history_r2_thumbnail_key(task_id, media_type),
                build_legacy_r2_key(object_name),
                build_legacy_r2_key(thumb_object_name),
            }
            if key
        }

    async def async_prune_user_web_history_r2_cache(
        self, user_id: int, keep_recent: int = 8
    ) -> None:
        if not self.r2_client or not self.r2_bucket or not user_id:
            return

        async with AsyncSessionLocal() as session:
            overflow_stmt = (
                select(
                    History.task_id,
                    History.output_file,
                    History.type,
                )
                .where(
                    History.user_id == user_id,
                    History.source == "web",
                    History.is_favorited.is_(False),
                    History.is_public.is_(False),
                    History.task_id.is_not(None),
                    History.output_file.is_not(None),
                )
                .order_by(History.created_at.desc())
                .offset(keep_recent)
                .limit(1)
            )
            overflow_row = (await session.execute(overflow_stmt)).first()

        if not overflow_row:
            logger.info(
                "Incremental prune skipped for user %s: no overflow web history beyond %s",
                user_id,
                keep_recent,
            )
            return

        task_id, output_file, history_type = overflow_row
        delete_keys = self._build_history_r2_cleanup_keys(
            task_id, output_file, history_type
        )

        deleted_count = await self.async_delete_r2_objects(list(delete_keys))
        logger.info(
            "Incrementally pruned user %s web history R2 cache: overflow_task=%s delete_keys=%s deleted=%s",
            user_id,
            task_id,
            len(delete_keys),
            deleted_count,
        )

    def upload_file(self, file_path: str, object_name: str, bucket_name: str = None) -> bool:
        """Upload a local file to MinIO"""
        bucket = bucket_name or MINIO_BUCKET
        if not self.client:
            logger.error("MinIO client not initialized")
            return False

        try:
            self.client.fput_object(bucket, object_name, file_path)
            return True
        except Exception as e:
            logger.error(f"Failed to upload file {file_path} to {bucket}/{object_name}: {e}")
            return False

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

    def object_exists(self, bucket_name: str, object_name: str) -> bool:
        """检查对象是否存在"""
        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error as exc:
            code = getattr(exc, "code", "")
            if code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                return False
            logger.warning(
                "MinIO stat_object failed for %s/%s: %s",
                bucket_name,
                object_name,
                exc,
            )
            return False
        except Exception as exc:
            logger.warning(
                "Unexpected object_exists failure for %s/%s: %s",
                bucket_name,
                object_name,
                exc,
            )
            return False

    async def async_object_exists(self, bucket_name: str, object_name: str) -> bool:
        return await asyncio.to_thread(self.object_exists, bucket_name, object_name)

    def _r2_object_exists_with_cache_hint(self, object_name: str) -> tuple[bool, bool]:
        if not self.r2_client or not self.r2_bucket:
            return False, False
        try:
            self.r2_client.head_object(Bucket=self.r2_bucket, Key=object_name)
            return True, True
        except ClientError as exc:
            error = exc.response.get("Error", {}) if exc.response else {}
            code = str(error.get("Code", ""))
            status_code = (
                exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if exc.response
                else None
            )
            if code in {"404", "NoSuchKey", "NotFound"} or status_code == 404:
                return False, True

            logger.warning(
                "R2 head_object failed for %s with cache skipped: code=%s status=%s",
                object_name,
                code or "unknown",
                status_code,
            )
            return False, False
        except Exception as exc:
            logger.warning(
                "R2 head_object raised transient error for %s, skip negative cache: %s",
                object_name,
                exc,
            )
            return False, False

    def r2_object_exists(self, object_name: str) -> bool:
        exists, _ = self._r2_object_exists_with_cache_hint(object_name)
        return exists

    async def _async_r2_object_exists_uncached(self, object_name: str) -> bool:
        probe_started_at = time.monotonic()
        async with self._r2_head_semaphore:
            exists, cacheable = await asyncio.to_thread(
                self._r2_object_exists_with_cache_hint, object_name
            )
        if cacheable:
            # Preserve the latest write-after-copy state when an older HEAD result
            # returns after the object has already been uploaded successfully.
            if not exists and self._has_newer_positive_r2_exists_cache(
                object_name, probe_started_at
            ):
                return True
            self._set_r2_exists_cache(object_name, exists)
        return exists

    async def async_r2_object_exists(self, object_name: str) -> bool:
        if not object_name:
            return False

        cached = self._get_r2_exists_cache(object_name)
        if cached is not None:
            return cached

        if not self.r2_client or not self.r2_bucket:
            return False

        self._ensure_r2_async_primitives()

        async with self._r2_exists_inflight_lock:
            cached = self._get_r2_exists_cache(object_name)
            if cached is not None:
                return cached

            inflight_task = self._r2_exists_inflight.get(object_name)
            if inflight_task is None:
                inflight_task = asyncio.create_task(
                    self._async_r2_object_exists_uncached(object_name)
                )
                self._r2_exists_inflight[object_name] = inflight_task
                self._attach_r2_inflight_cleanup(object_name, inflight_task)
        return await asyncio.shield(inflight_task)

    def get_r2_public_url(self, object_name: str) -> str:
        if not R2_PUBLIC_DOMAIN or not object_name:
            return ""
        base_url = R2_PUBLIC_DOMAIN.rstrip("/")
        return f"{base_url}/{object_name.lstrip('/')}"
            
    def download_file(self, bucket_name: str, object_name: str, file_path: str):
        """将对象下载到本地文件"""
        self.client.fget_object(bucket_name, object_name, file_path)

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
            response_headers = {}
            if download:
                filename = object_name.split("/")[-1]
                response_headers["response-content-disposition"] = (
                    f'attachment; filename="{filename}"'
                )

            from datetime import timedelta
            # 兼容：原来的 expires_hours 表示小时，现在我们在 media_processor 里其实传入的是秒，
            # 为了防止冲突，我们可以做个简单的判断，如果传入的值 > 24，我们认为它是秒，否则是小时
            if expires_hours > 24:
                expire_time = timedelta(seconds=float(expires_hours))
            else:
                expire_time = timedelta(hours=float(expires_hours))

            if hasattr(self, 'public_client') and self.public_client:
                url = self.public_client.presigned_get_object(
                    bucket_name,
                    object_name,
                    expires=expire_time,
                    response_headers=response_headers,
                )
            else:
                url = self.client.presigned_get_object(
                    bucket_name,
                    object_name,
                    expires=expire_time,
                    response_headers=response_headers,
                )
            return url
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
            # The Ultimate Fix for 403 SignatureDoesNotMatch with MinIO behind Cloudflare/Nginx:
            # 1. The signature MUST be calculated using the EXACT Host header the browser will send.
            # 2. We MUST initialize a temporary Minio client with the public URL to sign it correctly.
            # 3. We MUST avoid using `region` or other params that trigger network calls in older SDKs.

            if hasattr(self, 'public_client') and self.public_client:
                # Ensure expires_minutes is a float to avoid TypeError with string from config
                url = self.public_client.presigned_put_object(
                    bucket_name=bucket,
                    object_name=object_name,
                    expires=timedelta(minutes=float(expires_minutes)),
                )
            else:
                url = self.client.presigned_put_object(
                    bucket_name=bucket,
                    object_name=object_name,
                    expires=timedelta(minutes=float(expires_minutes)),
                )

            return url
        except Exception as e:
            logger.error(
                f"Failed to generate presigned PUT URL for {object_name} in {bucket}: {e}"
            )
            return ""


# Global instance
storage = StorageService()
