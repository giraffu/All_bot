#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

import asyncpg


DERIVED_PROMPT_TABLES = (
    "analytics_prompt_graph_layout",
    "analytics_prompt_graph_community_edges",
    "analytics_prompt_graph_memberships",
    "analytics_prompt_graph_communities",
    "analytics_prompt_graph_nodes",
    "analytics_prompt_graph_state",
    "analytics_prompt_semantic_scene_members",
    "analytics_prompt_semantic_scenes",
    "analytics_prompt_semantic_scene_state",
    "analytics_prompt_near_graph_edges",
    "analytics_prompt_near_graph_state",
    "analytics_prompt_similarity_members",
    "analytics_prompt_similarity_clusters",
    "analytics_prompt_similarity_edges",
)

PRESERVED_LOCAL_ANALYTICS_TABLES = (
    "analytics_prompt_mart_state",
    "analytics_prompt_dim",
    "analytics_prompt_occurrence",
    "analytics_prompt_group_stats",
    "analytics_prompt_rollup_stats",
    "analytics_prompt_slim_candidates",
    "analytics_prompt_vector_state",
    "analytics_prompt_embeddings",
    "analytics_user_profile_daily_snapshots",
)


@dataclass(frozen=True)
class CleanupConfig:
    database_url: str
    execute: bool = False


def normalize_database_url(dsn: str) -> str:
    value = dsn.strip()
    if value.startswith("postgresql+asyncpg://"):
        return "postgresql://" + value.removeprefix("postgresql+asyncpg://")
    if value.startswith("postgres://"):
        return "postgresql://" + value.removeprefix("postgres://")
    return value


def build_drop_sql() -> str:
    table_list = ",\n    ".join(DERIVED_PROMPT_TABLES)
    return f"drop table if exists\n    {table_list}\ncascade"


async def run_cleanup(
    config: CleanupConfig,
    *,
    connect: Callable[..., Awaitable[asyncpg.Connection]] = asyncpg.connect,
) -> dict[str, object]:
    sql = build_drop_sql()
    if not config.execute:
        print("[dry-run] would drop local prompt derivative tables:")
        for table_name in DERIVED_PROMPT_TABLES:
            print(f"  - {table_name}")
        return {"status": "dry_run", "tables": list(DERIVED_PROMPT_TABLES)}

    conn = await connect(dsn=normalize_database_url(config.database_url))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()
    return {"status": "dropped", "tables": list(DERIVED_PROMPT_TABLES)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drop deprecated local analytics prompt derivative tables.")
    parser.add_argument("--execute", action="store_true", help="actually drop tables; default is dry-run")
    parser.add_argument(
        "--database-url",
        default=os.getenv("LOCAL_ANALYTICS_DATABASE_URL", ""),
        help="PostgreSQL DSN; defaults to LOCAL_ANALYTICS_DATABASE_URL",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database_url = normalize_database_url(args.database_url)
    if args.execute and not database_url:
        raise SystemExit("--database-url or LOCAL_ANALYTICS_DATABASE_URL is required with --execute")
    result = asyncio.run(run_cleanup(CleanupConfig(database_url=database_url, execute=bool(args.execute))))
    print(result)


if __name__ == "__main__":
    main()
