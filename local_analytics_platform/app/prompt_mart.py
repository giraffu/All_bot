from __future__ import annotations

from typing import Any


PROMPT_NORMALIZATION_VERSION = "v4-task-type-prefix-strip"
PROMPT_NORMALIZE_SQL_TEMPLATE = """
trim(
  regexp_replace(
    regexp_replace(
      regexp_replace(
        regexp_replace(
          regexp_replace(
            translate(
              casefold(normalize(coalesce(__VALUE__, ''), NFKC)),
              chr(8203) || chr(8204) || chr(8205) || chr(8206) || chr(8207) || chr(8234) || chr(8235) || chr(8236) || chr(8237) || chr(8238) || chr(8288) || chr(65279),
              ''
            ),
            '\\s+', ' ', 'g'
          ),
          '[[:cntrl:]]+', '', 'g'
        ),
        '^(\\s*\\[[^\\]]*\\]\\s*)+', '', 'g'
      ),
      '\\s*([,.;:!?()\\[\\]{}<>，。！？、；：（）【】《》])\\s*', '\\1', 'g'
    ),
    '([,.;:!?，。！？、；：])\\1+', '\\1', 'g'
  )
)
"""


def prompt_normalize_sql(value_sql: str) -> str:
    return PROMPT_NORMALIZE_SQL_TEMPLATE.replace("__VALUE__", value_sql)


PROMPT_MART_READY_SQL = """
select
    to_regclass('public.analytics_prompt_group_stats') is not null
    and to_regclass('public.analytics_prompt_occurrence') is not null
    and to_regclass('public.analytics_prompt_dim') is not null
    and to_regclass('public.analytics_prompt_rollup_stats') is not null
    as ready
"""


PROMPT_MART_STATUS_SQL = """
select
    (select count(*)::bigint from analytics_prompt_dim) as prompt_count,
    (select count(*)::bigint from analytics_prompt_occurrence) as occurrence_count,
    (select count(*)::bigint from analytics_prompt_group_stats) as group_stats_count,
    (select count(*)::bigint from analytics_prompt_rollup_stats) as rollup_stats_count,
    (select max(updated_at) from analytics_prompt_group_stats) as stats_updated_at,
    (select value from analytics_prompt_mart_state where key = 'last_history_id') as last_history_id,
    (select value from analytics_prompt_mart_state where key = 'last_refresh_mode') as last_refresh_mode,
    (select value from analytics_prompt_mart_state where key = 'normalization_version') as normalization_version
"""


