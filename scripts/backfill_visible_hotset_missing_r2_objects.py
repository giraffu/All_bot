import argparse
import csv
import json
import logging
import mimetypes
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Iterable, Literal

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from minio import Minio
from minio.error import InvalidResponseError, S3Error
from urllib3.exceptions import HTTPError as Urllib3HTTPError


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _find_argv_value(argv: list[str], name: str) -> str | None:
    prefix = f"{name}="
    for index, arg in enumerate(argv):
        if arg == name and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return None


def _load_env_file_from_argv(argv: list[str]) -> None:
    env_file = _find_argv_value(argv, "--env-file")
    if not env_file:
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=True)
    except Exception:
        for raw_line in Path(env_file).read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key.replace("_", "").isalnum() or key[0].isdigit():
                continue
            os.environ[key] = value.strip().strip("'\"")


_load_env_file_from_argv(sys.argv)

from src.core.media_urls import build_thumbnail_file_path  # noqa: E402


logger = logging.getLogger(__name__)

DEFAULT_SOURCE_LABELS = [
    "all_gallery_posts",
    "history_favorites",
    "gallery_like_apply_interactions",
    "gallery_prompt_unlocks",
]
DEFAULT_SOURCE_R2_BUCKETS = ["user-data", "user-data-prod"]
DEFAULT_SOURCE_TYPES = ["r2", "minio"]

ObjectKind = Literal["media", "thumbnail", "input_file"]
AuditScope = Literal["runtime", "standard", "input"]


@dataclass
class MissingObject:
    target_key: str
    object_kind: ObjectKind
    history_count_override: int | None = None
    audit_scopes: set[str] = field(default_factory=set)
    history_ids: set[int] = field(default_factory=set)
    task_ids: set[str] = field(default_factory=set)
    media_types: set[str] = field(default_factory=set)
    output_files: set[str] = field(default_factory=set)
    source_labels: set[str] = field(default_factory=set)
    r2_candidate_keys: list[str] = field(default_factory=list)
    minio_candidates: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class SourceHit:
    source_type: str
    source_name: str
    bucket: str
    key: str


