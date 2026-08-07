#!/usr/bin/env python3
"""Atomically refresh the private R2 inventory consumed by temp cleanup."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from scripts.r2_temp_cleanup import PRODUCTION_BUCKET, _r2_client


def _last_modified(value: Any) -> str:
    if hasattr(value, "astimezone"):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def refresh_inventory(
    *, state_root: Path, client, bucket: str = PRODUCTION_BUCKET,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if bucket != PRODUCTION_BUCKET:
        raise ValueError("R2 temp cleanup inventory is restricted to user-data-prod")
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_root, 0o700)
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_path = state_root / f"inventory-{stamp}.sqlite3"
    if final_path.exists():
        raise FileExistsError(f"inventory revision already exists: {final_path.name}")
    temporary = state_root / f".{final_path.name}.tmp"
    if temporary.exists():
        temporary.unlink()
    db = sqlite3.connect(temporary)
    object_count = 0
    total_bytes = 0
    try:
        db.execute(
            "create table objects(key text primary key,size integer not null,"
            "etag text not null,last_modified text not null) without rowid"
        )
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            rows = []
            for item in page.get("Contents", []):
                size = int(item.get("Size") or 0)
                rows.append((
                    str(item["Key"]), size,
                    str(item.get("ETag") or "").strip('"'),
                    _last_modified(item.get("LastModified")),
                ))
                object_count += 1
                total_bytes += size
            if rows:
                db.executemany("insert into objects values(?,?,?,?)", rows)
                db.commit()
        if db.execute("pragma integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("inventory integrity check failed")
    except Exception:
        db.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        db.close()
    os.chmod(temporary, 0o600)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, final_path)
    link_tmp = state_root / ".current.sqlite3.tmp"
    if link_tmp.exists() or link_tmp.is_symlink():
        link_tmp.unlink()
    link_tmp.symlink_to(final_path.name)
    os.replace(link_tmp, state_root / "current.sqlite3")
    directory_fd = os.open(state_root, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return {
        "path": str(final_path), "current": str(state_root / "current.sqlite3"),
        "object_count": object_count, "bytes": total_bytes,
        "sha256": _file_sha256(final_path),
    }


def main() -> None:
    state_root = Path(os.getenv(
        "R2_TEMP_CLEANUP_STATE_ROOT", "/var/lib/allbot-r2-temp-cleanup"
    ))
    print(json.dumps(
        refresh_inventory(state_root=state_root, client=_r2_client()),
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