CREATE_PROMPT_MART_SCHEMA_SQL = [
    """
    create table if not exists analytics_prompt_mart_state (
        key text primary key,
        value text not null,
        updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists analytics_prompt_dim (
        prompt_hash text primary key,
        prompt text not null,
        char_count integer not null,
        builtin_template_key text,
        first_seen timestamp,
        last_seen timestamp,
        occurrence_count bigint not null default 0,
        updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists analytics_prompt_occurrence (
        history_id bigint primary key,
        prompt_hash text not null,
        raw_prompt text not null,
        prompt text not null,
        char_count integer not null,
        task_id text,
        user_id bigint,
        task_type text,
        created_at timestamp,
        is_favorited boolean,
        is_public boolean,
        allow_contribute boolean,
        source text,
        builtin_template_key text,
        input_file text,
        output_file text,
        extra_outputs jsonb,
        width integer,
        height integer,
        duration integer,
        result_rating integer not null default 0,
        updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists analytics_prompt_group_stats (
        scope_key text not null,
        prompt_hash text not null,
        prompt text not null,
        char_count integer not null,
        uses bigint not null,
        users bigint not null,
        variant_count bigint not null default 1,
        task_types text[] not null default '{}',
        first_seen timestamp,
        last_seen timestamp,
        favorite_records bigint not null default 0,
        public_records bigint not null default 0,
        gallery_posts bigint not null default 0,
        likes bigint not null default 0,
        dislikes bigint not null default 0,
        comments bigint not null default 0,
        applies bigint not null default 0,
        prompt_unlocks bigint not null default 0,
        derived_uses bigint not null default 0,
        builtin_template_uses bigint not null default 0,
        builtin_template_keys text[] not null default '{}',
        source_template_posts bigint not null default 0,
        value_score numeric(20, 2) not null default 0,
        updated_at timestamptz not null default now(),
        primary key (scope_key, prompt_hash)
    )
    """,
    """
    create table if not exists analytics_prompt_rollup_stats (
        period_days integer not null,
        scope_key text not null,
        prompt_hash text not null,
        prompt text not null,
        char_count integer not null,
        uses bigint not null,
        users bigint not null,
        variant_count bigint not null default 1,
        task_types text[] not null default '{}',
        first_seen timestamp,
        last_seen timestamp,
        favorite_records bigint not null default 0,
        public_records bigint not null default 0,
        gallery_posts bigint not null default 0,
        likes bigint not null default 0,
        dislikes bigint not null default 0,
        comments bigint not null default 0,
        applies bigint not null default 0,
        prompt_unlocks bigint not null default 0,
        derived_uses bigint not null default 0,
        builtin_template_uses bigint not null default 0,
        builtin_template_keys text[] not null default '{}',
        source_template_posts bigint not null default 0,
        value_score numeric(20, 2) not null default 0,
        updated_at timestamptz not null default now(),
        primary key (period_days, scope_key, prompt_hash)
    )
    """,
    "create index if not exists ix_prompt_occurrence_prompt_hash on analytics_prompt_occurrence(prompt_hash)",
    "create index if not exists ix_prompt_occurrence_created_at on analytics_prompt_occurrence(created_at desc)",
    "create index if not exists ix_prompt_occurrence_task_type on analytics_prompt_occurrence(task_type)",
    "create index if not exists ix_prompt_group_scope_value on analytics_prompt_group_stats(scope_key, value_score desc)",
    "create index if not exists ix_prompt_group_scope_uses on analytics_prompt_group_stats(scope_key, uses desc)",
    "create index if not exists ix_prompt_group_scope_users on analytics_prompt_group_stats(scope_key, users desc)",
    "create index if not exists ix_prompt_group_scope_last_seen on analytics_prompt_group_stats(scope_key, last_seen desc)",
    "create index if not exists ix_prompt_group_scope_char_count on analytics_prompt_group_stats(scope_key, char_count desc)",
    "create index if not exists ix_prompt_group_task_types on analytics_prompt_group_stats using gin(task_types)",
    "create index if not exists ix_prompt_rollup_scope_value on analytics_prompt_rollup_stats(period_days, scope_key, value_score desc)",
    "create index if not exists ix_prompt_rollup_scope_uses on analytics_prompt_rollup_stats(period_days, scope_key, uses desc)",
    "create index if not exists ix_prompt_rollup_scope_users on analytics_prompt_rollup_stats(period_days, scope_key, users desc)",
    "create index if not exists ix_prompt_rollup_scope_last_seen on analytics_prompt_rollup_stats(period_days, scope_key, last_seen desc)",
    "create index if not exists ix_prompt_rollup_scope_char_count on analytics_prompt_rollup_stats(period_days, scope_key, char_count desc)",
    "create index if not exists ix_prompt_rollup_task_types on analytics_prompt_rollup_stats using gin(task_types)",
    "alter table analytics_prompt_occurrence add column if not exists raw_prompt text",
    "alter table analytics_prompt_occurrence add column if not exists result_rating integer not null default 0",
    "alter table analytics_prompt_group_stats add column if not exists variant_count bigint not null default 1",
    "alter table analytics_prompt_rollup_stats add column if not exists variant_count bigint not null default 1",
]


