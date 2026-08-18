#!/usr/bin/env python3
"""Audit Gallery relational invariants and optionally apply deterministic repair."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


AUDIT_SQL = {
    "duplicate_post_groups": """
        SELECT count(*) FROM (
            SELECT task_id, user_id FROM gallery_posts
            GROUP BY task_id, user_id HAVING count(*) > 1
        ) AS conflicts
    """,
    "duplicate_posts_extra": """
        SELECT COALESCE(sum(item_count - 1), 0) FROM (
            SELECT count(*) AS item_count FROM gallery_posts
            GROUP BY task_id, user_id HAVING count(*) > 1
        ) AS conflicts
    """,
    "duplicate_apply_groups": """
        SELECT count(*) FROM (
            SELECT user_id, post_id FROM user_interactions
            WHERE action_type = 'apply'
            GROUP BY user_id, post_id HAVING count(*) > 1
        ) AS conflicts
    """,
    "duplicate_reaction_groups": """
        SELECT count(*) FROM (
            SELECT user_id, post_id FROM user_interactions
            WHERE action_type IN ('like', 'dislike')
            GROUP BY user_id, post_id HAVING count(*) > 1
        ) AS conflicts
    """,
    "dual_reaction_groups": """
        SELECT count(*) FROM (
            SELECT user_id, post_id FROM user_interactions
            WHERE action_type IN ('like', 'dislike')
            GROUP BY user_id, post_id
            HAVING count(DISTINCT action_type) > 1
        ) AS conflicts
    """,
    "invalid_interactions": """
        SELECT count(*) FROM user_interactions
        WHERE user_id IS NULL OR post_id IS NULL
           OR action_type IS NULL
           OR action_type NOT IN ('like', 'dislike', 'apply')
    """,
    "post_counter_drift": """
        SELECT count(*) FROM gallery_posts AS gp
        WHERE gp.likes_count IS DISTINCT FROM (
                SELECT count(*) FROM user_interactions ui
                WHERE ui.post_id = gp.id AND ui.action_type = 'like'
              )
           OR gp.dislikes_count IS DISTINCT FROM (
                SELECT count(*) FROM user_interactions ui
                WHERE ui.post_id = gp.id AND ui.action_type = 'dislike'
              )
           OR gp.applied_count IS DISTINCT FROM (
                SELECT count(*) FROM user_interactions ui
                WHERE ui.post_id = gp.id AND ui.action_type = 'apply'
              )
    """,
    "contribution_counter_drift": """
        SELECT count(*) FROM users AS u
        WHERE COALESCE(u.total_contributions, 0) <> (
            SELECT count(*) FROM gallery_posts gp
            WHERE gp.user_id = u.id AND gp.is_active IS TRUE
        )
    """,
}


REPAIR_SQL = """
CREATE TEMP TABLE gallery_post_merge_map ON COMMIT DROP AS
WITH ranked AS (
    SELECT
        id,
        first_value(id) OVER (
            PARTITION BY task_id, user_id
            ORDER BY is_active DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        ) AS master_id,
        row_number() OVER (
            PARTITION BY task_id, user_id
            ORDER BY is_active DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        ) AS rank_number
    FROM gallery_posts
)
SELECT id AS loser_id, master_id FROM ranked WHERE rank_number > 1;

DELETE FROM user_interactions
WHERE user_id IS NULL OR post_id IS NULL OR action_type IS NULL
   OR action_type NOT IN ('like', 'dislike', 'apply');

CREATE TEMP TABLE gallery_interaction_repair ON COMMIT DROP AS
SELECT
    ui.id,
    COALESCE(mapping.master_id, ui.post_id) AS canonical_post_id,
    row_number() OVER (
        PARTITION BY
            ui.user_id,
            COALESCE(mapping.master_id, ui.post_id),
            CASE WHEN ui.action_type = 'apply' THEN 'apply' ELSE 'reaction' END
        ORDER BY
            CASE WHEN ui.action_type = 'apply' THEN ui.created_at END ASC NULLS LAST,
            CASE WHEN ui.action_type IN ('like', 'dislike') THEN ui.created_at END DESC NULLS LAST,
            CASE WHEN ui.action_type = 'apply' THEN ui.id END ASC,
            CASE WHEN ui.action_type IN ('like', 'dislike') THEN ui.id END DESC
    ) AS rank_number
FROM user_interactions ui
LEFT JOIN gallery_post_merge_map mapping ON mapping.loser_id = ui.post_id;

DELETE FROM user_interactions ui
USING gallery_interaction_repair repair
WHERE ui.id = repair.id AND repair.rank_number > 1;

