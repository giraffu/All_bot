from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from .analytics_common import (
    MAX_ANALYTICS_DAYS,
    _clamp,
    _clamp_days,
    _classify_refs,
    _extract_refs,
    _fetch,
    _media_base_url,
    _media_bucket,
    _media_url,
    _query_days,
    _row,
)


router = APIRouter()


@router.get("/api/media-audit")
async def media_audit(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(100, ge=1, le=300),
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    limit = _clamp(limit, 1, 300)
    rows = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            id,
            task_id,
            user_id,
            type as task_type,
            input_file,
            output_file,
            extra_outputs,
            created_at,
            source,
            width,
            height,
            duration
        from history, bounds
        where created_at >= bounds.since
          and (
              input_file is not null
              or output_file is not null
              or extra_outputs::text not in ('{}', 'null', '')
          )
        order by created_at desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    records = []
    totals = {"input_refs": 0, "output_refs": 0, "images": 0, "videos": 0, "with_output": 0}
    for record in rows:
        item = _row(record)
        input_refs = _extract_refs(item.pop("input_file", None))
        output_refs = _extract_refs(item.pop("output_file", None)) + _extract_refs(item.pop("extra_outputs", None))
        input_media = _classify_refs(input_refs)
        output_media = _classify_refs(output_refs)
        totals["input_refs"] += input_media["total"]
        totals["output_refs"] += output_media["total"]
        totals["images"] += input_media["images"] + output_media["images"]
        totals["videos"] += input_media["videos"] + output_media["videos"]
        if output_refs:
            totals["with_output"] += 1
        item["input_refs"] = input_refs[:8]
        item["output_refs"] = output_refs[:8]
        item["media"] = {"input": input_media, "output": output_media}
        item["primary_output_url"] = _media_url(output_refs[0]) if output_refs else None
        records.append(item)
    return {
        "days": days,
        "limit": limit,
        "media_bucket": _media_bucket(),
        "media_url_enabled": bool(_media_base_url()),
        "totals": totals,
        "records": records,
    }
