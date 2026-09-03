from __future__ import annotations

import json
import http.client
import hashlib
import mimetypes
import os
from pathlib import PurePosixPath
import re
from typing import Iterable, Literal
from urllib.parse import quote, urlparse

import boto3
from botocore.config import Config
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from .analytics_common import _fetch, _fetchrow, _row, _rows
from .auth import AuthConfig, read_session_token


router = APIRouter()
RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")
CLOUDFLARE_HEADERS = (
    "cf-ray",
    "cf-connecting-ip",
    "cf-ipcountry",
    "cf-visitor",
)


def _validated_snapshot_gateway() -> tuple[str, int, str]:
    raw = os.getenv("SNAPSHOT_MEDIA_GATEWAY_URL", "").strip()
    token = os.getenv("SNAPSHOT_MEDIA_GATEWAY_TOKEN", "")
    if not token:
        session_secret = os.getenv("LOCAL_ANALYTICS_AUTH_SESSION_SECRET", "")
        if session_secret:
            token = hashlib.sha256(
                f"allbot-snapshot-gateway:{session_secret}".encode()
            ).hexdigest()
    parsed = urlparse(raw)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.path.rstrip("/")
        or not token
    ):
        raise HTTPException(
            status_code=503, detail="snapshot media gateway is not configured"
        )
    return parsed.hostname, parsed.port or 80, token


def _snapshot_gateway_response(
    *, batch_number: int, object_key: str, range_header: str | None
) -> dict[str, object]:
    host, port, token = _validated_snapshot_gateway()
    path = f"/v1/batches/{batch_number:06d}/objects/{quote(object_key, safe='')}"
    connection = http.client.HTTPConnection(host, port, timeout=30)
    headers = {"X-AllBot-Snapshot-Token": token}
    if range_header:
        headers["Range"] = range_header
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
    except Exception as exc:
        connection.close()
        raise HTTPException(
            status_code=503, detail="NAS snapshot content is temporarily unavailable"
        ) from exc
    if response.status not in {200, 206}:
        response.read()
        connection.close()
        detail = (
            "snapshot file is not present in its verified NAS batch"
            if response.status == 404
            else "NAS snapshot content is temporarily unavailable"
        )
        raise HTTPException(status_code=404 if response.status == 404 else 503, detail=detail)

    def body() -> Iterable[bytes]:
        try:
            while chunk := response.read(1024 * 1024):
                yield chunk
        finally:
            response.close()
            connection.close()

    return {
        "body": body(),
        "content_length": response.getheader("Content-Length"),
        "content_range": response.getheader("Content-Range"),
    }


def require_lan_archive_request(request: Request) -> None:
    if any(request.headers.get(name) for name in CLOUDFLARE_HEADERS):
        raise HTTPException(
            status_code=403,
            detail="full archive content is available from the authenticated LAN only",
        )


def require_archive_auth(request: Request) -> None:
    config = AuthConfig.from_env()
    if not config.enabled or not config.configured:
        raise HTTPException(
            status_code=503,
            detail="archive browser requires configured local analytics authentication",
        )
    if not read_session_token(config, request.cookies.get(config.cookie_name)):
        raise HTTPException(status_code=401, detail="authentication required")


def _nas_client():
    endpoint = os.getenv("NAS_MINIO_ENDPOINT", "https://192.168.1.150:9000")
    access_key = os.getenv("NAS_MINIO_ANALYTICS_ACCESS_KEY", "")
    secret_key = os.getenv("NAS_MINIO_ANALYTICS_SECRET_KEY", "")
    ca_file = os.getenv("NAS_MINIO_CA_FILE", "")
    if not access_key or not secret_key or not ca_file:
        raise HTTPException(
            status_code=503, detail="NAS read-only client is not configured"
        )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
        verify=ca_file,
        config=Config(signature_version="s3v4"),
    )


