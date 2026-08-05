from __future__ import annotations

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
    dependencies=[Depends(require_archive_auth)],
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
