"""One-shot, controlled migration for the official QQCC V1/V2 config."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import RuntimeCheckpoint
from src.services.qqcc_config_service import (
    QQCC_LAZY_BOT_CONFIG_KEY,
    normalize_qqcc_config,
)
from src.services.qqcc_demo_media_service import clone_qqcc_v2_demo_media_to_v1


async def run(*, backup_path: Path, apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RuntimeCheckpoint).where(
                RuntimeCheckpoint.key == QQCC_LAZY_BOT_CONFIG_KEY
            ).with_for_update()
        )
        checkpoint = result.scalar_one_or_none()
        if checkpoint is None:
            raise RuntimeError("Official QQCC configuration does not exist")
        raw = checkpoint.value or {}
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "key": QQCC_LAZY_BOT_CONFIG_KEY,
                    "config": raw,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        migrated = await clone_qqcc_v2_demo_media_to_v1(normalize_qqcc_config(raw))
        summary = {
            "video_v1": len(migrated["video_scenes_v1"]),
            "video_v2": len(migrated["video_scenes_v2"]),
            "draw_v1": len(migrated["draw_scenes_v1"]),
            "draw_v2": len(migrated["draw_scenes_v2"]),
        }
        print(json.dumps(summary, ensure_ascii=False))
        if not apply:
            return
        checkpoint.value = migrated
        await db.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(backup_path=args.backup, apply=args.apply))


if __name__ == "__main__":
    main()
