from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query

from .analytics_common import _fetch, _fetchrow, _gather_limited, _row, _rows


router = APIRouter()

GENERATION_HISTORY_PAGE_SIZE = 10


@router.get("/api/generation-history")
async def generation_history(
    task_type: str = Query("", max_length=64),
    sort: Literal["type_count_desc", "created_desc"] = "created_desc",
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    normalized_task_type = task_type.strip()
    offset = (page - 1) * GENERATION_HISTORY_PAGE_SIZE
    if sort == "type_count_desc" and not normalized_task_type:
        rows_query = """
            with type_counts as (
                select coalesce(type, 'unknown') as task_type, count(*)::bigint as generation_count
                from history
                group by 1
            )
            select
                'generation_history_rows' as row_type,
                h.id,
                h.user_id,
                coalesce(nullif(u.full_name, ''), nullif(u.username, ''), '') as nickname,
                coalesce(h.type, 'unknown') as task_type,
                h.source,
                h.prompt,
                h.billing_resolution,
                h.duration,
                h.width,
                h.height,
                case when h.is_favorited is true then 1 else 0 end::int as favorite_count,
                h.rating,
                h.created_at,
                ''::text as input_address,
                ''::text as output_address
            from history h
            join type_counts on type_counts.task_type = coalesce(h.type, 'unknown')
            left join users u on u.id = h.user_id
            order by type_counts.generation_count desc, h.created_at desc, h.id desc
            limit $1::int offset $2::int
        """
        rows_args: tuple[Any, ...] = (GENERATION_HISTORY_PAGE_SIZE, offset)
    else:
        rows_query = """
            select
                'generation_history_rows' as row_type,
                h.id,
                h.user_id,
                coalesce(nullif(u.full_name, ''), nullif(u.username, ''), '') as nickname,
                coalesce(h.type, 'unknown') as task_type,
                h.source,
                h.prompt,
                h.billing_resolution,
                h.duration,
                h.width,
                h.height,
                case when h.is_favorited is true then 1 else 0 end::int as favorite_count,
                h.rating,
                h.created_at,
                ''::text as input_address,
                ''::text as output_address
            from history h
            left join users u on u.id = h.user_id
            where ($1::text = '' or coalesce(h.type, 'unknown') = $1::text)
            order by h.created_at desc, h.id desc
            limit $2::int offset $3::int
        """
        rows_args = (normalized_task_type, GENERATION_HISTORY_PAGE_SIZE, offset)

    total, task_types, rows = await _gather_limited(
        3,
        _fetchrow(
            """
            select 'generation_history_total' as row_type, count(*)::bigint as total
            from history
            where ($1::text = '' or coalesce(type, 'unknown') = $1::text)
            """,
            normalized_task_type,
        ),
        _fetch(
            """
            select
                'generation_history_types' as row_type,
                coalesce(type, 'unknown') as task_type,
                count(*)::bigint as generation_count
            from history
            group by 2
            order by generation_count desc, task_type
            """
        ),
        _fetch(rows_query, *rows_args),
    )
    total_count = int(_row(total).get("total") or 0)
    total_pages = max(1, (total_count + GENERATION_HISTORY_PAGE_SIZE - 1) // GENERATION_HISTORY_PAGE_SIZE)
    return {
        "filters": {"task_type": normalized_task_type, "sort": sort},
        "task_types": _rows(task_types),
        "rows": _rows(rows),
        "pagination": {
            "page": page,
            "limit": GENERATION_HISTORY_PAGE_SIZE,
            "total": total_count,
            "total_pages": total_pages,
        },
    }
