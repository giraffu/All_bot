#!/usr/bin/env python3
"""Idempotently publish the repository's starter character-detail templates to test."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_ENV_FILE = ROOT / ".env.cloud.test"
ASSET_ROOT = ROOT / "assets" / "character_view_templates"


@dataclass(frozen=True)
class TemplateSeed:
    id: str
    filename: str
    view_type: str
    name: str
    gender: str
    sort_order: int


TEMPLATES = (
    TemplateSeed("a0000000-0000-4000-8000-000000000001", "female-torso-front.jpg", "torso_front", "女性胸部镜头", "female", 10),
    TemplateSeed("a0000000-0000-4000-8000-000000000002", "female-genitals-front-open.jpg", "genitals_front", "女性正面私处（双腿打开）", "female", 10),
    TemplateSeed("a0000000-0000-4000-8000-000000000003", "female-genitals-front-natural.png", "genitals_front", "女性正面私处（自然构图）", "female", 20),
    TemplateSeed("a0000000-0000-4000-8000-000000000004", "male-genitals-front.png", "genitals_front", "男性正面私处", "male", 30),
    TemplateSeed("a0000000-0000-4000-8000-000000000005", "female-pelvis-back.png", "pelvis_back", "女性背面私处", "female", 10),
)


def load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    if os.getenv("CLOUD_TEST_DATABASE_URL"):
        os.environ["DATABASE_URL"] = os.environ["CLOUD_TEST_DATABASE_URL"]
    if os.getenv("CLOUD_TEST_REDIS_URL"):
        os.environ["REDIS_URL"] = os.environ["CLOUD_TEST_REDIS_URL"]


def content_type(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }[path.suffix.lower()]


def durable_object_key(seed: TemplateSeed, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"character_assets/view_templates/seed/{seed.id}/{digest}{Path(seed.filename).suffix.lower()}"


async def seed_templates() -> None:
    from config import MINIO_BUCKET
    from src.database.core import AsyncSessionLocal
    from src.database.models import CharacterViewImageTemplate
    from src.services.storage import storage

    async with AsyncSessionLocal() as db:
        for seed in TEMPLATES:
            path = ASSET_ROOT / seed.filename
            payload = path.read_bytes()
            object_key = durable_object_key(seed, payload)
            uploaded = await asyncio.to_thread(
                storage.upload_bytes,
                payload,
                object_key,
                content_type(path),
                MINIO_BUCKET,
            )
            if not uploaded:
                raise RuntimeError(f"failed to upload {seed.filename}")
            row = await db.get(CharacterViewImageTemplate, seed.id)
            values = {
                "view_type": seed.view_type,
                "name": seed.name,
                "gender": seed.gender,
                "object_key": f"{MINIO_BUCKET}/{object_key}",
                "sort_order": seed.sort_order,
                "status": "active",
                "created_by": "repository-seed",
            }
            if row is None:
                db.add(CharacterViewImageTemplate(id=seed.id, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
        await db.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--confirm-test", action="store_true")
    args = parser.parse_args()
    if not args.confirm_test:
        parser.error("--confirm-test is required")
    load_env_file(args.env_file)
    environment = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "test")).lower()
    if environment in {"prod", "production"}:
        parser.error("refusing to seed a production environment")
    asyncio.run(seed_templates())
    print(f"seeded {len(TEMPLATES)} character view templates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