UPDATE user_interactions ui
SET post_id = repair.canonical_post_id
FROM gallery_interaction_repair repair
WHERE ui.id = repair.id AND repair.rank_number = 1
  AND ui.post_id <> repair.canonical_post_id;

UPDATE gallery_comments comments
SET post_id = mapping.master_id
FROM gallery_post_merge_map mapping
WHERE comments.post_id = mapping.loser_id;

CREATE TEMP TABLE gallery_report_repair ON COMMIT DROP AS
SELECT
    reports.id,
    COALESCE(mapping.master_id, reports.post_id) AS canonical_post_id,
    row_number() OVER (
        PARTITION BY reports.reporter_user_id,
            COALESCE(mapping.master_id, reports.post_id)
        ORDER BY reports.created_at DESC NULLS LAST, reports.id DESC
    ) AS rank_number
FROM gallery_reports reports
LEFT JOIN gallery_post_merge_map mapping ON mapping.loser_id = reports.post_id
WHERE reports.post_id IS NOT NULL;

UPDATE gallery_reports reports
SET post_id = NULL,
    status = 'resolved',
    resolved_at = COALESCE(reports.resolved_at, CURRENT_TIMESTAMP),
    resolution_action = COALESCE(reports.resolution_action, 'duplicate_post_merged')
FROM gallery_report_repair repair
WHERE reports.id = repair.id AND repair.rank_number > 1;

UPDATE gallery_reports reports
SET post_id = repair.canonical_post_id
FROM gallery_report_repair repair
WHERE reports.id = repair.id AND repair.rank_number = 1
  AND reports.post_id <> repair.canonical_post_id;

CREATE TEMP TABLE gallery_unlock_repair ON COMMIT DROP AS
SELECT
    unlocks.id,
    COALESCE(mapping.master_id, unlocks.post_id) AS canonical_post_id,
    row_number() OVER (
        PARTITION BY unlocks.user_id, COALESCE(mapping.master_id, unlocks.post_id)
        ORDER BY unlocks.created_at ASC NULLS LAST, unlocks.id ASC
    ) AS rank_number
FROM gallery_prompt_unlocks unlocks
LEFT JOIN gallery_post_merge_map mapping ON mapping.loser_id = unlocks.post_id;

DELETE FROM gallery_prompt_unlocks unlocks
USING gallery_unlock_repair repair
WHERE unlocks.id = repair.id AND repair.rank_number > 1;

UPDATE gallery_prompt_unlocks unlocks
SET post_id = repair.canonical_post_id
FROM gallery_unlock_repair repair
WHERE unlocks.id = repair.id AND repair.rank_number = 1
  AND unlocks.post_id <> repair.canonical_post_id;

DELETE FROM gallery_posts posts
USING gallery_post_merge_map mapping
WHERE posts.id = mapping.loser_id;

UPDATE gallery_posts posts
SET likes_count = counts.likes_count,
    dislikes_count = counts.dislikes_count,
    applied_count = counts.applied_count,
    comments_count = counts.comments_count
FROM (
    SELECT
        gp.id,
        count(ui.id) FILTER (WHERE ui.action_type = 'like') AS likes_count,
        count(ui.id) FILTER (WHERE ui.action_type = 'dislike') AS dislikes_count,
        count(ui.id) FILTER (WHERE ui.action_type = 'apply') AS applied_count,
        (SELECT count(*) FROM gallery_comments comments
         WHERE comments.post_id = gp.id AND comments.is_active IS TRUE) AS comments_count
    FROM gallery_posts gp
    LEFT JOIN user_interactions ui ON ui.post_id = gp.id
    GROUP BY gp.id
) counts
WHERE posts.id = counts.id;

UPDATE users users
SET total_contributions = counts.active_posts
FROM (
    SELECT users_inner.id,
           count(posts.id) FILTER (WHERE posts.is_active IS TRUE) AS active_posts
    FROM users users_inner
    LEFT JOIN gallery_posts posts ON posts.user_id = users_inner.id
    GROUP BY users_inner.id
) counts
WHERE users.id = counts.id;

