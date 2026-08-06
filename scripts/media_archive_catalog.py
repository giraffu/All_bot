#!/usr/bin/env python3
"""Initialize and seed the resumable archive catalog in the local shadow DB."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import uuid

import asyncpg


CATALOG_DDL = """
create table if not exists analytics_media_runs (
    id uuid primary key,
    run_type text not null,
    status text not null check (status in ('running','completed','failed','paused')),
    cursor jsonb not null default '{}'::jsonb,
    stats jsonb not null default '{}'::jsonb,
    error text,
    started_at timestamptz not null default now(),
    completed_at timestamptz
);
create table if not exists analytics_media_blobs (
    sha256 char(64) primary key,
    byte_size bigint not null check (byte_size >= 0),
    mime_type text,
    nas_bucket text not null,
    nas_key text not null,
    verified_at timestamptz not null,
    unique (nas_bucket, nas_key)
);
create table if not exists analytics_media_sources (
    source text primary key,
    priority integer not null,
    enabled boolean not null default true,
    retired_at timestamptz,
    retirement_evidence text,
    check (retired_at is null or nullif(btrim(retirement_evidence), '') is not null)
);
insert into analytics_media_sources(source, priority) values
  ('r2-user-data-prod', 10), ('minio-bot-data', 30),
  ('minio-comfyui-temp', 40), ('cold-minio-192.168.1.88-9001', 50),
  ('cold-minio-192.168.1.88-9002', 60), ('known-backups-and-filesystems', 70)
on conflict (source) do nothing;
create table if not exists analytics_media_asset_catalog (
    id bigserial primary key,
    history_id integer not null,
    task_id text,
    user_id bigint,
    history_created_at timestamptz,
    role text not null,
    ordinal integer not null,
    original_ref text not null,
    temperature text not null default 'unknown' check (temperature in ('hot','cold','unknown')),
    status text not null default 'pending_probe' check (status in (
      'pending_probe','source_offline','found','archived_verified','provisional_missing',
      'confirmed_lost','checksum_error','external_unmanaged')),
    found_source text,
    source_key text,
    sha256 char(64) references analytics_media_blobs(sha256),
    last_checked_at timestamptz,
    missing_rounds integer not null default 0,
    first_missing_at timestamptz,
    last_error text,
    unique (history_id, role, ordinal)
);
create index if not exists ix_analytics_media_catalog_status on analytics_media_asset_catalog(status, history_id);
create index if not exists ix_analytics_media_catalog_ref on analytics_media_asset_catalog(original_ref);
create table if not exists analytics_media_source_attempts (
    id bigserial primary key,
    run_id uuid not null references analytics_media_runs(id),
    asset_id bigint not null references analytics_media_asset_catalog(id) on delete cascade,
    source text not null,
    candidate_key text not null,
    status text not null check (status in ('found','not_found','source_offline','error','checksum_error')),
    error_code text,
    detail text,
    checked_at timestamptz not null default now()
);
create index if not exists ix_analytics_media_attempt_asset on analytics_media_source_attempts(asset_id, checked_at desc);
"""


SEED_SQL = """
with selected as (
  select id, task_id, user_id, created_at, input_file, output_file, extra_outputs
  from history where id between $1 and $2
), selected_users as (
  select distinct user_id from selected
), ranked as (
  select h.id, row_number() over(partition by h.user_id order by h.id desc) rn
  from history h join selected_users u on u.user_id=h.user_id
), hot as (
  select h.id from history h left join ranked r on r.id=h.id
  where h.id between $1 and $2 and (
    (r.rn <= 8 and h.is_visible is true) or h.is_favorited is true or h.is_public is true
    or exists(select 1 from gallery_posts gp where gp.task_id=h.task_id and gp.is_active is true)
  )
), assets as (
  select id history_id, task_id, user_id, created_at, 'input' role,
         ordinality::integer - 1 ordinal, btrim(ref) original_ref
  from selected cross join lateral unnest(string_to_array(coalesce(input_file,''), '|')) with ordinality as p(ref, ordinality)
  where btrim(ref) <> ''
  union all
  select id, task_id, user_id, created_at, 'output', 0, btrim(output_file)
  from selected where btrim(coalesce(output_file,'')) <> ''
  union all
  select s.id, s.task_id, s.user_id, s.created_at, 'extra:' || extras.key,
         row_number() over (partition by s.id, extras.key order by paths.path::text)::integer - 1,
         trim(both '"' from paths.path::text)
  from selected s
  cross join lateral jsonb_each(
    case
      when jsonb_typeof(coalesce(s.extra_outputs::jsonb, '{}'::jsonb)) = 'object'
        then coalesce(s.extra_outputs::jsonb, '{}'::jsonb)
      else '{}'::jsonb
    end
  ) extras
  cross join lateral jsonb_path_query(extras.value, 'strict $.**.path') paths(path)
)
insert into analytics_media_asset_catalog
  (history_id, task_id, user_id, history_created_at, role, ordinal, original_ref, temperature)