UPSERT_PROMPT_OCCURRENCES_SQL = f"""
with cursor_state as (
    select coalesce(
        (select value::bigint from analytics_prompt_mart_state where key = 'last_history_id'),
        0
    ) as last_history_id
),
builtin_prompts as (
    select builtin.key, builtin.prompt
    from unnest($1::text[], $2::text[]) as builtin(key, prompt)
),
normalized_history as (
    select
        h.id::bigint as history_id,
        h.prompt::text as raw_prompt,
        {prompt_normalize_sql("h.prompt")} as prompt,
        h.task_id::text,
        h.user_id::bigint,
        coalesce(h.type, 'unknown')::text as task_type,
        h.created_at,
        h.is_favorited,
        h.is_public,
        h.allow_contribute,
        h.source::text,
        h.input_file,
        h.output_file,
        h.extra_outputs::jsonb as extra_outputs,
        h.width,
        h.height,
        h.duration,
        coalesce(h.rating, 0)::int as result_rating
    from history h
    cross join cursor_state
    where h.prompt is not null
      and (
          $3::boolean
          or h.id > cursor_state.last_history_id
          or h.created_at >= now() - ($4::int * interval '1 day')
      )
),
source_history as (
    select
        nh.*,
        md5(nh.task_type || chr(31) || nh.prompt) as prompt_hash,
        length(nh.prompt)::int as char_count,
        bp.key as builtin_template_key
    from normalized_history nh
    left join builtin_prompts bp on bp.prompt = nh.prompt
    where length(nh.prompt) > 0
)
insert into analytics_prompt_occurrence (
    history_id,
    prompt_hash,
    raw_prompt,
    prompt,
    char_count,
    task_id,
    user_id,
    task_type,
    created_at,
    is_favorited,
    is_public,
    allow_contribute,
    source,
    builtin_template_key,
    input_file,
    output_file,
    extra_outputs,
    width,
    height,
    duration,
    result_rating,
    updated_at
)
select
    history_id,
    prompt_hash,
    raw_prompt,
    prompt,
    char_count,
    task_id,
    user_id,
    task_type,
    created_at,
    is_favorited,
    is_public,
    allow_contribute,
    source,
    builtin_template_key,
    input_file,
    output_file,
    extra_outputs,
    width,
    height,
    duration,
    result_rating,
    now()
from source_history
on conflict (history_id) do update set
    prompt_hash = excluded.prompt_hash,
    raw_prompt = excluded.raw_prompt,
    prompt = excluded.prompt,
    char_count = excluded.char_count,
    task_id = excluded.task_id,
    user_id = excluded.user_id,
    task_type = excluded.task_type,
    created_at = excluded.created_at,
    is_favorited = excluded.is_favorited,
    is_public = excluded.is_public,
    allow_contribute = excluded.allow_contribute,
    source = excluded.source,
    builtin_template_key = excluded.builtin_template_key,
    input_file = excluded.input_file,
    output_file = excluded.output_file,
    extra_outputs = excluded.extra_outputs,
    width = excluded.width,
    height = excluded.height,
    duration = excluded.duration,
    result_rating = excluded.result_rating,
    updated_at = now()
"""


REFRESH_PROMPT_DIM_SQL = """
insert into analytics_prompt_dim (
    prompt_hash,
    prompt,
    char_count,
    builtin_template_key,
    first_seen,
    last_seen,
    occurrence_count,
    updated_at
)
select
    prompt_hash,
    min(prompt) as prompt,
    max(char_count)::int as char_count,
    min(builtin_template_key) filter (where builtin_template_key is not null) as builtin_template_key,
    min(created_at) as first_seen,
    max(created_at) as last_seen,
    count(*)::bigint as occurrence_count,
    now() as updated_at
from analytics_prompt_occurrence
group by prompt_hash
on conflict (prompt_hash) do update set
    prompt = excluded.prompt,
    char_count = excluded.char_count,
    builtin_template_key = excluded.builtin_template_key,
    first_seen = excluded.first_seen,
    last_seen = excluded.last_seen,
    occurrence_count = excluded.occurrence_count,
    updated_at = now()
"""


