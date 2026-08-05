from __future__ import annotations

import json
import os
from pathlib import PurePosixPath
import re
from urllib.parse import quote

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
async def history_media(history_id: int):
    history = await _fetchrow(
        "select id, task_id, user_id, type, created_at from history where id=$1",
        history_id,
    )
    if not history:
        raise HTTPException(status_code=404, detail="history not found")
    assets = await _fetch(
        """
        select a.id, a.role, a.ordinal, a.original_ref, a.temperature, a.status,
               a.found_source, a.source_key, a.sha256, a.last_checked_at,
               a.last_error, b.byte_size, b.mime_type, b.nas_bucket, b.nas_key,
               b.verified_at
        from analytics_media_asset_catalog a
        left join analytics_media_blobs b on b.sha256=a.sha256
        where a.history_id=$1
        order by case when a.role='input' then 0 when a.role='output' then 1 else 2 end,
                 a.role, a.ordinal
        """,
        history_id,
    )
    return {"history": _row(history), "assets": _rows(assets)}


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
        if not RANGE_PATTERN.match(range_header):
            raise HTTPException(status_code=416, detail="invalid byte range")
        request_args["Range"] = range_header
        status_code = 206
    response = _nas_client().get_object(**request_args)
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