select history_id, task_id, user_id, created_at, role, ordinal, original_ref,
  case when exists(select 1 from hot where hot.id=assets.history_id) then 'hot' else 'cold' end
from assets
where original_ref <> ''
on conflict (history_id, role, ordinal) do update set
  task_id=excluded.task_id, user_id=excluded.user_id,
  history_created_at=excluded.history_created_at, original_ref=excluded.original_ref,
  temperature=excluded.temperature
returning id;
"""

SEED_IDS_SQL = SEED_SQL.replace(
    "from history where id between $1 and $2",
    "from history where id = any($3::int[])",
).replace(
    "where h.id between $1 and $2 and (",
    "where h.id = any($3::int[]) and (",
)


def load_history_ids(path: str | None) -> tuple[int, ...]:
    if not path:
        return ()
    values = []
    for line_number, raw in enumerate(Path(path).read_text().splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if not value.isdigit() or int(value) < 1:
            raise ValueError(f"invalid History ID on line {line_number}")
        values.append(int(value))
    result = tuple(sorted(set(values)))
    if not result or len(result) > 10000:
        raise ValueError("History ID file must contain between 1 and 10000 IDs")
    return result


CONFIRM_MISSING_SQL = """
with absent as (
  select x.asset_id
  from analytics_media_source_attempts x
  join analytics_media_sources s on s.source = x.source and s.enabled
  where x.run_id = $1
  group by x.asset_id
  having bool_and(x.status = 'not_found')
     and count(distinct x.source) = (select count(*) from analytics_media_sources where enabled)
)
update analytics_media_asset_catalog a
set status = case
      when a.missing_rounds + 1 >= 2 and a.first_missing_at <= now() - interval '24 hours'
        then 'confirmed_lost' else 'provisional_missing' end,
    missing_rounds = a.missing_rounds + 1,
    first_missing_at = coalesce(a.first_missing_at, now()),
    last_checked_at = now()
from absent where absent.asset_id = a.id;
"""


async def main_async(args) -> None:
    database_url = os.getenv("LOCAL_ANALYTICS_DATABASE_URL") or os.getenv(
        "DATABASE_URL"
    )
    if not database_url:
        raise SystemExit("LOCAL_ANALYTICS_DATABASE_URL is required")
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(CATALOG_DDL)
        if args.command == "init":
            print("archive catalog tables initialized")
        elif args.command == "seed":
            history_ids = load_history_ids(args.history_id_file)
            start_id = history_ids[0] if history_ids else args.start_id
            end_id = history_ids[-1] if history_ids else args.end_id
            run_id = uuid.uuid4()
            await conn.execute(
                "insert into analytics_media_runs(id,run_type,status,cursor) values($1,'seed','running',jsonb_build_object('start',$2::bigint,'end',$3::bigint))",
                run_id,
                start_id,
                end_id,
            )
            rows = await conn.fetch(
                SEED_IDS_SQL if history_ids else SEED_SQL,
                start_id,
                end_id,
                *([list(history_ids)] if history_ids else []),
            )
            await conn.execute(
                "update analytics_media_runs set status='completed',stats=jsonb_build_object('upserted',$2::bigint),completed_at=now() where id=$1",
                run_id,
                len(rows),
            )
            print(f"seeded {len(rows)} logical assets; run={run_id}")
        elif args.command == "finalize-missing":
            await conn.execute(CONFIRM_MISSING_SQL, uuid.UUID(args.run_id))
            print(
                "missing statuses finalized; offline sources were not treated as loss"
            )
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("init")
    seed = subs.add_parser("seed")
    seed.add_argument("--start-id", type=int)
    seed.add_argument("--end-id", type=int)
    seed.add_argument("--history-id-file")
    finalize = subs.add_parser("finalize-missing")
    finalize.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if (
        args.command == "seed"
        and not args.history_id_file
        and (args.start_id is None or args.end_id is None)
    ):
        parser.error("seed requires --start-id/--end-id or --history-id-file")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