REBUILD_PROMPT_GROUP_STATS_SQL = """
truncate table analytics_prompt_group_stats;

insert into analytics_prompt_group_stats (
    scope_key,
    prompt_hash,
    prompt,
    char_count,
    uses,
    users,
    variant_count,
    task_types,
    first_seen,
    last_seen,
    favorite_records,
    public_records,
    gallery_posts,
    likes,
    dislikes,
    comments,
    applies,
    prompt_unlocks,
    derived_uses,
    builtin_template_uses,
    builtin_template_keys,
    source_template_posts,
    value_score,
    updated_at
)
with unlock_counts as (
    select post_id, count(*)::bigint as unlocks
    from gallery_prompt_unlocks
    group by post_id
),
gallery_by_task as (
    select
        gp.task_id,
        min(gp.id) as post_id,
        count(*)::bigint as post_count,
        coalesce(sum(gp.likes_count), 0)::bigint as likes,
        coalesce(sum(gp.dislikes_count), 0)::bigint as dislikes,
        coalesce(sum(gp.comments_count), 0)::bigint as comments,
        coalesce(sum(gp.applied_count), 0)::bigint as applies,
        coalesce(sum(coalesce(uc.unlocks, 0)), 0)::bigint as prompt_unlocks
    from gallery_posts gp
    left join unlock_counts uc on uc.post_id = gp.id
    where gp.is_active is true
      and gp.task_id is not null
    group by gp.task_id
),
base as (
    select
        o.*,
        gp.post_id,
        coalesce(gp.post_count, 0)::bigint as post_count,
        coalesce(gp.likes, 0)::bigint as likes,
        coalesce(gp.dislikes, 0)::bigint as dislikes,
        coalesce(gp.comments, 0)::bigint as comments,
        coalesce(gp.applies, 0)::bigint as applies,
        coalesce(gp.prompt_unlocks, 0)::bigint as prompt_unlocks
    from analytics_prompt_occurrence o
    left join gallery_by_task gp on gp.task_id = o.task_id
),
scoped as (
    select 'all'::text as scope_key, *
    from base
    union all
    select 'natural'::text as scope_key, *
    from base
    where allow_contribute is distinct from false
      and builtin_template_key is null
    union all
    select 'source_template'::text as scope_key, *
    from base
    where allow_contribute is distinct from false
      and builtin_template_key is null
      and post_id is not null
    union all
    select 'builtin_template'::text as scope_key, *
    from base
    where allow_contribute is distinct from false
      and builtin_template_key is not null
    union all
    select 'derived'::text as scope_key, *
    from base
    where allow_contribute is false
),
grouped as (
    select
        scope_key,
        prompt_hash,
        min(prompt) as prompt,
        max(char_count)::int as char_count,
        count(*)::bigint as uses,
        count(distinct user_id)::bigint as users,
        count(distinct coalesce(raw_prompt, prompt))::bigint as variant_count,
        array_remove(array_agg(distinct task_type order by task_type), null) as task_types,
        min(created_at) as first_seen,
        max(created_at) as last_seen,
        count(*) filter (where is_favorited is true)::bigint as favorite_records,
        count(*) filter (where is_public is true)::bigint as public_records,
        coalesce(sum(post_count), 0)::bigint as gallery_posts,
        coalesce(sum(likes), 0)::bigint as likes,
        coalesce(sum(dislikes), 0)::bigint as dislikes,
        coalesce(sum(comments), 0)::bigint as comments,
        coalesce(sum(applies), 0)::bigint as applies,
        coalesce(sum(prompt_unlocks), 0)::bigint as prompt_unlocks,
        count(*) filter (where allow_contribute is false)::bigint as derived_uses,
        count(*) filter (
            where builtin_template_key is not null
              and allow_contribute is distinct from false
        )::bigint as builtin_template_uses,
        array_remove(array_agg(distinct builtin_template_key order by builtin_template_key), null) as builtin_template_keys,
        coalesce(sum(post_count) filter (
            where post_id is not null
              and allow_contribute is distinct from false
              and builtin_template_key is null
        ), 0)::bigint as source_template_posts
    from scoped
    group by scope_key, prompt_hash
)
select
    scope_key,
    prompt_hash,
    prompt,
    char_count,
    uses,
    users,
    variant_count,
    task_types,
    first_seen,
    last_seen,
    favorite_records,
    public_records,
    gallery_posts,
    likes,
    dislikes,
    comments,
    applies,
    prompt_unlocks,
    derived_uses,
    builtin_template_uses,
    builtin_template_keys,
    source_template_posts,
    round(
        (
            ln(uses + 1) * 8
            + ln(users + 1) * 14
            + favorite_records * 8
            + gallery_posts * 10
            + likes * 2
            - dislikes
            + comments * 2
            + applies * 5
            + prompt_unlocks * 8
        )::numeric,
        2
    ) as value_score,
    now() as updated_at
from grouped
"""