@router.get(
    "/api/archive/status",
    dependencies=[Depends(require_archive_auth)],
)
async def archive_status():
    summary = _row(
        await _fetchrow(
            """
            select count(*)::bigint logical_assets,
              count(*) filter(where status='archived_verified')::bigint verified_assets,
              count(*) filter(where status='source_offline')::bigint offline_assets,
              count(*) filter(where status='provisional_missing')::bigint provisional_missing,
              count(*) filter(where status='confirmed_lost')::bigint confirmed_lost,
              count(*) filter(where status='checksum_error')::bigint checksum_errors,
              count(*) filter(where status='pending_probe')::bigint pending_assets
            from analytics_media_asset_catalog
            """
        )
    )
    blobs = _row(
        await _fetchrow(
            "select count(*)::bigint blob_count,coalesce(sum(byte_size),0)::bigint archived_bytes from analytics_media_blobs"
        )
    )
    source_hits = _rows(
        await _fetch(
            """select coalesce(found_source,'unresolved') source,count(*)::bigint asset_count
               from analytics_media_asset_catalog group by 1 order by asset_count desc"""
        )
    )
    latest_run = _row(
        await _fetchrow(
            """select run_type,status,stats,error,started_at,completed_at
               from analytics_media_runs order by started_at desc limit 1"""
        )
    )
    raw_stats = latest_run.get("stats")
    if isinstance(raw_stats, str):
        try:
            raw_stats = json.loads(raw_stats)
        except json.JSONDecodeError:
            raw_stats = {}
    run_stats = raw_stats if isinstance(raw_stats, dict) else {}
    latest_run["stats"] = run_stats
    has_outbox = bool(
        _row(
            await _fetchrow(
                "select to_regclass('public.media_archive_outbox') is not null as present"
            )
        ).get("present")
    )
    backlog = {}
    if has_outbox:
        backlog = _row(
            await _fetchrow(
                """select count(*) filter(where status in ('pending','retry','leased'))::bigint backlog,
                   count(*) filter(where status='leased')::bigint leased,
                   count(*) filter(where status='manual_review')::bigint manual_review,
                   coalesce(extract(epoch from now()-min(created_at)
                     filter(where status in ('pending','retry','leased'))),0)::bigint oldest_backlog_seconds
                   from media_archive_outbox"""
            )
        )
    snapshot_backup = _row(
        await _fetchrow(
            """select snapshot_id,snapshot_label,object_count,reference_count,
                      last_verified_batch,status_counts,refreshed_at
               from analytics_snapshot_backup_sets where ready
               order by created_at desc limit 1"""
        )
    )
    if isinstance(snapshot_backup.get("status_counts"), str):
        try:
            snapshot_backup["status_counts"] = json.loads(
                snapshot_backup["status_counts"]
            )
        except json.JSONDecodeError:
            snapshot_backup["status_counts"] = {}
    capacity = int(os.getenv("NAS_ARCHIVE_CAPACITY_BYTES", "0") or 0)
    archived_bytes = int(blobs.get("archived_bytes") or 0)
    usage_ratio = archived_bytes / capacity if capacity else None
    pause_reason = None
    if usage_ratio is not None and usage_ratio >= 0.9:
        pause_reason = "nas_usage_90_stop_all"
    elif usage_ratio is not None and usage_ratio >= 0.8:
        pause_reason = "nas_usage_80_stop_cold"
    return {
        **summary,
        **blobs,
        "source_hits": source_hits,
        "latest_run": latest_run,
        "outbox": backlog,
        "snapshot_backup": snapshot_backup,
        "throughput_bytes_per_second": run_stats.get("bytes_per_second", 0),
        "capacity_bytes": capacity or None,
        "usage_ratio": usage_ratio,
        "pause_reason": pause_reason,
        "alerts": {
            "capacity_warning": bool(usage_ratio is not None and usage_ratio >= 0.75),
            "checksum_error": bool(summary.get("checksum_errors")),
            "archive_warning": int(backlog.get("oldest_backlog_seconds") or 0) >= 3600,
            "archive_critical": int(backlog.get("oldest_backlog_seconds") or 0)
            >= 86400,
        },
    }