@dataclass
class ObjectResult:
    target_key: str
    object_kind: str
    status: str
    source_type: str | None = None
    source_name: str | None = None
    source_bucket: str | None = None
    source_key: str | None = None
    history_count: int = 0
    source_labels: list[str] = field(default_factory=list)
    error_code: str | None = None


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_pipe(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    return [item for item in items if item and not (item in seen or seen.add(item))]


def _dedupe_pairs(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    return [item for item in items if item[0] and item[1] and not (item in seen or seen.add(item))]


def _guess_content_type(key: str) -> str:
    content_type, _ = mimetypes.guess_type(key)
    return content_type or "application/octet-stream"


def _append_minio_candidate(
    candidates: list[tuple[str, str]],
    *,
    path: str,
    buckets: list[str],
) -> None:
    if not path:
        return
    for bucket in buckets:
        prefix = f"{bucket}/"
        if path.startswith(prefix):
            candidates.append((bucket, path[len(prefix) :]))
            return
    if "/" not in path:
        for bucket in buckets:
            candidates.append((bucket, path))
        return
    candidates.append((buckets[0], path))
    for bucket in buckets[1:]:
        candidates.append((bucket, path))


def _build_minio_candidates(row: dict, *, minio_buckets: list[str]) -> list[tuple[str, str]]:
    object_kind = row["object_kind"]
    output_file = row.get("output_file") or ""
    media_type = row.get("media_type") or "image"
    target_key = row.get("r2_key") or ""
    r2_candidates = _split_pipe(row.get("candidate_keys"))
    candidates: list[tuple[str, str]] = []

    if object_kind == "media":
        for path in [output_file, *_dedupe(r2_candidates), target_key]:
            _append_minio_candidate(candidates, path=path, buckets=minio_buckets)
    elif object_kind == "thumbnail":
        thumb_file = build_thumbnail_file_path(output_file, media_type)
        for path in [thumb_file, *_dedupe(r2_candidates), target_key]:
            _append_minio_candidate(candidates, path=path, buckets=minio_buckets)
    elif object_kind == "input_file":
        for path in [target_key, *_dedupe(r2_candidates)]:
            _append_minio_candidate(candidates, path=path, buckets=minio_buckets)
    return _dedupe_pairs(candidates)


def load_missing_objects(
    csv_path: Path,
    *,
    source_labels: set[str],
    object_kinds: set[str],
    audit_scopes: set[str],
    minio_buckets: list[str],
    limit: int | None = None,
) -> tuple[list[MissingObject], dict]:
    objects_by_key: dict[tuple[str, str], MissingObject] = {}
    raw_rows = 0
    selected_rows = 0
    skipped_no_label = 0
    skipped_kind = 0
    skipped_scope = 0
    skipped_no_key = 0

    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw_rows += 1
            labels = set(_split_pipe(row.get("source_labels")))
            if source_labels and not labels.intersection(source_labels):
                skipped_no_label += 1
                continue
            object_kind = row.get("object_kind") or ""
            if object_kind not in object_kinds:
                skipped_kind += 1
                continue
            audit_scope = row.get("audit_scope") or ""
            if audit_scope not in audit_scopes:
                skipped_scope += 1
                continue
            target_key = row.get("r2_key") or ""
            if not target_key:
                skipped_no_key += 1
                continue

            selected_rows += 1
            key = (object_kind, target_key)
            item = objects_by_key.get(key)
            if item is None:
                item = MissingObject(target_key=target_key, object_kind=object_kind)  # type: ignore[arg-type]
                objects_by_key[key] = item
            item.audit_scopes.add(audit_scope)
            if row.get("history_id"):
                item.history_ids.add(int(row["history_id"]))
            if row.get("task_id"):
                item.task_ids.add(row["task_id"])
            if row.get("media_type"):
                item.media_types.add(row["media_type"])
            if row.get("output_file"):
                item.output_files.add(row["output_file"])
            item.source_labels.update(labels)
            item.r2_candidate_keys.extend(_split_pipe(row.get("candidate_keys")))
            item.minio_candidates.extend(
                _build_minio_candidates(row, minio_buckets=minio_buckets)
            )
            if limit and len(objects_by_key) >= limit:
                break

    objects = list(objects_by_key.values())
    for item in objects:
        item.r2_candidate_keys = _dedupe(item.r2_candidate_keys)
        item.minio_candidates = _dedupe_pairs(item.minio_candidates)

    return objects, {
        "raw_rows": raw_rows,
        "selected_rows": selected_rows,
        "selected_unique_objects": len(objects),
        "skipped_no_label": skipped_no_label,
        "skipped_kind": skipped_kind,
        "skipped_scope": skipped_scope,
        "skipped_no_key": skipped_no_key,
    }


def missing_object_to_manifest_row(item: MissingObject) -> dict:
    return {
        "target_key": item.target_key,
        "object_kind": item.object_kind,
        "history_count": history_count(item),
        "audit_scopes": sorted(item.audit_scopes),
        "task_ids": sorted(item.task_ids),
        "media_types": sorted(item.media_types),
        "output_files": sorted(item.output_files),
        "source_labels": sorted(item.source_labels),
        "r2_candidate_keys": item.r2_candidate_keys,
        "minio_candidates": [
            {"bucket": bucket, "key": key}
            for bucket, key in item.minio_candidates
        ],
    }


def write_manifest(objects: list[MissingObject], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in objects:
            fh.write(json.dumps(missing_object_to_manifest_row(item), ensure_ascii=False))
            fh.write("\n")


def load_manifest(path: Path, *, limit: int | None = None) -> tuple[list[MissingObject], dict]:
    objects: list[MissingObject] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            objects.append(
                MissingObject(
                    target_key=row["target_key"],
                    object_kind=row["object_kind"],
                    history_count_override=int(row.get("history_count", 0)),
                    audit_scopes=set(row.get("audit_scopes") or []),
                    task_ids=set(row.get("task_ids") or []),
                    media_types=set(row.get("media_types") or []),
                    output_files=set(row.get("output_files") or []),
                    source_labels=set(row.get("source_labels") or []),
                    r2_candidate_keys=list(row.get("r2_candidate_keys") or []),
                    minio_candidates=[
                        (candidate["bucket"], candidate["key"])
                        for candidate in row.get("minio_candidates") or []
                    ],
                )
            )
            if limit and len(objects) >= limit:
                break
    return objects, {
        "manifest_rows": len(objects),
        "selected_unique_objects": len(objects),
    }


def load_source_results(
    path: Path,
    *,
    statuses: set[str],
    source_types: set[str],
    object_kinds: set[str],
    limit: int | None = None,
) -> tuple[list[ObjectResult], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    source_results: list[ObjectResult] = []
    raw_results = 0
    skipped_status = 0
    skipped_source_type = 0
    skipped_kind = 0
    skipped_no_source = 0
    for row in payload.get("results") or []:
        raw_results += 1
        status = row.get("status")
        if status not in statuses:
            skipped_status += 1
            continue
        if object_kinds and row.get("object_kind") not in object_kinds:
            skipped_kind += 1
            continue
        source_type = row.get("source_type")
        if source_type not in source_types:
            skipped_source_type += 1
            continue
        if not row.get("source_bucket") or not row.get("source_key"):
            skipped_no_source += 1
            continue
        source_results.append(
            ObjectResult(
                target_key=row["target_key"],
                object_kind=row["object_kind"],
                status=status,
                source_type=source_type,
                source_name=row.get("source_name"),
                source_bucket=row.get("source_bucket"),
                source_key=row.get("source_key"),
                history_count=int(row.get("history_count", 0)),
                source_labels=list(row.get("source_labels") or []),
                error_code=row.get("error_code"),
            )
        )
        if limit and len(source_results) >= limit:
            break
    return source_results, {
        "source_results_input": str(path),
        "raw_results": raw_results,
        "selected_source_results": len(source_results),
        "skipped_status": skipped_status,
        "skipped_source_type": skipped_source_type,
        "skipped_kind": skipped_kind,
        "skipped_no_source": skipped_no_source,
    }


def history_count(item: MissingObject) -> int:
    if item.history_count_override is not None:
        return item.history_count_override
    return len(item.history_ids)


class R2Client:
    def __init__(self):
        self.bucket = os.environ["R2_BUCKET"]
        self.operation_attempts = int(os.getenv("R2_BACKFILL_OPERATION_ATTEMPTS", "5"))
        self.retry_delay_seconds = float(os.getenv("R2_BACKFILL_RETRY_DELAY_SECONDS", "1"))
        self.transfer_config = TransferConfig(
            max_concurrency=int(os.getenv("R2_BACKFILL_UPLOAD_PART_CONCURRENCY", "1")),
            multipart_chunksize=int(
                os.getenv("R2_BACKFILL_UPLOAD_MULTIPART_CHUNK_BYTES", str(16 * 1024 * 1024))
            ),
            use_threads=_parse_bool(
                os.getenv("R2_BACKFILL_UPLOAD_PART_THREADS"),
                default=False,
            ),
        )
        self.client = boto3.client(
            "s3",
            endpoint_url=os.environ["R2_ENDPOINT"],
            aws_access_key_id=os.environ["R2_ACCESS_KEY"],
            aws_secret_access_key=os.environ["R2_SECRET_KEY"],
            config=BotoConfig(
                signature_version="s3v4",
                max_pool_connections=int(os.getenv("R2_MAX_POOL_CONNECTIONS", "64")),
                connect_timeout=float(os.getenv("R2_HEAD_CONNECT_TIMEOUT_SECONDS", "5")),
                read_timeout=float(os.getenv("R2_HEAD_READ_TIMEOUT_SECONDS", "60")),
                retries={"max_attempts": int(os.getenv("R2_HEAD_MAX_ATTEMPTS", "5"))},
            ),
            region_name="auto",
        )

    def _sleep_before_retry(self, attempt: int) -> None:
        time.sleep(min(self.retry_delay_seconds * attempt, 5.0))

    @staticmethod
    def _is_not_found(exc: ClientError) -> bool:
        error = exc.response.get("Error", {}) if exc.response else {}
        code = str(error.get("Code", "ClientError"))
        status_code = (
            exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if exc.response
            else None
        )
        return code in {"404", "NoSuchKey", "NotFound"} or status_code == 404

    @staticmethod
    def _is_retryable_client_error(exc: ClientError) -> bool:
        error = exc.response.get("Error", {}) if exc.response else {}
        code = str(error.get("Code", "ClientError"))
        status_code = (
            exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if exc.response
            else None
        )
        return code in {
            "RequestTimeout",
            "SlowDown",
            "Throttling",
            "InternalError",
            "ServiceUnavailable",
        } or status_code in {408, 429, 500, 502, 503, 504}

    def exists(self, bucket: str, key: str) -> bool:
        for attempt in range(1, self.operation_attempts + 1):
            try:
                self.client.head_object(Bucket=bucket, Key=key)
                return True
            except ClientError as exc:
                if self._is_not_found(exc):
                    return False
                if attempt < self.operation_attempts and self._is_retryable_client_error(exc):
                    self._sleep_before_retry(attempt)
                    continue
                raise
            except (BotoCoreError, OSError, Urllib3HTTPError):
                if attempt >= self.operation_attempts:
                    raise
                self._sleep_before_retry(attempt)
        return False

    def copy(self, source_bucket: str, source_key: str, target_key: str) -> None:
        for attempt in range(1, self.operation_attempts + 1):
            try:
                self.client.copy_object(
                    Bucket=self.bucket,
                    Key=target_key,
                    CopySource={"Bucket": source_bucket, "Key": source_key},
                    ContentType=_guess_content_type(target_key),
                    MetadataDirective="REPLACE",
                )
                return
            except ClientError as exc:
                if attempt < self.operation_attempts and self._is_retryable_client_error(exc):
                    self._sleep_before_retry(attempt)
                    continue
                raise
            except (BotoCoreError, OSError):
                if attempt >= self.operation_attempts:
                    raise
                self._sleep_before_retry(attempt)

    def upload_from_minio(
        self,
        *,
        minio_client: Minio,
        source_bucket: str,
        source_key: str,
        target_key: str,
    ) -> None:
        for attempt in range(1, self.operation_attempts + 1):
            response = None
            try:
                response = minio_client.get_object(source_bucket, source_key)
                with SpooledTemporaryFile(max_size=64 * 1024 * 1024) as temp_file:
                    for chunk in response.stream(1024 * 1024):
                        temp_file.write(chunk)
                    temp_file.seek(0)
                    self.client.upload_fileobj(
                        temp_file,
                        self.bucket,
                        target_key,
                        ExtraArgs={"ContentType": _guess_content_type(target_key)},
                        Config=self.transfer_config,
                    )
                return
            except (BotoCoreError, OSError):
                if attempt >= self.operation_attempts:
                    raise
                self._sleep_before_retry(attempt)
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()


class MinioSource:
    def __init__(
        self,
        *,
        name: str,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool,
    ):
        self.name = name
        self.operation_attempts = int(os.getenv("MINIO_BACKFILL_OPERATION_ATTEMPTS", "5"))
        self.retry_delay_seconds = float(
            os.getenv("MINIO_BACKFILL_RETRY_DELAY_SECONDS", "1")
        )
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    def _sleep_before_retry(self, attempt: int) -> None:
        time.sleep(min(self.retry_delay_seconds * attempt, 5.0))

    def exists(self, bucket: str, key: str) -> bool:
        for attempt in range(1, self.operation_attempts + 1):
            try:
                self.client.stat_object(bucket, key)
                return True
            except S3Error as exc:
                if exc.code in {"NoSuchKey", "NoSuchBucket", "NoSuchObject"}:
                    return False
                if attempt < self.operation_attempts and exc.code in {
                    "RequestTimeout",
                    "SlowDown",
                    "InternalError",
                    "ServiceUnavailable",
                }:
                    self._sleep_before_retry(attempt)
                    continue
                raise
            except InvalidResponseError:
                return False
            except OSError:
                if attempt >= self.operation_attempts:
                    raise
                self._sleep_before_retry(attempt)
        return False


def build_minio_sources(args: argparse.Namespace) -> list[MinioSource]:
    sources: list[MinioSource] = []
    legacy_endpoint = args.legacy_minio_endpoint or os.getenv("LEGACY_MINIO_ENDPOINT")
    legacy_access = os.getenv("LEGACY_MINIO_ACCESS_KEY")
    legacy_secret = os.getenv("LEGACY_MINIO_SECRET_KEY")
    if legacy_endpoint and legacy_access and legacy_secret:
        sources.append(
            MinioSource(
                name="legacy-hot",
                endpoint=legacy_endpoint,
                access_key=legacy_access,
                secret_key=legacy_secret,
                secure=_parse_bool(os.getenv("LEGACY_MINIO_SECURE"), default=False),
            )
        )

    cold_endpoint = args.cold_minio_endpoint or os.getenv("COLD_MINIO_ENDPOINT")
    if cold_endpoint:
        cold_access = os.getenv("COLD_MINIO_ACCESS_KEY") or legacy_access
        cold_secret = os.getenv("COLD_MINIO_SECRET_KEY") or legacy_secret
        if cold_access and cold_secret:
            sources.append(
                MinioSource(
                    name="cold-minio",
                    endpoint=cold_endpoint,
                    access_key=cold_access,
                    secret_key=cold_secret,
                    secure=_parse_bool(os.getenv("COLD_MINIO_SECURE"), default=False),
                )
            )
    return sources


def find_source_hit(
    item: MissingObject,
    *,
    r2: R2Client,
    source_r2_buckets: list[str],
    minio_sources: list[MinioSource],
) -> SourceHit | None:
    for bucket in source_r2_buckets:
        for key in item.r2_candidate_keys:
            if bucket == r2.bucket and key == item.target_key:
                continue
            if r2.exists(bucket, key):
                return SourceHit(
                    source_type="r2",
                    source_name=bucket,
                    bucket=bucket,
                    key=key,
                )

    for source in minio_sources:
        for bucket, key in item.minio_candidates:
            if source.exists(bucket, key):
                return SourceHit(
                    source_type="minio",
                    source_name=source.name,
                    bucket=bucket,
                    key=key,
                )
    return None


def process_objects(
    objects: list[MissingObject],
    *,
    apply_changes: bool,
    r2: R2Client,
    source_r2_buckets: list[str],
    minio_sources: list[MinioSource],
    progress_interval: int,
    concurrency: int,
) -> list[ObjectResult]:
    results: list[ObjectResult] = []
    minio_by_name = {source.name: source for source in minio_sources}

    def process_one(item: MissingObject) -> ObjectResult:
        try:
            if r2.exists(r2.bucket, item.target_key):
                status = "exists"
                hit = None
            else:
                hit = find_source_hit(
                    item,
                    r2=r2,
                    source_r2_buckets=source_r2_buckets,
                    minio_sources=minio_sources,
                )
                if hit is None:
                    status = "source_missing"
                elif not apply_changes:
                    status = "would_upload"
                else:
                    if hit.source_type == "r2":
                        r2.copy(hit.bucket, hit.key, item.target_key)
                    else:
                        minio_source = minio_by_name[hit.source_name]
                        r2.upload_from_minio(
                            minio_client=minio_source.client,
                            source_bucket=hit.bucket,
                            source_key=hit.key,
                            target_key=item.target_key,
                        )
                    status = "uploaded"
            return ObjectResult(
                target_key=item.target_key,
                object_kind=item.object_kind,
                status=status,
                source_type=hit.source_type if hit else None,
                source_name=hit.source_name if hit else None,
                source_bucket=hit.bucket if hit else None,
                source_key=hit.key if hit else None,
                history_count=history_count(item),
                source_labels=sorted(item.source_labels),
            )
        except (ClientError, BotoCoreError, S3Error, OSError, Urllib3HTTPError) as exc:
            logger.warning(
                "Failed to process target=%s kind=%s: %s",
                item.target_key,
                item.object_kind,
                type(exc).__name__,
            )
            return ObjectResult(
                target_key=item.target_key,
                object_kind=item.object_kind,
                status="failed",
                history_count=history_count(item),
                source_labels=sorted(item.source_labels),
                error_code=type(exc).__name__,
            )

    processed = 0
    safe_concurrency = max(1, concurrency)
    executor = ThreadPoolExecutor(max_workers=safe_concurrency)
    try:
        future_to_item = {executor.submit(process_one, item): item for item in objects}
        for future in as_completed(future_to_item):
            results.append(future.result())
            processed += 1
            if progress_interval > 0 and (
                processed == 1
                or processed % progress_interval == 0
                or processed == len(objects)
            ):
                logger.info("Processed %s/%s missing objects", processed, len(objects))
    except KeyboardInterrupt:
        for future in future_to_item:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
    return results


def process_source_results(
    source_results: list[ObjectResult],
    *,
    apply_changes: bool,
    r2: R2Client,
    minio_sources: list[MinioSource],
    progress_interval: int,
    concurrency: int,
) -> list[ObjectResult]:
    results: list[ObjectResult] = []
    minio_by_name = {source.name: source for source in minio_sources}

    def process_one(source_result: ObjectResult) -> ObjectResult:
        hit = SourceHit(
            source_type=source_result.source_type or "",
            source_name=source_result.source_name or "",
            bucket=source_result.source_bucket or "",
            key=source_result.source_key or "",
        )
        try:
            if r2.exists(r2.bucket, source_result.target_key):
                status = "exists"
            elif not apply_changes:
                status = "would_upload"
            else:
                if hit.source_type == "r2":
                    r2.copy(hit.bucket, hit.key, source_result.target_key)
                elif hit.source_type == "minio":
                    minio_source = minio_by_name[hit.source_name]
                    r2.upload_from_minio(
                        minio_client=minio_source.client,
                        source_bucket=hit.bucket,
                        source_key=hit.key,
                        target_key=source_result.target_key,
                    )
                else:
                    raise ValueError(f"Unsupported source_type: {hit.source_type}")
                status = "uploaded"
            return ObjectResult(
                target_key=source_result.target_key,
                object_kind=source_result.object_kind,
                status=status,
                source_type=hit.source_type if status != "exists" else None,
                source_name=hit.source_name if status != "exists" else None,
                source_bucket=hit.bucket if status != "exists" else None,
                source_key=hit.key if status != "exists" else None,
                history_count=source_result.history_count,
                source_labels=source_result.source_labels,
            )
        except (
            ClientError,
            BotoCoreError,
            S3Error,
            OSError,
            Urllib3HTTPError,
            ValueError,
        ) as exc:
            logger.warning(
                "Failed to process target=%s kind=%s: %s",
                source_result.target_key,
                source_result.object_kind,
                type(exc).__name__,
            )
            return ObjectResult(
                target_key=source_result.target_key,
                object_kind=source_result.object_kind,
                status="failed",
                source_type=hit.source_type,
                source_name=hit.source_name,
                source_bucket=hit.bucket,
                source_key=hit.key,
                history_count=source_result.history_count,
                source_labels=source_result.source_labels,
                error_code=type(exc).__name__,
            )

    processed = 0
    safe_concurrency = max(1, concurrency)
    executor = ThreadPoolExecutor(max_workers=safe_concurrency)
    try:
        future_to_result = {
            executor.submit(process_one, source_result): source_result
            for source_result in source_results
        }
        for future in as_completed(future_to_result):
            results.append(future.result())
            processed += 1
            if progress_interval > 0 and (
                processed == 1
                or processed % progress_interval == 0
                or processed == len(source_results)
            ):
                logger.info(
                    "Processed %s/%s source-hit objects",
                    processed,
                    len(source_results),
                )
    except KeyboardInterrupt:
        for future in future_to_result:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
    return results


def summarize_results(results: list[ObjectResult], *, selection: dict, apply_changes: bool) -> dict:
    counts = Counter(result.status for result in results)
    by_kind: dict[str, Counter] = defaultdict(Counter)
    by_source: dict[str, Counter] = defaultdict(Counter)
    by_label: dict[str, Counter] = defaultdict(Counter)
    for result in results:
        by_kind[result.object_kind][result.status] += 1
        source_name = result.source_name or "none"
        by_source[source_name][result.status] += 1
        for label in result.source_labels:
            by_label[label][result.status] += 1
    return {
        "mode": "apply" if apply_changes else "dry-run",
        "selection": selection,
        "processed_unique_objects": len(results),
        "status_counts": dict(sorted(counts.items())),
        "by_kind": {key: dict(value) for key, value in sorted(by_kind.items())},
        "by_source": {key: dict(value) for key, value in sorted(by_source.items())},
        "by_source_label": {key: dict(value) for key, value in sorted(by_label.items())},
    }


def write_report(
    *,
    report_dir: Path,
    summary: dict,
    results: list[ObjectResult],
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"visible_hotset_missing_r2_backfill_{timestamp}"
    json_path = report_dir / f"{base_name}.json"
    md_path = report_dir / f"{base_name}.md"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "results": [asdict(result) for result in results],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Visible Hotset Missing R2 Backfill",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- mode: `{summary['mode']}`",
        f"- processed_unique_objects: `{summary['processed_unique_objects']}`",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in summary["status_counts"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## By Kind", ""])
    for key, value in summary["by_kind"].items():
        lines.append(f"- `{key}`: `{json.dumps(value, ensure_ascii=False)}`")
    lines.extend(["", "## By Source", ""])
    for key, value in summary["by_source"].items():
        lines.append(f"- `{key}`: `{json.dumps(value, ensure_ascii=False)}`")
    lines.extend(["", "## By Source Label", ""])
    for key, value in summary["by_source_label"].items():
        lines.append(f"- `{key}`: `{json.dumps(value, ensure_ascii=False)}`")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "从 R2 审计缺失附录中筛选社区强可见对象，并从 R2 fallback/"
            "legacy MinIO/冷 MinIO 补齐到正式 R2。默认 dry-run。"
        )
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--missing-appendix", type=Path)
    parser.add_argument("--manifest-input", type=Path)
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument(
        "--source-results-input",
        type=Path,
        help="读取本脚本上一次 dry-run/apply JSON 报告中的 source hit，直接补齐这些对象。",
    )
    parser.add_argument(
        "--source-result-statuses",
        default="would_upload",
        help="配合 --source-results-input 使用，逗号分隔筛选结果状态。",
    )
    parser.add_argument(
        "--inventory-only",
        action="store_true",
        help="仅从缺失附录聚合唯一目标对象并写报告/manifest，不探测或复制源。",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--source-labels",
        default=",".join(DEFAULT_SOURCE_LABELS),
        help="逗号分隔的 source_labels 过滤；默认四类社区强可见集合。",
    )
    parser.add_argument(
        "--object-kinds",
        default="media,thumbnail,input_file",
        help="逗号分隔对象类型。",
    )
    parser.add_argument(
        "--audit-scopes",
        default="runtime,input,standard",
        help="逗号分隔审计 scope；默认 runtime/input/standard 都补。",
    )
    parser.add_argument(
        "--source-r2-buckets",
        default=",".join(DEFAULT_SOURCE_R2_BUCKETS),
        help="逗号分隔的 R2 源桶候选；会跳过当前桶同 key。",
    )
    parser.add_argument(
        "--source-types",
        default=",".join(DEFAULT_SOURCE_TYPES),
        help="逗号分隔的源类型：r2,minio。可先用 r2-only 快速补旧 R2 桶。",
    )
    parser.add_argument(
        "--minio-buckets",
        default="bot-data,comfyui-temp",
        help="逗号分隔的 MinIO 源桶候选。",
    )
    parser.add_argument(
        "--legacy-minio-endpoint",
        help="覆盖热 legacy MinIO endpoint；本地主机补数时可用 127.0.0.1:9000 避免绕 Tailscale。",
    )
    parser.add_argument(
        "--cold-minio-endpoint",
        default="192.168.1.88:9001",
        help="冷 MinIO endpoint；凭据默认复用 COLD_MINIO_* 或 LEGACY_MINIO_*。",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--progress-interval", type=int, default=1000)
    parser.add_argument("--report-dir", type=Path, default=Path("logs"))
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    source_labels = set(_split_csv(args.source_labels))
    object_kinds = set(_split_csv(args.object_kinds))
    audit_scopes = set(_split_csv(args.audit_scopes))
    minio_buckets = _split_csv(args.minio_buckets)
    source_types = set(_split_csv(args.source_types))
    source_r2_buckets = (
        _split_csv(args.source_r2_buckets) if "r2" in source_types else []
    )

    if args.source_results_input:
        source_statuses = set(_split_csv(args.source_result_statuses))
        source_results, selection = load_source_results(
            args.source_results_input,
            statuses=source_statuses,
            source_types=source_types,
            object_kinds=object_kinds,
            limit=args.limit,
        )
        logger.info(
            "Loaded %s source-hit objects from report",
            len(source_results),
        )
    elif args.manifest_input:
        objects, selection = load_manifest(args.manifest_input, limit=args.limit)
    else:
        if not args.missing_appendix:
            raise SystemExit(
                "--missing-appendix, --manifest-input, or --source-results-input is required"
            )
        objects, selection = load_missing_objects(
            args.missing_appendix,
            source_labels=source_labels,
            object_kinds=object_kinds,
            audit_scopes=audit_scopes,
            minio_buckets=minio_buckets,
            limit=args.limit,
        )
    if not args.source_results_input:
        logger.info("Loaded %s unique missing objects from appendix", len(objects))
    if args.manifest_output:
        if args.source_results_input:
            raise SystemExit("--manifest-output is only supported for appendix/manifest inputs")
        write_manifest(objects, args.manifest_output)
        logger.info("Wrote manifest: %s", args.manifest_output)
    if args.inventory_only:
        if args.source_results_input:
            raise SystemExit("--inventory-only is only supported for appendix/manifest inputs")
        summary = {
            "mode": "inventory-only",
            "selection": selection,
            "processed_unique_objects": len(objects),
            "by_kind": dict(Counter(item.object_kind for item in objects)),
            "by_source_label": {
                label: sum(1 for item in objects if label in item.source_labels)
                for label in sorted(source_labels)
            },
        }
        json_path, md_path = write_report(
            report_dir=args.report_dir,
            summary={
                **summary,
                "status_counts": {"inventory": len(objects)},
                "by_source": {},
            },
            results=[],
        )
        print(
            json.dumps(
                {
                    "summary": summary,
                    "json_report": str(json_path),
                    "markdown_report": str(md_path),
                    "manifest_output": str(args.manifest_output)
                    if args.manifest_output
                    else None,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return

    r2 = R2Client()
    minio_sources = build_minio_sources(args) if "minio" in source_types else []
    logger.info(
        "Configured sources: source_types=%s r2_buckets=%s minio_sources=%s",
        sorted(source_types),
        source_r2_buckets,
        [source.name for source in minio_sources],
    )
    if args.source_results_input:
        results = process_source_results(
            source_results,
            apply_changes=args.apply,
            r2=r2,
            minio_sources=minio_sources,
            progress_interval=args.progress_interval,
            concurrency=args.concurrency,
        )
    else:
        results = process_objects(
            objects,
            apply_changes=args.apply,
            r2=r2,
            source_r2_buckets=source_r2_buckets,
            minio_sources=minio_sources,
            progress_interval=args.progress_interval,
            concurrency=args.concurrency,
        )
    summary = summarize_results(
        results,
        selection=selection,
        apply_changes=args.apply,
    )
    json_path, md_path = write_report(
        report_dir=args.report_dir,
        summary=summary,
        results=results,
    )
    print(
        json.dumps(
            {
                "summary": summary,
                "json_report": str(json_path),
                "markdown_report": str(md_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