REBUILD_PROMPT_ROLLUP_STATS_SQL = """
truncate table analytics_prompt_rollup_stats;

insert into analytics_prompt_rollup_stats (
    period_days,
    scope_key,
    prompt_hash,
    prompt,
    char_count,
    uses,
    users,
    variant_count,
    task_types,
    first_seen,
    last_seen,
    favorite_records,
    public_records,
    gallery_posts,
    likes,
    dislikes,
    comments,
    applies,
    prompt_unlocks,
    derived_uses,
    builtin_template_uses,
    builtin_template_keys,
    source_template_posts,
    value_score,
    updated_at
)
with periods(period_days, since) as (
    values
        (7, now() - interval '7 day'),
        (30, now() - interval '30 day'),
        (90, now() - interval '90 day'),
        (180, now() - interval '180 day'),
        (240, now() - interval '240 day'),
        (360, now() - interval '360 day')
),
unlock_counts as (
    select post_id, count(*)::bigint as unlocks
    from gallery_prompt_unlocks
    group by post_id
),
gallery_by_task as (
    select
        gp.task_id,
        min(gp.id) as post_id,
        count(*)::bigint as post_count,
        coalesce(sum(gp.likes_count), 0)::bigint as likes,
        coalesce(sum(gp.dislikes_count), 0)::bigint as dislikes,
        coalesce(sum(gp.comments_count), 0)::bigint as comments,
        coalesce(sum(gp.applied_count), 0)::bigint as applies,
        coalesce(sum(coalesce(uc.unlocks, 0)), 0)::bigint as prompt_unlocks
    from gallery_posts gp
    left join unlock_counts uc on uc.post_id = gp.id
    where gp.is_active is true
      and gp.task_id is not null
    group by gp.task_id
),
base as (
    select
        p.period_days,
        o.*,
        gp.post_id,
        coalesce(gp.post_count, 0)::bigint as post_count,
        coalesce(gp.likes, 0)::bigint as likes,
        coalesce(gp.dislikes, 0)::bigint as dislikes,
        coalesce(gp.comments, 0)::bigint as comments,
        coalesce(gp.applies, 0)::bigint as applies,
        coalesce(gp.prompt_unlocks, 0)::bigint as prompt_unlocks
    from periods p
    join analytics_prompt_occurrence o on o.created_at >= p.since
    left join gallery_by_task gp on gp.task_id = o.task_id
),
scoped as (
    select 'all'::text as scope_key, base.*
    from base
    union all
    select 'natural'::text as scope_key, base.*
    from base
    where allow_contribute is distinct from false
      and builtin_template_key is null
    union all
    select 'source_template'::text as scope_key, base.*
    from base
    where allow_contribute is distinct from false
      and builtin_template_key is null
      and post_id is not null
    union all
    select 'builtin_template'::text as scope_key, base.*
    from base
    where allow_contribute is distinct from false
      and builtin_template_key is not null
    union all
    select 'derived'::text as scope_key, base.*
    from base
    where allow_contribute is false
),
grouped as (
    select
        period_days,
        scope_key,
        prompt_hash,
        min(prompt) as prompt,
        max(char_count)::int as char_count,
        count(*)::bigint as uses,
        count(distinct user_id)::bigint as users,
        count(distinct coalesce(raw_prompt, prompt))::bigint as variant_count,
        array_remove(array_agg(distinct task_type order by task_type), null) as task_types,
        min(created_at) as first_seen,
        max(created_at) as last_seen,
        count(*) filter (where is_favorited is true)::bigint as favorite_records,
        count(*) filter (where is_public is true)::bigint as public_records,
        coalesce(sum(post_count), 0)::bigint as gallery_posts,
        coalesce(sum(likes), 0)::bigint as likes,
        coalesce(sum(dislikes), 0)::bigint as dislikes,
        coalesce(sum(comments), 0)::bigint as comments,
        coalesce(sum(applies), 0)::bigint as applies,
        coalesce(sum(prompt_unlocks), 0)::bigint as prompt_unlocks,
        count(*) filter (where allow_contribute is false)::bigint as derived_uses,
        count(*) filter (
            where builtin_template_key is not null
              and allow_contribute is distinct from false
        )::bigint as builtin_template_uses,
        array_remove(array_agg(distinct builtin_template_key order by builtin_template_key), null) as builtin_template_keys,
        coalesce(sum(post_count) filter (
            where post_id is not null
              and allow_contribute is distinct from false
              and builtin_template_key is null
        ), 0)::bigint as source_template_posts
    from scoped
    group by period_days, scope_key, prompt_hash
)
select
    period_days,
    scope_key,
    prompt_hash,
    prompt,
    char_count,
    uses,
    users,
    variant_count,
    task_types,
    first_seen,
    last_seen,
    favorite_records,
    public_records,
    gallery_posts,
    likes,
    dislikes,
    comments,
    applies,
    prompt_unlocks,
    derived_uses,
    builtin_template_uses,
    builtin_template_keys,
    source_template_posts,
    round(
        (
            ln(uses + 1) * 8
            + ln(users + 1) * 14
            + favorite_records * 8
            + gallery_posts * 10
            + likes * 2
            - dislikes
            + comments * 2
            + applies * 5
            + prompt_unlocks * 8
        )::numeric,
        2
    ) as value_score,
    now() as updated_at
from grouped
"""