@router.get(
    "/api/generation-history/{history_id}/media",
    dependencies=[Depends(require_archive_auth)],
)
async def history_media(
    history_id: int,
    role_group: Literal["input", "output", "all"] = "all",
):
    history = await _fetchrow(
        "select id, task_id, user_id, type, created_at from history where id=$1",
        history_id,
    )
    if not history:
        raise HTTPException(status_code=404, detail="history not found")
    role_predicate = {
        "input": "snapshot_ref.role='input'",
        "output": "snapshot_ref.role<>'input'",
        "all": "true",
    }[role_group]
    snapshot_assets = await _fetch(
        f"""
        select snapshot_ref.id, snapshot_ref.role, snapshot_ref.ordinal,
               snapshot_ref.original_ref, snapshot_ref.object_key,
               snapshot_object.backup_status, snapshot_object.batch_number,
               snapshot_object.byte_size, snapshot_object.sha256,
               snapshot_object.error_code, snapshot_set.snapshot_label
        from analytics_snapshot_backup_refs snapshot_ref
        join analytics_snapshot_backup_objects snapshot_object
          on snapshot_object.snapshot_id=snapshot_ref.snapshot_id
         and snapshot_object.object_key=snapshot_ref.object_key
        join analytics_snapshot_backup_sets snapshot_set
          on snapshot_set.snapshot_id=snapshot_ref.snapshot_id and snapshot_set.ready
        where snapshot_ref.history_id=$1 and {role_predicate}
        order by case when snapshot_ref.role='input' then 0
                      when snapshot_ref.role='output' then 1 else 2 end,
                 snapshot_ref.role, snapshot_ref.ordinal
        """,
        history_id,
    )
    if snapshot_assets:
        projected_assets = []
        for raw_asset in _rows(snapshot_assets):
            asset = dict(raw_asset)
            asset["status"] = asset.pop("backup_status")
            asset["found_source"] = "r2-history-snapshot"
            asset["mime_type"] = mimetypes.guess_type(
                str(asset.get("original_ref") or asset.get("object_key") or "")
            )[0]
            asset.pop("object_key", None)
            local_available = bool(
                asset.get("status") == "backed_up"
                and asset.get("batch_number")
                and asset.get("sha256")
            )
            asset["local_available"] = local_available
            asset["content_url"] = (
                f"/api/snapshot-assets/{asset['id']}/content"
                if local_available
                else None
            )
            projected_assets.append(asset)
        return {
            "history": _row(history),
            "role_group": role_group,
            "media_source": "snapshot_backup",
            "assets": projected_assets,
        }
    role_predicate = {
        "input": "a.role='input'",
        "output": "a.role<>'input'",
        "all": "true",
    }[role_group]
    assets = await _fetch(
        f"""
        select a.id, a.role, a.ordinal, a.original_ref, a.temperature, a.status,
               a.found_source, a.source_key, a.sha256, a.last_checked_at,
               a.last_error, b.byte_size, b.mime_type, b.nas_bucket, b.nas_key,
               b.verified_at
        from analytics_media_asset_catalog a
        left join analytics_media_blobs b on b.sha256=a.sha256
        where a.history_id=$1 and {role_predicate}
        order by case when a.role='input' then 0 when a.role='output' then 1 else 2 end,
                 a.role, a.ordinal
        """,
        history_id,
    )
    projected_assets = []
    for raw_asset in _rows(assets):
        asset = dict(raw_asset)
        nas_bucket = asset.pop("nas_bucket", None)
        nas_key = asset.pop("nas_key", None)
        local_available = bool(
            asset.get("status") == "archived_verified"
            and asset.get("sha256")
            and nas_bucket
            and nas_key
        )
        asset["local_available"] = local_available
        asset["content_url"] = (
            f"/api/archive/assets/{asset['id']}/content" if local_available else None
        )
        projected_assets.append(asset)
    return {
        "history": _row(history),
        "role_group": role_group,
        "media_source": "official_archive",
        "assets": projected_assets,
    }


