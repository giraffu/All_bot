#!/usr/bin/env python3
"""Materialize the independent R2 History snapshot ledger for local analytics."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

import asyncpg

from scripts.r2_history_snapshot_backup import iter_manifest_objects


SCHEMA_SQL = """
create table if not exists analytics_snapshot_backup_sets(
  snapshot_id text primary key,
  snapshot_label text not null,
  manifest_sha256 char(64) not null,
  ready boolean not null default false,
  object_count bigint not null default 0,
  reference_count bigint not null default 0,
  last_verified_batch integer not null default 0,
  status_counts jsonb not null default '{}'::jsonb,
  refreshed_at timestamptz,
  created_at timestamptz not null default now()
);
create table if not exists analytics_snapshot_backup_objects(
  snapshot_id text not null,
  object_key text not null,
  backup_status text not null check (backup_status in
    ('backed_up','file_missing','not_backed_up','backing_up','backup_failed')),
  batch_number integer,
  byte_size bigint,
  sha256 char(64),
  error_code text,
  updated_at timestamptz not null default now(),
  primary key(snapshot_id,object_key)
);
create table if not exists analytics_snapshot_backup_refs(
  id bigserial primary key,
  snapshot_id text not null,
  history_id bigint not null,
  task_id text,
  role text not null,
  ordinal integer not null,
  original_ref text not null,
  object_key text not null
);
"""


def classify_snapshot_state(
    row: Mapping[str, Any] | None, *, batch_status: str | None
) -> str:
    if row is None:
        return "backing_up" if batch_status in {"copying", "transferring"} else "not_backed_up"
    status = str(row.get("status") or "")
    if status == "completed":
        return "backed_up" if batch_status == "verified" else "backing_up"
    if status == "failed":
        code = str(row.get("error_code") or "").strip().lower()
        http_status = row.get("error_http_status")
        if http_status == 404 or code in {"404", "nosuchkey", "notfound", "nosuchobject"}:
            return "file_missing"
        return "backup_failed"
    return "backing_up" if batch_status in {"copying", "transferring"} else "not_backed_up"


def _open_readonly_sqlite(path: Path, *, immutable: bool = False) -> sqlite3.Connection:
    suffix = "&immutable=1" if immutable else ""
    connection = sqlite3.connect(f"file:{path}?mode=ro{suffix}", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma busy_timeout=5000")
    return connection


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_frozen_inputs(
    *,
    manifest_path: Path,
    manifest_sha256: str,
    manifest_file_sha256: str,
    inventory_path: Path,
    inventory_file_sha256: str,
) -> None:
    if _sha256_file(manifest_path) != manifest_file_sha256:
        raise ValueError("frozen manifest file SHA-256 is invalid")
    if _sha256_file(inventory_path) != inventory_file_sha256:
        raise ValueError("frozen inventory file SHA-256 is invalid")
    with manifest_path.open("rb") as stream:
        prefix = stream.read(1024 * 1024).decode("utf-8")
    marker = f'"manifest_sha256":"{manifest_sha256}"'
    if marker not in prefix.split('"objects":[', 1)[0]:
        raise ValueError("manifest identity does not match the configured snapshot")


async def ensure_schema(connection: asyncpg.Connection) -> None:
    await connection.execute(SCHEMA_SQL)


async def _copy_initial_chunk(
    connection: asyncpg.Connection,
    *,
    object_rows: list[tuple[Any, ...]],
    reference_rows: list[tuple[Any, ...]],
) -> None:
    if object_rows:
        await connection.copy_records_to_table(
            "analytics_snapshot_backup_objects",
            records=object_rows,
            columns=(
                "snapshot_id",
                "object_key",
                "backup_status",
                "batch_number",
                "byte_size",
                "sha256",
                "error_code",
            ),
        )
    if reference_rows:
        await connection.copy_records_to_table(
            "analytics_snapshot_backup_refs",
            records=reference_rows,
            columns=(
                "snapshot_id",
                "history_id",
                "task_id",
                "role",
                "ordinal",
                "original_ref",
                "object_key",
            ),
        )


async def import_manifest(
    connection: asyncpg.Connection,
    *,
    snapshot_id: str,
    snapshot_label: str,
    manifest_sha256: str,
    manifest_file_sha256: str,
    manifest_path: Path,
    inventory_path: Path,
    inventory_file_sha256: str,
    rebuild: bool,
    chunk_size: int = 10_000,
) -> dict[str, int]:
    existing = await connection.fetchrow(
        "select ready,manifest_sha256 from analytics_snapshot_backup_sets where snapshot_id=$1",
        snapshot_id,
    )
    if existing and existing["ready"] and not rebuild:
        return {"objects": 0, "references": 0}
    _verify_frozen_inputs(
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        manifest_file_sha256=manifest_file_sha256,
        inventory_path=inventory_path,
        inventory_file_sha256=inventory_file_sha256,
    )
    await connection.execute(
        "drop index if exists ix_snapshot_backup_refs_history_role"
    )
    await connection.execute("drop index if exists ix_snapshot_backup_objects_status")
    async with connection.transaction():
        await connection.execute(
            "delete from analytics_snapshot_backup_refs where snapshot_id=$1", snapshot_id
        )
        await connection.execute(
            "delete from analytics_snapshot_backup_objects where snapshot_id=$1", snapshot_id
        )
        await connection.execute(
            """insert into analytics_snapshot_backup_sets(
                   snapshot_id,snapshot_label,manifest_sha256,ready)
               values($1,$2,$3,false)
               on conflict(snapshot_id) do update set
                 snapshot_label=excluded.snapshot_label,
                 manifest_sha256=excluded.manifest_sha256,
                 ready=false,object_count=0,reference_count=0,
                 last_verified_batch=0,status_counts='{}'::jsonb,refreshed_at=null""",
            snapshot_id,
            snapshot_label,
            manifest_sha256,
        )
    inventory = _open_readonly_sqlite(inventory_path, immutable=True)
    cursor = inventory.execute("select key,size from objects order by key")
    inventory_row = cursor.fetchone()
    object_rows: list[tuple[Any, ...]] = []
    reference_rows: list[tuple[Any, ...]] = []
    object_count = reference_count = 0
    try:
        for item in iter_manifest_objects(manifest_path):
            key = str(item["key"])
            while inventory_row is not None and str(inventory_row["key"]) < key:
                inventory_row = cursor.fetchone()
            present = inventory_row is not None and str(inventory_row["key"]) == key
            size = int(inventory_row["size"]) if present else None
            object_rows.append(
                (
                    snapshot_id,
                    key,
                    "not_backed_up" if present else "file_missing",
                    None,
                    size,
                    None,
                    None if present else "inventory_absent",
                )
            )
            object_count += 1
            references = item.get("references") or []
            for reference in references:
                reference_rows.append(
                    (
                        snapshot_id,
                        int(reference["history_id"]),
                        str(reference.get("task_id") or "") or None,
                        str(reference["role"]),
                        int(reference["ordinal"]),
                        str(reference["reference"]),
                        key,
                    )
                )
                reference_count += 1
            if len(object_rows) >= chunk_size:
                await _copy_initial_chunk(
                    connection,
                    object_rows=object_rows,
                    reference_rows=reference_rows,
                )
                object_rows.clear()
                reference_rows.clear()
        await _copy_initial_chunk(
            connection, object_rows=object_rows, reference_rows=reference_rows
        )
    finally:
        inventory.close()
    await connection.execute(
        """create index if not exists ix_snapshot_backup_refs_history_role
             on analytics_snapshot_backup_refs(history_id,role,snapshot_id);
           create index if not exists ix_snapshot_backup_objects_status
             on analytics_snapshot_backup_objects(snapshot_id,backup_status);"""
    )
    await connection.execute(
        """update analytics_snapshot_backup_sets
           set ready=true,object_count=$2,reference_count=$3,refreshed_at=now()
           where snapshot_id=$1""",
        snapshot_id,
        object_count,
        reference_count,
    )
    return {"objects": object_count, "references": reference_count}


def _read_batch(state_path: Path, batch_number: int) -> tuple[str | None, list[sqlite3.Row]]:
    state = _open_readonly_sqlite(state_path)
    try:
        batch = state.execute(
            "select status from snapshot_backup_batches where batch_number=?",
            (batch_number,),
        ).fetchone()
        if not batch:
            return None, []
        rows = state.execute(
            """select member.object_key,object.status,object.byte_size,object.sha256,
                      object.error_code,object.error_http_status
               from snapshot_backup_batch_objects member
               left join snapshot_objects object using(object_key)
               where member.batch_number=? order by member.object_key""",
            (batch_number,),
        ).fetchall()
        return str(batch["status"]), rows
    finally:
        state.close()


def _state_batches(state_path: Path, after_batch: int) -> tuple[list[int], list[int]]:
    state = _open_readonly_sqlite(state_path)
    try:
        verified = [
            int(row[0])
            for row in state.execute(
                """select batch_number from snapshot_backup_batches
                   where status='verified' and batch_number>? order by batch_number""",
                (after_batch,),
            )
        ]
        active = [
            int(row[0])
            for row in state.execute(
                """select batch_number from snapshot_backup_batches
                   where status in ('copying','transferring') order by batch_number"""
            )
        ]
        return verified, active
    finally:
        state.close()


async def _apply_batch(
    connection: asyncpg.Connection,
    *,
    snapshot_id: str,
    state_path: Path,
    batch_number: int,
) -> int:
    # The downloader uses rollback-journal SQLite. Keep each read transaction to one 5k batch.
    batch_status, rows = await asyncio.to_thread(_read_batch, state_path, batch_number)
    if not batch_status or not rows:
        return 0
    records = []
    for row in rows:
        state_record = dict(row)
        status = classify_snapshot_state(state_record, batch_status=batch_status)
        records.append(
            (
                str(row["object_key"]),
                status,
                batch_number,
                row["byte_size"],
                row["sha256"],
                row["error_code"],
            )
        )
    await connection.execute(
        """create temporary table if not exists snapshot_batch_updates(
               object_key text primary key,backup_status text not null,batch_number integer,
               byte_size bigint,sha256 char(64),error_code text) on commit preserve rows;
           truncate snapshot_batch_updates"""
    )
    await connection.copy_records_to_table(
        "snapshot_batch_updates",
        records=records,
        columns=(
            "object_key",
            "backup_status",
            "batch_number",
            "byte_size",
            "sha256",
            "error_code",
        ),
    )
    await connection.execute(
        """update analytics_snapshot_backup_objects target set
             backup_status=updates.backup_status,
             batch_number=case when updates.backup_status='backed_up'
                               then updates.batch_number else null end,
             byte_size=coalesce(updates.byte_size,target.byte_size),
             sha256=updates.sha256,error_code=updates.error_code,updated_at=now()
           from snapshot_batch_updates updates
           where target.snapshot_id=$1 and target.object_key=updates.object_key""",
        snapshot_id,
    )
    return len(records)


async def refresh_state(
    connection: asyncpg.Connection, *, snapshot_id: str, state_path: Path
) -> dict[str, Any]:
    row = await connection.fetchrow(
        "select ready,last_verified_batch from analytics_snapshot_backup_sets where snapshot_id=$1",
        snapshot_id,
    )
    if not row or not row["ready"]:
        raise RuntimeError("snapshot manifest index is not ready")
    verified, active = await asyncio.to_thread(
        _state_batches, state_path, int(row["last_verified_batch"])
    )
    updated = 0
    for batch_number in [*verified, *active]:
        updated += await _apply_batch(
            connection,
            snapshot_id=snapshot_id,
            state_path=state_path,
            batch_number=batch_number,
        )
    last_verified = max(verified, default=int(row["last_verified_batch"]))
    counts_rows = await connection.fetch(
        """select backup_status,count(*)::bigint count
           from analytics_snapshot_backup_objects where snapshot_id=$1 group by 1""",
        snapshot_id,
    )
    counts = {str(item["backup_status"]): int(item["count"]) for item in counts_rows}
    await connection.execute(
        """update analytics_snapshot_backup_sets set
             last_verified_batch=$2,status_counts=$3::jsonb,refreshed_at=now()
           where snapshot_id=$1""",
        snapshot_id,
        last_verified,
        json.dumps(counts, sort_keys=True),
    )
    return {
        "updated": updated,
        "verified_batches": len(verified),
        "active_batches": active,
        "last_verified_batch": last_verified,
        "status_counts": counts,
    }


async def run(args: argparse.Namespace) -> None:
    database_url = os.getenv("LOCAL_ANALYTICS_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("LOCAL_ANALYTICS_DATABASE_URL is required")
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = "postgresql://" + database_url.removeprefix("postgresql+asyncpg://")
    connection = await asyncpg.connect(database_url, command_timeout=3600)
    try:
        await ensure_schema(connection)
        imported = await import_manifest(
            connection,
            snapshot_id=args.snapshot_id,
            snapshot_label=args.snapshot_label,
            manifest_sha256=args.manifest_sha256,
            manifest_file_sha256=args.manifest_file_sha256,
            manifest_path=Path(args.manifest),
            inventory_path=Path(args.inventory),
            inventory_file_sha256=args.inventory_file_sha256,
            rebuild=args.rebuild,
        )
        refreshed = await refresh_state(
            connection,
            snapshot_id=args.snapshot_id,
            state_path=Path(args.state),
        )
        print(
            json.dumps(
                {
                    "status": "ready",
                    "snapshot_id": args.snapshot_id,
                    "imported": imported,
                    "refresh": refreshed,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-label", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--manifest-file-sha256", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--inventory-file-sha256", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--rebuild", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
