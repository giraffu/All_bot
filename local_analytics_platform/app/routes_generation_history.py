from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Query

from .analytics_common import _fetch, _fetchrow, _gather_limited, _row, _rows


router = APIRouter()
GENERATION_HISTORY_PAGE_SIZE = 10

MEDIA_COLUMNS_SQL = """
    '/api/generation-history/' || h.id || '/media?role_group=input' input_address,
    '/api/generation-history/' || h.id || '/media?role_group=output' output_address,
    coalesce(media.input_asset_count,0)::int input_asset_count,
    coalesce(media.input_verified_count,0)::int input_verified_count,
    coalesce(media.output_asset_count,0)::int output_asset_count,
    coalesce(media.output_verified_count,0)::int output_verified_count,
    coalesce(media.asset_count,0)::int asset_count,
    coalesce(media.verified_count,0)::int verified_count,
    coalesce(media.problem_count,0)::int problem_count
"""

MEDIA_JOIN_SQL = """
    left join lateral (
      select count(*) asset_count,
        count(*) filter (where role='input') input_asset_count,
        count(*) filter (where role='input' and status='archived_verified') input_verified_count,
        count(*) filter (where role<>'input') output_asset_count,
        count(*) filter (where role<>'input' and status='archived_verified') output_verified_count,
        count(*) filter (where status='archived_verified') verified_count,
        count(*) filter (where status in ('source_offline','provisional_missing','confirmed_lost','checksum_error')) problem_count
      from analytics_media_asset_catalog a where a.history_id=h.id
    ) media on true
"""

FILTER_SQL = """
  ($1::text = '' or coalesce(h.type, 'unknown') = $1::text)
  and ($2::bigint is null or h.id = $2::bigint)
  and ($3::text = '' or coalesce(h.task_id, '') = $3::text)
  and ($4::bigint is null or h.user_id = $4::bigint)
  and ($5::date is null or h.created_at >= $5::date)
  and ($6::date is null or h.created_at < ($6::date + interval '1 day'))
  and ($7::text = '' or exists (
    select 1 from analytics_media_asset_catalog a where a.history_id=h.id and a.status=$7::text))
  and ($8::text = '' or exists (
    select 1 from analytics_media_asset_catalog a where a.history_id=h.id and a.role=$8::text))
  and ($9::text = '' or exists (
    select 1 from analytics_media_asset_catalog a where a.history_id=h.id and a.found_source=$9::text))
  and ($10::boolean is false or exists (
    select 1 from analytics_media_asset_catalog a where a.history_id=h.id
    and a.status in ('source_offline','provisional_missing','confirmed_lost','checksum_error')))
  and ($11::text = '' or (
    $11::text = '__unrecorded__'
    and coalesce(h.type, '') in (
      'minimax_h3_t2v', 'minimax_h3_i2v', 'minimax_h3_flf2v', 'minimax_h3_ref2v'
    )
    and coalesce(h.extra_outputs->'_minimax_h3_context'->>'main_model', '') = ''
  ) or coalesce(h.extra_outputs->'_minimax_h3_context'->>'main_model', '') = $11::text)
"""

H3_MAIN_MODEL_SQL = """
    coalesce(h.extra_outputs->'_minimax_h3_context'->>'main_model', '') h3_main_model
"""

H3_MAIN_MODELS_QUERY = """
    select 'generation_history_h3_main_models' row_type,
      h.extra_outputs->'_minimax_h3_context'->>'main_model' main_model,
      count(*)::bigint generation_count
    from history h
    where coalesce(h.extra_outputs->'_minimax_h3_context'->>'main_model', '') <> ''
    group by 2
    order by generation_count desc, main_model
"""


