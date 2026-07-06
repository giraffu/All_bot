from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from .analytics_common import (
    GENERATION_OPERATION_TYPES,
    MAX_ANALYTICS_DAYS,
    _chart_days,
    _clamp,
    _clamp_days,
    _fetch,
    _fetchrow,
    _gather_limited,
    _parse_compare_dates,
    _query_days,
    _row,
    _rows,
)


router = APIRouter()


@router.get("/api/generation")
async def generation(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(12, ge=1, le=50),
) -> dict[str, Any]:
    return await _build_generation_payload(days=days, limit=limit)


async def _build_generation_payload(
    *,
    days: int,
    limit: int,
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    chart_days = _chart_days(days)
    limit = _clamp(limit, 1, 50)
    summary_task = _fetchrow(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        recent_history as (
            select *
            from history, bounds
            where created_at >= bounds.since
        ),
        gallery_for_history as (
            select gp.*
            from gallery_posts gp
            where gp.is_active is true
              and exists (
                  select 1
                  from recent_history h
                  where h.task_id = gp.task_id
              )
        ),
        history_stats as (
            select
                count(*)::bigint as generations,
                count(distinct user_id)::bigint as creators,
                count(*) filter (where source = 'web')::bigint as web_generations,
                count(*) filter (where source = 'bot')::bigint as bot_generations,
                count(*) filter (where output_file is not null or extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
                count(*) filter (where input_file is not null and input_file <> '')::bigint as with_input_records,
                count(*) filter (where is_favorited is true)::bigint as favorited_records,
                count(*) filter (where is_public is true)::bigint as public_records,
                coalesce(avg(duration) filter (where duration is not null), 0) as avg_duration,
                coalesce(avg(width) filter (where width is not null), 0) as avg_width,
                coalesce(avg(height) filter (where height is not null), 0) as avg_height,
                max(created_at) as latest_generation_at
            from recent_history
        ),
        gallery_stats as (
            select
                count(*)::bigint as gallery_posts,
                coalesce(sum(likes_count), 0)::bigint as likes,
                coalesce(sum(dislikes_count), 0)::bigint as dislikes,
                coalesce(sum(comments_count), 0)::bigint as comments,
                coalesce(sum(applied_count), 0)::bigint as applies
            from gallery_for_history
        ),
        unlock_stats as (
            select count(*)::bigint as prompt_unlocks
            from gallery_prompt_unlocks, bounds
            where created_at >= bounds.since
        ),
        credit_stats as (
            select
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent,
                count(*)::bigint as debit_events
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change < 0
              and operation_type = any($2::text[])
        ),
        worker_stats as (
            select
                count(*) filter (where lower(status) = 'success')::bigint as worker_successes,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures,
                coalesce(avg(duration) filter (where lower(status) = 'success'), 0) as avg_worker_duration,
                coalesce(percentile_cont(0.95) within group (order by duration) filter (where lower(status) = 'success'), 0) as p95_worker_duration
            from worker_logs, bounds
            where start_time >= bounds.since
        )
        select
            'generation_summary' as row_type,
            (select count(*) from history)::bigint as total_generations,
            history_stats.generations,
            history_stats.creators,
            history_stats.web_generations,
            history_stats.bot_generations,
            history_stats.result_records,
            round(case when history_stats.generations > 0 then history_stats.result_records::numeric / history_stats.generations * 100 else 0 end, 2) as result_rate,
            history_stats.with_input_records,
            round(case when history_stats.generations > 0 then history_stats.with_input_records::numeric / history_stats.generations * 100 else 0 end, 2) as input_rate,
            history_stats.favorited_records,
            round(case when history_stats.generations > 0 then history_stats.favorited_records::numeric / history_stats.generations * 100 else 0 end, 2) as favorite_rate,
            history_stats.public_records,
            round(case when history_stats.generations > 0 then history_stats.public_records::numeric / history_stats.generations * 100 else 0 end, 2) as public_rate,
            gallery_stats.gallery_posts,
            round(case when history_stats.generations > 0 then gallery_stats.gallery_posts::numeric / history_stats.generations * 100 else 0 end, 2) as gallery_rate,
            gallery_stats.likes,
            gallery_stats.dislikes,
            gallery_stats.comments,
            gallery_stats.applies,
            unlock_stats.prompt_unlocks,
            credit_stats.credits_spent,
            round(case when history_stats.generations > 0 then credit_stats.credits_spent::numeric / history_stats.generations else 0 end, 2) as avg_credits_per_generation,
            worker_stats.worker_successes,
            worker_stats.worker_failures,
            round(case when worker_stats.worker_successes + worker_stats.worker_failures > 0 then worker_stats.worker_failures::numeric / (worker_stats.worker_successes + worker_stats.worker_failures) * 100 else 0 end, 2) as worker_failure_rate,
            worker_stats.avg_worker_duration,
            worker_stats.p95_worker_duration,
            history_stats.latest_generation_at,
            history_stats.avg_duration,
            history_stats.avg_width,
            history_stats.avg_height
        from history_stats, gallery_stats, unlock_stats, credit_stats, worker_stats
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    daily_task = _fetch(
        """
        with days as (
            select generate_series(
                current_date - (($1::int - 1) * interval '1 day'),
                current_date,
                interval '1 day'
            )::date as day
        ),
        history_daily as (
            select
                created_at::date as day,
                count(*)::bigint as generations,
                count(distinct user_id)::bigint as creators,
                count(*) filter (where source = 'web')::bigint as web_generations,
                count(*) filter (where source = 'bot')::bigint as bot_generations,
                count(*) filter (where output_file is not null or extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
                count(*) filter (where is_public is true)::bigint as public_records,
                count(*) filter (where is_favorited is true)::bigint as favorited_records
            from history
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        gallery_daily as (
            select
                h.created_at::date as day,
                count(distinct gp.id)::bigint as gallery_posts
            from history h
            join gallery_posts gp on gp.task_id = h.task_id and gp.is_active is true
            where h.created_at >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        credit_daily as (
            select
                created_at::date as day,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent
            from user_logs
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
              and credit_change < 0
              and operation_type = any($2::text[])
            group by 1
        ),
        worker_daily as (
            select
                start_time::date as day,
                count(*) filter (where lower(status) = 'success')::bigint as worker_successes,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures
            from worker_logs
            where start_time >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        )
        select
            'generation_daily' as row_type,
            to_char(days.day, 'YYYY-MM-DD') as day,
            coalesce(history_daily.generations, 0)::bigint as generations,
            coalesce(history_daily.creators, 0)::bigint as creators,
            coalesce(history_daily.web_generations, 0)::bigint as web_generations,
            coalesce(history_daily.bot_generations, 0)::bigint as bot_generations,
            coalesce(history_daily.result_records, 0)::bigint as result_records,
            coalesce(history_daily.public_records, 0)::bigint as public_records,
            coalesce(history_daily.favorited_records, 0)::bigint as favorited_records,
            coalesce(gallery_daily.gallery_posts, 0)::bigint as gallery_posts,
            coalesce(credit_daily.credits_spent, 0)::bigint as credits_spent,
            coalesce(worker_daily.worker_successes, 0)::bigint as worker_successes,
            coalesce(worker_daily.worker_failures, 0)::bigint as worker_failures
        from days
        left join history_daily using (day)
        left join gallery_daily using (day)
        left join credit_daily using (day)
        left join worker_daily using (day)
        order by days.day
        """,
        chart_days,
        GENERATION_OPERATION_TYPES,
    )
    by_type_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        h_type as (
            select
                coalesce(h.type, 'unknown') as task_type,
                count(*)::bigint as generations,
                count(distinct h.user_id)::bigint as creators,
                count(*) filter (where h.output_file is not null or h.extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
                count(*) filter (where h.input_file is not null and h.input_file <> '')::bigint as with_input,
                count(*) filter (where h.is_favorited is true)::bigint as favorited_records,
                count(*) filter (where h.is_public is true)::bigint as public_records,
                coalesce(avg(h.duration) filter (where h.duration is not null), 0) as avg_duration
            from history h, bounds
            where h.created_at >= bounds.since
            group by 1
        ),
        gallery_type as (
            select
                coalesce(h.type, 'unknown') as task_type,
                count(distinct gp.id)::bigint as gallery_posts,
                coalesce(sum(gp.likes_count), 0)::bigint as likes,
                coalesce(sum(gp.dislikes_count), 0)::bigint as dislikes,
                coalesce(sum(gp.comments_count), 0)::bigint as comments,
                coalesce(sum(gp.applied_count), 0)::bigint as applies
            from history h
            join gallery_posts gp on gp.task_id = h.task_id and gp.is_active is true,
            bounds
            where h.created_at >= bounds.since
            group by 1
        ),
        credit_type as (
            select
                operation_type as task_type,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change < 0
              and operation_type = any($2::text[])
            group by 1
        ),
        worker_type as (
            select
                coalesce(task_type, 'unknown') as task_type,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures,
                count(*) filter (where lower(status) in ('success', 'failed'))::bigint as worker_events,
                coalesce(avg(duration) filter (where lower(status) = 'success'), 0) as avg_worker_duration
            from worker_logs, bounds
            where start_time >= bounds.since
            group by 1
        ),
        type_keys as (
            select task_type from h_type
            union
            select task_type from credit_type
            union
            select task_type from worker_type
        )
        select
            'generation_by_type' as row_type,
            type_keys.task_type,
            coalesce(h_type.generations, 0)::bigint as generations,
            coalesce(h_type.creators, 0)::bigint as creators,
            coalesce(h_type.result_records, 0)::bigint as result_records,
            round(case when coalesce(h_type.generations, 0) > 0 then h_type.result_records::numeric / h_type.generations * 100 else 0 end, 2) as result_rate,
            coalesce(h_type.with_input, 0)::bigint as with_input,
            round(case when coalesce(h_type.generations, 0) > 0 then h_type.with_input::numeric / h_type.generations * 100 else 0 end, 2) as input_rate,
            coalesce(h_type.favorited_records, 0)::bigint as favorited_records,
            round(case when coalesce(h_type.generations, 0) > 0 then h_type.favorited_records::numeric / h_type.generations * 100 else 0 end, 2) as favorite_rate,
            coalesce(h_type.public_records, 0)::bigint as public_records,
            round(case when coalesce(h_type.generations, 0) > 0 then h_type.public_records::numeric / h_type.generations * 100 else 0 end, 2) as public_rate,
            coalesce(gallery_type.gallery_posts, 0)::bigint as gallery_posts,
            round(case when coalesce(h_type.generations, 0) > 0 then coalesce(gallery_type.gallery_posts, 0)::numeric / h_type.generations * 100 else 0 end, 2) as gallery_rate,
            coalesce(gallery_type.likes, 0)::bigint as likes,
            coalesce(gallery_type.dislikes, 0)::bigint as dislikes,
            coalesce(gallery_type.comments, 0)::bigint as comments,
            coalesce(gallery_type.applies, 0)::bigint as applies,
            coalesce(credit_type.credits_spent, 0)::bigint as credits_spent,
            round(case when coalesce(h_type.generations, 0) > 0 then coalesce(credit_type.credits_spent, 0)::numeric / h_type.generations else 0 end, 2) as avg_credits_per_generation,
            coalesce(worker_type.worker_failures, 0)::bigint as worker_failures,
            round(case when coalesce(worker_type.worker_events, 0) > 0 then worker_type.worker_failures::numeric / worker_type.worker_events * 100 else 0 end, 2) as worker_failure_rate,
            coalesce(worker_type.avg_worker_duration, 0) as avg_worker_duration,
            coalesce(h_type.avg_duration, 0) as avg_duration
        from type_keys
        left join h_type using (task_type)
        left join gallery_type using (task_type)
        left join credit_type using (task_type)
        left join worker_type using (task_type)
        order by generations desc
        limit 50
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    credits_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            'generation_credits' as row_type,
            operation_type as task_type,
            count(*)::bigint as debit_events,
            abs(coalesce(sum(credit_change), 0))::bigint as credits_spent,
            coalesce(avg(abs(credit_change)), 0) as avg_credits_per_event
        from user_logs, bounds
        where created_at >= bounds.since
          and credit_change < 0
          and operation_type = any($2::text[])
        group by operation_type
        order by credits_spent desc
        limit 50
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    hourly_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            'generation_hourly' as row_type,
            extract(hour from created_at)::int as hour,
            count(*)::bigint as generations,
            count(distinct user_id)::bigint as creators
        from history, bounds
        where created_at >= bounds.since
        group by 2
        order by 2
        """,
        query_days,
    )
    source_mix_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            'generation_source_mix' as row_type,
            case
                when source = 'web' then 'Web'
                when source = 'bot' then 'Bot'
                else '未知来源'
            end as label,
            coalesce(source, 'unknown') as source,
            count(*)::bigint as count,
            count(distinct user_id)::bigint as creators
        from history, bounds
        where created_at >= bounds.since
        group by 2, 3
        order by count desc
        """,
        query_days,
    )
    quality_segments_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        recent_history as (
            select *
            from history, bounds
            where created_at >= bounds.since
        ),
        gallery_tasks as (
            select distinct task_id
            from gallery_posts
            where is_active is true
        )
        select 'generation_quality_segments' as row_type, '有输出' as label,
               count(*) filter (where output_file is not null or extra_outputs::text not in ('{}', 'null', ''))::bigint as count
        from recent_history
        union all
        select 'generation_quality_segments', '无输出',
               count(*) filter (where output_file is null and coalesce(extra_outputs::text, 'null') in ('{}', 'null', ''))::bigint
        from recent_history
        union all
        select 'generation_quality_segments', '有输入',
               count(*) filter (where input_file is not null and input_file <> '')::bigint
        from recent_history
        union all
        select 'generation_quality_segments', '公开',
               count(*) filter (where is_public is true)::bigint
        from recent_history
        union all
        select 'generation_quality_segments', '收藏',
               count(*) filter (where is_favorited is true)::bigint
        from recent_history
        union all
        select 'generation_quality_segments', 'Gallery 投稿',
               count(*) filter (where exists (select 1 from gallery_tasks where gallery_tasks.task_id = recent_history.task_id))::bigint
        from recent_history
        """,
        query_days,
    )
    generation_leaderboard_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        user_generation as (
            select
                h.user_id,
                count(distinct h.id)::bigint as generations,
                count(distinct h.id) filter (where h.output_file is not null or h.extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
                count(distinct gp.id) filter (where gp.is_active is true)::bigint as gallery_posts,
                max(h.created_at) as last_generation_at
            from history h
            left join gallery_posts gp on gp.task_id = h.task_id,
            bounds
            where h.created_at >= bounds.since
              and h.user_id is not null
            group by h.user_id
        )
        select
            'generation_user_rank' as row_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            user_generation.generations,
            user_generation.result_records,
            user_generation.gallery_posts,
            user_generation.last_generation_at
        from user_generation
        join users u on u.id = user_generation.user_id
        order by user_generation.generations desc, u.id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    credit_leaderboard_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        user_credits as (
            select
                user_id,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent,
                count(*)::bigint as debit_events,
                coalesce(avg(abs(credit_change)), 0) as avg_credits_per_event
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change < 0
              and operation_type = any($2::text[])
              and user_id is not null
            group by user_id
        )
        select
            'generation_credit_user_rank' as row_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            user_credits.credits_spent,
            user_credits.debit_events,
            user_credits.avg_credits_per_event,
            u.credits as current_balance
        from user_credits
        join users u on u.id = user_credits.user_id
        order by user_credits.credits_spent desc, u.id desc
        limit $3::int
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
        limit,
    )
    gallery_leaderboard_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        user_gallery as (
            select
                gp.user_id,
                count(*)::bigint as gallery_posts,
                coalesce(sum(gp.likes_count), 0)::bigint as likes,
                coalesce(sum(gp.dislikes_count), 0)::bigint as dislikes,
                coalesce(sum(gp.comments_count), 0)::bigint as comments,
                coalesce(sum(gp.applied_count), 0)::bigint as applies,
                max(gp.created_at) as latest_post_at
            from gallery_posts gp, bounds
            where gp.created_at >= bounds.since
              and gp.is_active is true
              and gp.user_id is not null
            group by gp.user_id
        )
        select
            'generation_gallery_user_rank' as row_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            user_gallery.gallery_posts,
            user_gallery.likes,
            user_gallery.dislikes,
            user_gallery.comments,
            user_gallery.applies,
            (user_gallery.gallery_posts * 8 + user_gallery.likes * 2 - user_gallery.dislikes + user_gallery.comments * 2 + user_gallery.applies * 5)::bigint as signal_score,
            user_gallery.latest_post_at
        from user_gallery
        join users u on u.id = user_gallery.user_id
        order by signal_score desc, u.id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    recent_high_signal_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        recent as (
            select
                h.id as history_id,
                h.task_id,
                coalesce(h.type, 'unknown') as task_type,
                h.user_id,
                h.is_favorited,
                h.is_public,
                h.created_at,
                gp.media_type,
                coalesce(gp.likes_count, 0)::bigint as likes,
                coalesce(gp.dislikes_count, 0)::bigint as dislikes,
                coalesce(gp.comments_count, 0)::bigint as comments,
                coalesce(gp.applied_count, 0)::bigint as applies,
                (
                    case when h.is_favorited is true then 10 else 0 end
                    + case when h.is_public is true then 6 else 0 end
                    + case when gp.id is not null then 12 else 0 end
                    + coalesce(gp.likes_count, 0) * 2
                    - coalesce(gp.dislikes_count, 0)
                    + coalesce(gp.comments_count, 0) * 2
                    + coalesce(gp.applied_count, 0) * 5
                )::bigint as signal_score
            from history h
            left join gallery_posts gp on gp.task_id = h.task_id and gp.is_active is true,
            bounds
            where h.created_at >= bounds.since
        )
        select
            'generation_recent_high_signal' as row_type,
            recent.history_id,
            recent.task_id,
            recent.task_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            recent.media_type,
            recent.likes,
            recent.dislikes,
            recent.comments,
            recent.applies,
            recent.is_favorited,
            recent.is_public,
            recent.created_at,
            recent.signal_score
        from recent
        left join users u on u.id = recent.user_id
        where recent.signal_score > 0
        order by recent.signal_score desc, recent.created_at desc, recent.history_id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    (
        summary,
        daily,
        by_type,
        credits,
        hourly,
        source_mix,
        quality_segments,
        generation_leaderboard,
        credit_leaderboard,
        gallery_leaderboard,
        recent_high_signal,
    ) = await _gather_limited(
        4,
        summary_task,
        daily_task,
        by_type_task,
        credits_task,
        hourly_task,
        source_mix_task,
        quality_segments_task,
        generation_leaderboard_task,
        credit_leaderboard_task,
        gallery_leaderboard_task,
        recent_high_signal_task,
    )
    return {
        "days": days,
        "limit": limit,
        "summary": _row(summary),
        "daily": _rows(daily),
        "by_type": _rows(by_type),
        "credits": _rows(credits),
        "hourly": _rows(hourly),
        "source_mix": _rows(source_mix),
        "quality_segments": _rows(quality_segments),
        "leaderboards": {
            "generation": _rows(generation_leaderboard),
            "credits": _rows(credit_leaderboard),
            "gallery": _rows(gallery_leaderboard),
        },
        "recent_high_signal": _rows(recent_high_signal),
    }


@router.get("/api/generation/hourly-comparison")
async def generation_hourly_comparison(
    dates: str = Query(..., description="Comma-separated YYYY-MM-DD values, max 3"),
) -> dict[str, Any]:
    compare_dates = _parse_compare_dates(dates)
    hourly = await _fetch(
        """
        with selected_dates as (
            select unnest($1::text[]) as selected_date
        ),
        hours as (
            select generate_series(0, 23)::int as hour
        ),
        grid as (
            select selected_dates.selected_date, hours.hour
            from selected_dates
            cross join hours
        ),
        history_hourly as (
            select
                to_char(created_at::date, 'YYYY-MM-DD') as selected_date,
                extract(hour from created_at)::int as hour,
                count(*)::bigint as generations,
                count(distinct user_id)::bigint as creators,
                count(*) filter (where source = 'web')::bigint as web_generations,
                count(*) filter (where source = 'bot')::bigint as bot_generations
            from history
            where to_char(created_at::date, 'YYYY-MM-DD') = any($1::text[])
            group by 1, 2
        ),
        credit_hourly as (
            select
                to_char(created_at::date, 'YYYY-MM-DD') as selected_date,
                extract(hour from created_at)::int as hour,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent
            from user_logs
            where to_char(created_at::date, 'YYYY-MM-DD') = any($1::text[])
              and credit_change < 0
              and operation_type = any($2::text[])
            group by 1, 2
        ),
        worker_hourly as (
            select
                to_char(start_time::date, 'YYYY-MM-DD') as selected_date,
                extract(hour from start_time)::int as hour,
                count(*) filter (where lower(status) = 'success')::bigint as worker_successes,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures
            from worker_logs
            where to_char(start_time::date, 'YYYY-MM-DD') = any($1::text[])
            group by 1, 2
        )
        select
            'generation_hourly_comparison' as row_type,
            grid.selected_date as date,
            grid.hour,
            coalesce(history_hourly.generations, 0)::bigint as generations,
            coalesce(history_hourly.creators, 0)::bigint as creators,
            coalesce(history_hourly.web_generations, 0)::bigint as web_generations,
            coalesce(history_hourly.bot_generations, 0)::bigint as bot_generations,
            coalesce(credit_hourly.credits_spent, 0)::bigint as credits_spent,
            coalesce(worker_hourly.worker_successes, 0)::bigint as worker_successes,
            coalesce(worker_hourly.worker_failures, 0)::bigint as worker_failures
        from grid
        left join history_hourly
          on history_hourly.selected_date = grid.selected_date
         and history_hourly.hour = grid.hour
        left join credit_hourly
          on credit_hourly.selected_date = grid.selected_date
         and credit_hourly.hour = grid.hour
        left join worker_hourly
          on worker_hourly.selected_date = grid.selected_date
         and worker_hourly.hour = grid.hour
        order by array_position($1::text[], grid.selected_date), grid.hour
        """,
        compare_dates,
        GENERATION_OPERATION_TYPES,
    )
    return {"dates": compare_dates, "hourly": _rows(hourly)}


@router.get("/api/generation/hourly-cumulative")
async def generation_hourly_cumulative(
    days: int = Query(30, ge=1, le=MAX_ANALYTICS_DAYS),
) -> dict[str, Any]:
    days = _clamp(days, 1, MAX_ANALYTICS_DAYS)
    hourly = await _fetch(
        """
        with hours as (
            select generate_series(0, 23)::int as hour
        ),
        history_hourly as (
            select
                extract(hour from created_at)::int as hour,
                count(*)::bigint as generations,
                count(distinct user_id)::bigint as creators,
                count(*) filter (where source = 'web')::bigint as web_generations,
                count(*) filter (where source = 'bot')::bigint as bot_generations
            from history
            where created_at >= now() - ($1::int * interval '1 day')
            group by 1
        ),
        credit_hourly as (
            select
                extract(hour from created_at)::int as hour,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent
            from user_logs
            where created_at >= now() - ($1::int * interval '1 day')
              and credit_change < 0
              and operation_type = any($2::text[])
            group by 1
        ),
        worker_hourly as (
            select
                extract(hour from start_time)::int as hour,
                count(*) filter (where lower(status) = 'success')::bigint as worker_successes,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures
            from worker_logs
            where start_time >= now() - ($1::int * interval '1 day')
            group by 1
        )
        select
            'generation_hourly_cumulative' as row_type,
            hours.hour,
            coalesce(history_hourly.generations, 0)::bigint as generations,
            coalesce(history_hourly.creators, 0)::bigint as creators,
            coalesce(history_hourly.web_generations, 0)::bigint as web_generations,
            coalesce(history_hourly.bot_generations, 0)::bigint as bot_generations,
            coalesce(credit_hourly.credits_spent, 0)::bigint as credits_spent,
            coalesce(worker_hourly.worker_successes, 0)::bigint as worker_successes,
            coalesce(worker_hourly.worker_failures, 0)::bigint as worker_failures
        from hours
        left join history_hourly using (hour)
        left join credit_hourly using (hour)
        left join worker_hourly using (hour)
        order by hours.hour
        """,
        days,
        GENERATION_OPERATION_TYPES,
    )
    return {"days": days, "hourly": _rows(hourly)}


@router.get("/api/generation/type-comparison")
async def generation_type_comparison(
    dates: str = Query(..., description="Comma-separated YYYY-MM-DD values, max 3"),
) -> dict[str, Any]:
    compare_dates = _parse_compare_dates(dates)
    type_rows = await _fetch(
        """
        select
            'generation_type_comparison' as row_type,
            to_char(created_at::date, 'YYYY-MM-DD') as date,
            coalesce(type, 'unknown') as task_type,
            count(*)::bigint as generations,
            count(distinct user_id)::bigint as creators
        from history
        where to_char(created_at::date, 'YYYY-MM-DD') = any($1::text[])
        group by 2, 3
        order by array_position($1::text[], to_char(created_at::date, 'YYYY-MM-DD')), generations desc, task_type
        """,
        compare_dates,
    )
    return {"dates": compare_dates, "types": _rows(type_rows)}