@router.get(
    "/api/snapshot-assets/{snapshot_ref_id}/content",
    dependencies=[Depends(require_lan_archive_request), Depends(require_archive_auth)],
)
async def snapshot_asset_content(
    snapshot_ref_id: int,
    range_header: str | None = Header(default=None, alias="Range"),
):
    asset = _row(
        await _fetchrow(
            """select snapshot_ref.original_ref, snapshot_ref.object_key,
                      snapshot_object.backup_status, snapshot_object.batch_number,
                      snapshot_object.byte_size
               from analytics_snapshot_backup_refs snapshot_ref
               join analytics_snapshot_backup_objects snapshot_object
                 on snapshot_object.snapshot_id=snapshot_ref.snapshot_id
                and snapshot_object.object_key=snapshot_ref.object_key
               join analytics_snapshot_backup_sets snapshot_set
                 on snapshot_set.snapshot_id=snapshot_ref.snapshot_id and snapshot_set.ready
               where snapshot_ref.id=$1
                 and snapshot_object.backup_status='backed_up'
                 and snapshot_object.batch_number is not null""",
            snapshot_ref_id,
        )
    )
    if not asset:
        raise HTTPException(status_code=404, detail="verified snapshot content not found")
    status_code = 200
    if range_header:
        match = RANGE_PATTERN.match(range_header)
        if not match:
            raise HTTPException(status_code=416, detail="invalid byte range")
        start, end = match.groups()
        if (not start and not end) or (start and end and int(end) < int(start)):
            raise HTTPException(status_code=416, detail="invalid byte range")
        status_code = 206
    response = _snapshot_gateway_response(
        batch_number=int(asset["batch_number"]),
        object_key=str(asset["object_key"]),
        range_header=range_header,
    )
    filename = (
        PurePosixPath(str(asset["original_ref"])).name
        or f"snapshot-asset-{snapshot_ref_id}"
    )
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
    }
    if response.get("content_range"):
        headers["Content-Range"] = str(response["content_range"])
    if response.get("content_length") is not None:
        headers["Content-Length"] = str(response["content_length"])
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return StreamingResponse(
        response["body"], status_code=status_code, media_type=mime_type, headers=headers
    )


@router.get(
    "/api/archive/assets/{asset_id}", dependencies=[Depends(require_archive_auth)]
)
async def archive_asset(asset_id: int):
    asset = await _fetchrow(
        """
        select a.*, b.byte_size, b.mime_type, b.nas_bucket, b.nas_key, b.verified_at
        from analytics_media_asset_catalog a
        left join analytics_media_blobs b on b.sha256=a.sha256 where a.id=$1
        """,
        asset_id,
    )
    if not asset:
        raise HTTPException(status_code=404, detail="archive asset not found")
    return _row(asset)


@router.get(
    "/api/archive/assets/{asset_id}/content",
    dependencies=[Depends(require_lan_archive_request), Depends(require_archive_auth)],
)
async def archive_asset_content(
    asset_id: int, range_header: str | None = Header(default=None, alias="Range")
):
    asset = _row(
        await _fetchrow(
            """select a.original_ref, a.status, b.byte_size, b.mime_type, b.nas_bucket, b.nas_key
           from analytics_media_asset_catalog a join analytics_media_blobs b on b.sha256=a.sha256
           where a.id=$1 and a.status='archived_verified'""",
            asset_id,
        )
    )
    if not asset:
        raise HTTPException(
            status_code=404, detail="verified archive content not found"
        )
    request_args = {"Bucket": asset["nas_bucket"], "Key": asset["nas_key"]}
    status_code = 200
    if range_header:
        match = RANGE_PATTERN.match(range_header)
        if not match:
            raise HTTPException(status_code=416, detail="invalid byte range")
        start, end = match.groups()
        if (not start and not end) or (start and end and int(end) < int(start)):
            raise HTTPException(status_code=416, detail="invalid byte range")
        request_args["Range"] = range_header
        status_code = 206
    try:
        response = _nas_client().get_object(**request_args)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="NAS archive content is temporarily unavailable",
        ) from exc
    body = response["Body"]

    def stream():
        try:
            yield from body.iter_chunks(chunk_size=1024 * 1024)
        finally:
            body.close()

    filename = PurePosixPath(str(asset["original_ref"])).name or f"asset-{asset_id}"
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
    }
    if response.get("ContentRange"):
        headers["Content-Range"] = response["ContentRange"]
    if response.get("ContentLength") is not None:
        headers["Content-Length"] = str(response["ContentLength"])
    return StreamingResponse(
        stream(),
        status_code=status_code,
        media_type=asset.get("mime_type") or "application/octet-stream",
        headers=headers,
    )