@router.get("/api/generation-history")
async def generation_history(
    task_type: str = Query("", max_length=64),
    history_id: int | None = Query(None, ge=1),
    task_id: str = Query("", max_length=128),
    user_id: int | None = Query(None, ge=1),
    date_from: date | None = None,
    date_to: date | None = None,
    archive_status: str = Query("", max_length=32),
    asset_role: str = Query("", max_length=64),
    archive_source: str = Query("", max_length=128),
    loss_only: bool = False,
    h3_main_model: str = Query("", max_length=64),
    sort: Literal["type_count_desc", "created_desc"] = "created_desc",
    page: int = Query(1, ge=1),
) -> dict[str, Any]:
    normalized_task_type = task_type.strip()
    normalized_h3_main_model = h3_main_model.strip().lower()
    advanced = any(
        value not in (None, "", False)
        for value in (
            history_id,
            task_id.strip(),
            user_id,
            date_from,
            date_to,
            archive_status.strip(),
            asset_role.strip(),
            archive_source.strip(),
            loss_only,
            normalized_h3_main_model,
        )
    )
    if not advanced:
        offset = (page - 1) * GENERATION_HISTORY_PAGE_SIZE
        if sort == "type_count_desc" and not normalized_task_type:
            rows_query = f"""
                with type_counts as (
                    select coalesce(type, 'unknown') task_type, count(*)::bigint generation_count
                    from history group by 1
                )
                select 'generation_history_rows' row_type, h.id, h.task_id, h.user_id,
                    coalesce(nullif(u.full_name,''),nullif(u.username,''),'') nickname,
                    coalesce(h.type,'unknown') task_type, h.source, h.prompt, h.billing_resolution,
                    h.duration,h.width,h.height,case when h.is_favorited then 1 else 0 end::int favorite_count,
                    h.rating,h.created_at,{H3_MAIN_MODEL_SQL},{MEDIA_COLUMNS_SQL}
                from history h join type_counts on type_counts.task_type=coalesce(h.type,'unknown')
                left join users u on u.id=h.user_id
                {MEDIA_JOIN_SQL}
                order by type_counts.generation_count desc,h.created_at desc,h.id desc limit $1::int offset $2::int
            """
            rows_args = (GENERATION_HISTORY_PAGE_SIZE, offset)
        else:
            rows_query = f"""
                select 'generation_history_rows' row_type, h.id, h.task_id, h.user_id,
                    coalesce(nullif(u.full_name,''),nullif(u.username,''),'') nickname,
                    coalesce(h.type,'unknown') task_type,h.source,h.prompt,h.billing_resolution,
                    h.duration,h.width,h.height,case when h.is_favorited then 1 else 0 end::int favorite_count,
                    h.rating,h.created_at,{H3_MAIN_MODEL_SQL},{MEDIA_COLUMNS_SQL}
                from history h left join users u on u.id=h.user_id
                {MEDIA_JOIN_SQL}
                where ($1::text='' or coalesce(h.type,'unknown')=$1::text)
                order by h.created_at desc,h.id desc limit $2::int offset $3::int
            """
            rows_args = (normalized_task_type, GENERATION_HISTORY_PAGE_SIZE, offset)
        total, task_types, h3_main_models, rows = await _gather_limited(
            4,
            _fetchrow(
                """select 'generation_history_total' row_type,count(*)::bigint total from history
                         where ($1::text='' or coalesce(type,'unknown')=$1::text)""",
                normalized_task_type,
            ),
            _fetch("""select 'generation_history_types' row_type,coalesce(type,'unknown') task_type,
                       count(*)::bigint generation_count from history group by 2
                       order by generation_count desc,task_type"""),
            _fetch(H3_MAIN_MODELS_QUERY),
            _fetch(rows_query, *rows_args),
        )
        total_count = int(_row(total).get("total") or 0)
        total_pages = max(
            1,
            (total_count + GENERATION_HISTORY_PAGE_SIZE - 1)
            // GENERATION_HISTORY_PAGE_SIZE,
        )
        return {
            "filters": {
                "task_type": normalized_task_type,
                "h3_main_model": normalized_h3_main_model,
                "sort": sort,
            },
            "task_types": _rows(task_types),
            "h3_main_models": _rows(h3_main_models),
            "rows": _rows(rows),
            "pagination": {
                "page": page,
                "limit": GENERATION_HISTORY_PAGE_SIZE,
                "total": total_count,
                "total_pages": total_pages,
            },
        }
    filters = (
        normalized_task_type,
        history_id,
        task_id.strip(),
        user_id,
        date_from,
        date_to,
        archive_status.strip(),
        asset_role.strip(),
        archive_source.strip(),
        loss_only,
        normalized_h3_main_model,
    )
    offset = (page - 1) * GENERATION_HISTORY_PAGE_SIZE
    order_sql = (
        "type_counts.generation_count desc, h.created_at desc, h.id desc"
        if sort == "type_count_desc"
        else "h.created_at desc, h.id desc"
    )
    type_join = (
        """
      join (select coalesce(type,'unknown') task_type, count(*)::bigint generation_count
            from history group by 1) type_counts
        on type_counts.task_type=coalesce(h.type,'unknown')
    """
        if sort == "type_count_desc"
        else ""
    )
    rows_query = f"""
      select h.id, h.task_id, h.user_id,
        coalesce(nullif(u.full_name,''),nullif(u.username,''),'') nickname,
        coalesce(h.type,'unknown') task_type, h.source, h.prompt, h.billing_resolution,
        h.duration, h.width, h.height, case when h.is_favorited then 1 else 0 end::int favorite_count,
        h.rating, h.created_at, {H3_MAIN_MODEL_SQL}, {MEDIA_COLUMNS_SQL}
      from history h left join users u on u.id=h.user_id {type_join}
      {MEDIA_JOIN_SQL}
      where {FILTER_SQL}
      order by {order_sql} limit $12::int offset $13::int
    """
    total, task_types, h3_main_models, rows = await _gather_limited(
        4,
        _fetchrow(
            f"select count(*)::bigint total from history h where {FILTER_SQL}", *filters
        ),
        _fetch("""select coalesce(type,'unknown') task_type, count(*)::bigint generation_count
                  from history group by 1 order by generation_count desc, task_type"""),
        _fetch(H3_MAIN_MODELS_QUERY),
        _fetch(rows_query, *filters, GENERATION_HISTORY_PAGE_SIZE, offset),
    )
    total_count = int(_row(total).get("total") or 0)
    total_pages = max(
        1,
        (total_count + GENERATION_HISTORY_PAGE_SIZE - 1)
        // GENERATION_HISTORY_PAGE_SIZE,
    )
    return {
        "filters": {
            "task_type": normalized_task_type,
            "history_id": history_id,
            "task_id": task_id.strip(),
            "user_id": user_id,
            "date_from": date_from,
            "date_to": date_to,
            "archive_status": archive_status.strip(),
            "asset_role": asset_role.strip(),
            "archive_source": archive_source.strip(),
            "loss_only": loss_only,
            "h3_main_model": normalized_h3_main_model,
            "sort": sort,
        },
        "task_types": _rows(task_types),
        "h3_main_models": _rows(h3_main_models),
        "rows": _rows(rows),
        "pagination": {
            "page": page,
            "limit": GENERATION_HISTORY_PAGE_SIZE,
            "total": total_count,
            "total_pages": total_pages,
        },
    }