UPDATE_PROMPT_MART_STATE_SQL = """
insert into analytics_prompt_mart_state (key, value, updated_at)
values
    ('last_history_id', coalesce((select max(history_id)::text from analytics_prompt_occurrence), '0'), now()),
    ('last_refresh_mode', case when $1::boolean then 'full' else 'incremental' end, now()),
    ('last_refreshed_at', now()::text, now()),
    ('normalization_version', $2::text, now())
on conflict (key) do update set
    value = excluded.value,
    updated_at = now()
"""


async def ensure_prompt_mart_schema(conn: Any) -> None:
    for statement in CREATE_PROMPT_MART_SCHEMA_SQL:
        await conn.execute(statement)


async def refresh_prompt_mart(
    conn: Any,
    *,
    builtin_template_keys: list[str],
    builtin_template_prompts: list[str],
    full: bool = False,
    recent_days: int = 7,
) -> dict[str, Any]:
    await ensure_prompt_mart_schema(conn)
    if not full:
        current_version = await conn.fetchval(
            "select value from analytics_prompt_mart_state where key = 'normalization_version'"
        )
        if current_version != PROMPT_NORMALIZATION_VERSION:
            raise RuntimeError(
                "prompt mart normalization version mismatch; rerun refresh_prompt_mart with --full"
            )
    if full:
        await conn.execute(
            """
            truncate table
                analytics_prompt_rollup_stats,
                analytics_prompt_group_stats,
                analytics_prompt_dim,
                analytics_prompt_occurrence,
                analytics_prompt_mart_state
            """
        )

    occurrence_result = await conn.execute(
        UPSERT_PROMPT_OCCURRENCES_SQL,
        builtin_template_keys,
        builtin_template_prompts,
        full,
        recent_days,
    )
    await conn.execute(REFRESH_PROMPT_DIM_SQL)
    await conn.execute(REBUILD_PROMPT_GROUP_STATS_SQL)
    await conn.execute(REBUILD_PROMPT_ROLLUP_STATS_SQL)
    await conn.execute(UPDATE_PROMPT_MART_STATE_SQL, full, PROMPT_NORMALIZATION_VERSION)
    for table in (
        "analytics_prompt_occurrence",
        "analytics_prompt_dim",
        "analytics_prompt_group_stats",
        "analytics_prompt_rollup_stats",
    ):
        await conn.execute(f"analyze {table}")

    status = await conn.fetchrow(PROMPT_MART_STATUS_SQL)
    return {
        **dict(status or {}),
        "occurrence_upsert_result": occurrence_result,
        "full": full,
        "recent_days": recent_days,
    }