UPDATE history histories
SET is_public = EXISTS (
    SELECT 1 FROM gallery_posts posts
    WHERE posts.task_id = histories.task_id
      AND posts.user_id = histories.user_id
      AND posts.is_active IS TRUE
)
WHERE EXISTS (
    SELECT 1 FROM gallery_post_merge_map mapping
    JOIN gallery_posts master ON master.id = mapping.master_id
    WHERE master.task_id = histories.task_id AND master.user_id = histories.user_id
);
"""


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip("'\"")


def _normalize_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


async def _scalar(connection, sql: str) -> int:
    return int((await connection.execute(text(sql))).scalar_one() or 0)


async def _audit(connection) -> dict:
    revision = (
        await connection.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar_one_or_none()
    index_rows = (
        await connection.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename IN ('gallery_posts', 'user_interactions') "
                "ORDER BY indexname"
            )
        )
    ).scalars().all()
    constraint_rows = (
        await connection.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid IN ('gallery_posts'::regclass, "
                "'user_interactions'::regclass) ORDER BY conname"
            )
        )
    ).scalars().all()
    counts = {name: await _scalar(connection, sql) for name, sql in AUDIT_SQL.items()}
    return {
        "alembic_revision": revision,
        "gallery_indexes": list(index_rows),
        "gallery_constraints": list(constraint_rows),
        "counts": counts,
        "consistent": all(value == 0 for value in counts.values()),
    }


async def _repair(connection) -> None:
    for statement in REPAIR_SQL.split(";\n\n"):
        sql = statement.strip().rstrip(";")
        if sql:
            await connection.execute(text(sql))


async def _read_only_audit(engine, *, statement_timeout_seconds: int) -> dict:
    async with engine.connect() as connection:
        async with connection.begin():
            if connection.dialect.name == "postgresql":
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                await connection.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": f"{max(1, statement_timeout_seconds)}s"},
                )
            return await _audit(connection)


def _validate_apply_args(args) -> None:
    if not args.apply:
        return
    if not args.backup_confirmed:
        raise SystemExit("--apply requires --backup-confirmed")
    if args.confirm_env != args.environment:
        raise SystemExit("--apply requires --confirm-env matching --environment")
    if args.environment == "prod" and args.confirm_production != "APPLY_GALLERY_PROD_REPAIR":
        raise SystemExit(
            "production repair requires --confirm-production APPLY_GALLERY_PROD_REPAIR"
        )


def _write_reports(report_dir: Path, payload: dict) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"gallery_consistency_audit_{stamp}.json"
    md_path = report_dir / f"gallery_consistency_audit_{stamp}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    before = payload["before"]["counts"]
    after = payload.get("after", payload["before"])["counts"]
    rows = [
        "# Gallery consistency audit",
        "",
        f"- Environment: `{payload['environment']}`",
        f"- Mode: `{'apply' if payload['applied'] else 'dry-run'}`",
        f"- Alembic revision: `{payload['before']['alembic_revision']}`",
        "",
        "| Check | Before | After |",
        "| --- | ---: | ---: |",
    ]
    rows.extend(f"| `{name}` | {before[name]} | {after[name]} |" for name in before)
    rows.extend(
        [
            "",
            "Reports contain aggregate counts and schema names only; "
            "no connection strings or user content.",
            "",
        ]
    )
    md_path.write_text("\n".join(rows), encoding="utf-8")
    return json_path, md_path


async def _run(args) -> dict:
    engine = create_async_engine(
        _normalize_async_url(os.environ["DATABASE_URL"]),
        connect_args={"timeout": 10},
        pool_pre_ping=True,
    )
    try:
        before = await _read_only_audit(
            engine,
            statement_timeout_seconds=args.statement_timeout_seconds,
        )
        after = None
        if args.apply:
            async with engine.begin() as connection:
                if connection.dialect.name != "postgresql":
                    raise RuntimeError("Gallery repair only supports PostgreSQL")
                await _repair(connection)
            after = await _read_only_audit(
                engine,
                statement_timeout_seconds=args.statement_timeout_seconds,
            )
        return {
            "schema_version": 1,
            "environment": args.environment,
            "applied": bool(args.apply),
            "before": before,
            **({"after": after} if after is not None else {}),
        }
    finally:
        await engine.dispose()


def _parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--environment", choices=("local", "test", "prod"), required=True)
    parser.add_argument("--report-dir", type=Path, default=Path("logs"))
    parser.add_argument("--statement-timeout-seconds", type=int, default=60)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-confirmed", action="store_true")
    parser.add_argument("--confirm-env")
    parser.add_argument("--confirm-production")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.env_file:
        _load_env_file(args.env_file)
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")
    _validate_apply_args(args)
    try:
        payload = asyncio.run(_run(args))
    except Exception as exc:
        raise SystemExit(f"Gallery audit failed: {type(exc).__name__}") from None
    json_path, md_path = _write_reports(args.report_dir, payload)
    print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path)}))


if __name__ == "__main__":
    main()
