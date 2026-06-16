import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlparse

from PIL import Image, ImageOps
from sqlalchemy import desc, func, select, union


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _find_argv_value(argv: list[str], name: str) -> str | None:
    prefix = f"{name}="
    for index, arg in enumerate(argv):
        if arg == name and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return None


def _load_env_file_from_argv(argv: list[str]) -> None:
    env_file = _find_argv_value(argv, "--env-file")
    if not env_file:
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=True)
    except Exception:
        for raw_line in Path(env_file).read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key.replace("_", "").isalnum() or key[0].isdigit():
                continue
            os.environ[key] = value.strip().strip("'\"")


def _enable_legacy_storage_for_migration(argv: list[str]) -> None:
    source_storage = _find_argv_value(argv, "--source-storage")
    hotset_profile = _find_argv_value(argv, "--hotset-profile")
    if source_storage == "legacy" or (hotset_profile and source_storage != "current"):
        os.environ["LEGACY_MINIO_READ_FALLBACK_ENABLED"] = "true"


_load_env_file_from_argv(sys.argv)
_enable_legacy_storage_for_migration(sys.argv)

from src.core.media_paths import (  # noqa: E402
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_legacy_r2_key,
    build_storage_r2_object_key,
    get_media_type_from_history,
    resolve_legacy_storage_object,
    resolve_storage_object,
)
from src.core.media_processor import generate_and_upload_thumbnail  # noqa: E402
from src.core.media_urls import build_thumbnail_file_path  # noqa: E402
from src.database.core import AsyncSessionLocal  # noqa: E402
from src.database.models import (  # noqa: E402
    GalleryPost,
    GalleryPromptUnlock,
    History,
    User,
    UserInteraction,
)
from src.services.storage import storage  # noqa: E402

logger = logging.getLogger(__name__)

ResolveSourceObjectFunc = Callable[[str], tuple[str, str]]

HOTSET_PROFILE_CLOUD_PROD_LAG_FIX = "cloud-prod-lag-fix"
HOTSET_PROFILE_WEB_VISIBLE_RETIRE_LEGACY = "web-visible-retire-legacy"
HOTSET_PROFILES = [
    HOTSET_PROFILE_CLOUD_PROD_LAG_FIX,
    HOTSET_PROFILE_WEB_VISIBLE_RETIRE_LEGACY,
]
HOTSET_SOURCE_LIMITS = {
    "gallery_latest": 300,
    "gallery_likes_top": 1000,
    "gallery_applied_top": 1000,
    "recent_history": 3000,
    "recent_like_apply_interactions": 3000,
    "recent_favorites": 1000,
    "recent_prompt_unlocks": 1000,
}
HOTSET_WAVE_CAPS = {
    "first": 5000,
    "second": 12000,
}
HOTSET_MAX_BATCH_SIZE = 500
HOTSET_COPY_TIMEOUT_SECONDS = int(os.getenv("HOTSET_COPY_TIMEOUT_SECONDS", "180"))

MediaStatus = Literal[
    "exists",
    "would_upload",
    "uploaded",
    "source_missing",
    "upload_failed",
]
ThumbnailStatus = Literal[
    "exists",
    "skipped",
    "would_copy",
    "copied",
    "would_generate",
    "generated",
    "source_missing",
    "copy_failed",
    "generate_failed",
]
InputStatus = Literal[
    "exists",
    "skipped",
    "skipped_external",
    "would_upload",
    "uploaded",
    "source_missing",
    "upload_failed",
]


@dataclass
class HistoryR2Candidate:
    history_id: int
    user_id: int | None
    username: str | None
    task_id: str | None
    history_type: str | None
    media_type: str
    output_file: str
    source_bucket: str
    source_object: str
    media_r2_key: str
    thumbnail_file: str
    thumbnail_source_bucket: str
    thumbnail_source_object: str
    thumbnail_r2_key: str
    input_files: list["InputFileCandidate"]


@dataclass
class InputFileCandidate:
    file_path: str
    source_bucket: str | None
    source_object: str | None
    r2_key: str | None
    skip_reason: str | None = None


@dataclass
class InputFileResult:
    candidate: InputFileCandidate
    status: InputStatus


@dataclass
class CandidateResult:
    candidate: HistoryR2Candidate
    media_status: MediaStatus
    thumbnail_status: ThumbnailStatus
    input_results: list[InputFileResult]


@dataclass
class BackfillSummary:
    mode: Literal["dry-run", "apply"]
    scanned: int
    media_exists: int
    media_missing_on_source: int
    media_would_upload: int
    media_uploaded: int
    media_failed: int
    thumbnail_exists: int
    thumbnail_skipped: int
    thumbnail_missing_on_source: int
    thumbnail_would_copy: int
    thumbnail_copied: int
    thumbnail_would_generate: int
    thumbnail_generated: int
    thumbnail_failed: int
    input_exists: int
    input_skipped: int
    input_skipped_external: int
    input_missing_on_source: int
    input_would_upload: int
    input_uploaded: int
    input_failed: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HotsetSelection:
    profile: str
    wave: str
    candidate_cap: int
    selected_count: int
    batch_count: int
    skipped_by_cursor: int
    source_counts: dict[str, dict[str, int]]

    def to_dict(self) -> dict:
        return asdict(self)


def build_history_r2_candidate(
    *,
    history_id: int,
    user_id: int | None,
    username: str | None,
    task_id: str | None,
    history_type: str | None,
    output_file: str,
    input_file: str | None = None,
    resolve_source_object_func: ResolveSourceObjectFunc = resolve_storage_object,
) -> HistoryR2Candidate:
    media_type = get_media_type_from_history(history_type)
    source_bucket, source_object = resolve_source_object_func(output_file)
    thumbnail_file = build_thumbnail_file_path(output_file, media_type)
    thumbnail_source_bucket, thumbnail_source_object = resolve_source_object_func(
        thumbnail_file
    )

    media_r2_key = (
        build_history_r2_media_key(task_id, output_file)
        if task_id
        else build_legacy_r2_key(output_file)
    )
    thumbnail_r2_key = (
        build_history_r2_thumbnail_key(task_id, media_type)
        if task_id
        else build_legacy_r2_key(thumbnail_file)
    )

    return HistoryR2Candidate(
        history_id=history_id,
        user_id=user_id,
        username=username,
        task_id=task_id,
        history_type=history_type,
        media_type=media_type,
        output_file=output_file,
        source_bucket=source_bucket,
        source_object=source_object,
        media_r2_key=media_r2_key,
        thumbnail_file=thumbnail_file,
        thumbnail_source_bucket=thumbnail_source_bucket,
        thumbnail_source_object=thumbnail_source_object,
        thumbnail_r2_key=thumbnail_r2_key,
        input_files=build_input_file_candidates(
            input_file,
            resolve_source_object_func=resolve_source_object_func,
        ),
    )


def _is_external_input_file(file_path: str) -> bool:
    parsed = urlparse(file_path)
    return parsed.scheme in {"http", "https", "data"}


def build_input_file_candidates(
    input_file: str | None,
    *,
    resolve_source_object_func: ResolveSourceObjectFunc = resolve_storage_object,
) -> list[InputFileCandidate]:
    if not input_file:
        return []

    candidates: list[InputFileCandidate] = []
    seen: set[str] = set()
    for raw_item in str(input_file).split("|"):
        file_path = raw_item.strip()
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        if _is_external_input_file(file_path):
            candidates.append(
                InputFileCandidate(
                    file_path=file_path,
                    source_bucket=None,
                    source_object=None,
                    r2_key=None,
                    skip_reason="external",
                )
            )
            continue
        source_bucket, source_object = resolve_source_object_func(file_path)
        candidates.append(
            InputFileCandidate(
                file_path=file_path,
                source_bucket=source_bucket,
                source_object=source_object,
                r2_key=build_storage_r2_object_key(file_path),
            )
        )
    return candidates


def build_user_visible_history_ids_stmt(*, recent_limit: int):
    recent_ranked = (
        select(
            History.id.label("history_id"),
            func.row_number()
            .over(partition_by=History.user_id, order_by=desc(History.id))
            .label("row_number"),
        )
        .subquery()
    )
    recent_ids = select(recent_ranked.c.history_id).where(
        recent_ranked.c.row_number <= recent_limit
    )
    gallery_ids = (
        select(History.id.label("history_id"))
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .where(History.is_visible.is_not(False))
    )
    favorited_history_ids = select(History.id.label("history_id")).where(
        History.is_favorited.is_(True),
        History.is_visible.is_not(False),
    )
    interacted_gallery_ids = (
        select(History.id.label("history_id"))
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .join(UserInteraction, UserInteraction.post_id == GalleryPost.id)
        .where(
            GalleryPost.is_active.is_(True),
            UserInteraction.action_type.in_(["like", "apply"]),
            History.is_visible.is_not(False),
        )
    )
    prompt_unlocked_gallery_ids = (
        select(History.id.label("history_id"))
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .join(GalleryPromptUnlock, GalleryPromptUnlock.post_id == GalleryPost.id)
        .where(
            GalleryPost.is_active.is_(True),
            History.is_visible.is_not(False),
        )
    )

    return union(
        recent_ids,
        gallery_ids,
        favorited_history_ids,
        interacted_gallery_ids,
        prompt_unlocked_gallery_ids,
    ).subquery()


async def collect_limited_user_visible_history_ids(
    session,
    *,
    recent_limit: int,
    limit: int,
) -> list[int]:
    _ = recent_limit
    seen: set[int] = set()
    history_ids: list[int] = []

    async def collect_from_stmt(stmt) -> None:
        remaining = limit - len(history_ids)
        if remaining <= 0:
            return
        rows = (await session.execute(stmt.limit(remaining))).scalars().all()
        for history_id in rows:
            if history_id in seen:
                continue
            seen.add(history_id)
            history_ids.append(history_id)
            if len(history_ids) >= limit:
                return

    common_history_filters = (
        History.output_file.is_not(None),
        History.output_file != "",
        History.is_visible.is_not(False),
    )

    await collect_from_stmt(
        select(History.id)
        .where(*common_history_filters)
        .order_by(desc(History.id))
    )
    await collect_from_stmt(
        select(History.id)
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .where(*common_history_filters)
        .order_by(desc(History.id))
    )
    await collect_from_stmt(
        select(History.id)
        .where(
            *common_history_filters,
            History.is_favorited.is_(True),
        )
        .order_by(desc(History.id))
    )
    await collect_from_stmt(
        select(History.id)
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .join(UserInteraction, UserInteraction.post_id == GalleryPost.id)
        .where(
            *common_history_filters,
            GalleryPost.is_active.is_(True),
            UserInteraction.action_type.in_(["like", "apply"]),
        )
        .order_by(desc(History.id))
    )
    await collect_from_stmt(
        select(History.id)
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .join(GalleryPromptUnlock, GalleryPromptUnlock.post_id == GalleryPost.id)
        .where(
            *common_history_filters,
            GalleryPost.is_active.is_(True),
        )
        .order_by(desc(History.id))
    )

    return history_ids


def _append_unique_history_ids(
    target: list[int],
    seen: set[int],
    source_rows: list[int],
    *,
    cap: int,
) -> int:
    added = 0
    for history_id in source_rows:
        if history_id in seen:
            continue
        seen.add(history_id)
        target.append(history_id)
        added += 1
        if len(target) >= cap:
            break
    return added


async def _fetch_history_ids(session, stmt) -> list[int]:
    rows = (await session.execute(stmt)).scalars().all()
    return [int(history_id) for history_id in rows if history_id is not None]


async def collect_cloud_prod_lag_fix_history_ids(
    session,
    *,
    wave: Literal["first", "second"] = "first",
    total_limit: int | None = None,
) -> tuple[list[int], dict[str, dict[str, int]]]:
    wave_cap = HOTSET_WAVE_CAPS[wave]
    cap = min(wave_cap, total_limit) if total_limit else wave_cap
    if cap <= 0:
        return [], {}

    common_history_filters = (
        History.output_file.is_not(None),
        History.output_file != "",
        History.is_visible.is_not(False),
    )
    selected: list[int] = []
    seen: set[int] = set()
    source_counts: dict[str, dict[str, int]] = {}

    async def collect_source(label: str, stmt) -> None:
        if len(selected) >= cap:
            source_counts[label] = {"raw": 0, "added": 0}
            return
        rows = await _fetch_history_ids(session, stmt)
        added = _append_unique_history_ids(selected, seen, rows, cap=cap)
        source_counts[label] = {"raw": len(rows), "added": added}

    gallery_latest = (
        select(
            GalleryPost.task_id.label("task_id"),
            GalleryPost.created_at.label("sort_created_at"),
            GalleryPost.id.label("post_id"),
        )
        .where(GalleryPost.is_active.is_(True), GalleryPost.task_id.is_not(None))
        .order_by(GalleryPost.created_at.desc(), GalleryPost.id.desc())
        .limit(HOTSET_SOURCE_LIMITS["gallery_latest"])
        .subquery()
    )
    await collect_source(
        "gallery_latest",
        select(History.id)
        .select_from(gallery_latest)
        .join(History, History.task_id == gallery_latest.c.task_id)
        .where(*common_history_filters)
        .order_by(
            gallery_latest.c.sort_created_at.desc(),
            gallery_latest.c.post_id.desc(),
            History.id.desc(),
        ),
    )

    gallery_likes = (
        select(
            GalleryPost.task_id.label("task_id"),
            GalleryPost.likes_count.label("sort_count"),
            GalleryPost.id.label("post_id"),
        )
        .where(GalleryPost.is_active.is_(True), GalleryPost.task_id.is_not(None))
        .order_by(GalleryPost.likes_count.desc(), GalleryPost.id.desc())
        .limit(HOTSET_SOURCE_LIMITS["gallery_likes_top"])
        .subquery()
    )
    await collect_source(
        "gallery_likes_top",
        select(History.id)
        .select_from(gallery_likes)
        .join(History, History.task_id == gallery_likes.c.task_id)
        .where(*common_history_filters)
        .order_by(
            gallery_likes.c.sort_count.desc(),
            gallery_likes.c.post_id.desc(),
            History.id.desc(),
        ),
    )

    gallery_applied = (
        select(
            GalleryPost.task_id.label("task_id"),
            GalleryPost.applied_count.label("sort_count"),
            GalleryPost.id.label("post_id"),
        )
        .where(GalleryPost.is_active.is_(True), GalleryPost.task_id.is_not(None))
        .order_by(GalleryPost.applied_count.desc(), GalleryPost.id.desc())
        .limit(HOTSET_SOURCE_LIMITS["gallery_applied_top"])
        .subquery()
    )
    await collect_source(
        "gallery_applied_top",
        select(History.id)
        .select_from(gallery_applied)
        .join(History, History.task_id == gallery_applied.c.task_id)
        .where(*common_history_filters)
        .order_by(
            gallery_applied.c.sort_count.desc(),
            gallery_applied.c.post_id.desc(),
            History.id.desc(),
        ),
    )

    await collect_source(
        "recent_history",
        select(History.id)
        .where(*common_history_filters)
        .order_by(History.id.desc())
        .limit(HOTSET_SOURCE_LIMITS["recent_history"]),
    )

    recent_interactions = (
        select(
            UserInteraction.post_id.label("post_id"),
            UserInteraction.id.label("interaction_id"),
        )
        .where(UserInteraction.action_type.in_(["like", "apply"]))
        .order_by(UserInteraction.id.desc())
        .limit(HOTSET_SOURCE_LIMITS["recent_like_apply_interactions"])
        .subquery()
    )
    await collect_source(
        "recent_like_apply_interactions",
        select(History.id)
        .select_from(recent_interactions)
        .join(GalleryPost, GalleryPost.id == recent_interactions.c.post_id)
        .join(History, History.task_id == GalleryPost.task_id)
        .where(GalleryPost.is_active.is_(True), *common_history_filters)
        .order_by(recent_interactions.c.interaction_id.desc(), History.id.desc()),
    )

    await collect_source(
        "recent_favorites",
        select(History.id)
        .where(*common_history_filters, History.is_favorited.is_(True))
        .order_by(History.id.desc())
        .limit(HOTSET_SOURCE_LIMITS["recent_favorites"]),
    )

    recent_prompt_unlocks = (
        select(
            GalleryPromptUnlock.post_id.label("post_id"),
            GalleryPromptUnlock.id.label("unlock_id"),
        )
        .order_by(GalleryPromptUnlock.id.desc())
        .limit(HOTSET_SOURCE_LIMITS["recent_prompt_unlocks"])
        .subquery()
    )
    await collect_source(
        "recent_prompt_unlocks",
        select(History.id)
        .select_from(recent_prompt_unlocks)
        .join(GalleryPost, GalleryPost.id == recent_prompt_unlocks.c.post_id)
        .join(History, History.task_id == GalleryPost.task_id)
        .where(GalleryPost.is_active.is_(True), *common_history_filters)
        .order_by(recent_prompt_unlocks.c.unlock_id.desc(), History.id.desc()),
    )

    return selected, source_counts


async def collect_web_visible_retire_legacy_history_ids(
    session,
    *,
    recent_limit: int = 8,
    include_per_user_recent: bool = True,
    total_limit: int | None = None,
) -> tuple[list[int], dict[str, dict[str, int]]]:
    cap = total_limit if total_limit and total_limit > 0 else sys.maxsize
    common_history_filters = (
        History.output_file.is_not(None),
        History.output_file != "",
        History.is_visible.is_not(False),
    )
    selected: list[int] = []
    seen: set[int] = set()
    source_counts: dict[str, dict[str, int]] = {}

    async def collect_source(label: str, stmt) -> None:
        if len(selected) >= cap:
            source_counts[label] = {"raw": 0, "added": 0}
            return
        rows = await _fetch_history_ids(session, stmt)
        added = _append_unique_history_ids(selected, seen, rows, cap=cap)
        source_counts[label] = {"raw": len(rows), "added": added}

    if include_per_user_recent:
        recent_ranked = (
            select(
                History.id.label("history_id"),
                func.row_number()
                .over(partition_by=History.user_id, order_by=desc(History.id))
                .label("row_number"),
            )
            .where(*common_history_filters)
            .subquery()
        )
        await collect_source(
            "per_user_recent_visible_history",
            select(recent_ranked.c.history_id)
            .where(recent_ranked.c.row_number <= recent_limit)
            .order_by(recent_ranked.c.history_id.desc()),
        )
    else:
        source_counts["per_user_recent_visible_history"] = {"raw": 0, "added": 0}

    await collect_source(
        "all_gallery_posts",
        select(History.id)
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .where(*common_history_filters)
        .order_by(GalleryPost.id.desc(), History.id.desc()),
    )

    await collect_source(
        "history_favorites",
        select(History.id)
        .where(*common_history_filters, History.is_favorited.is_(True))
        .order_by(History.id.desc()),
    )

    await collect_source(
        "gallery_like_apply_interactions",
        select(History.id)
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .join(UserInteraction, UserInteraction.post_id == GalleryPost.id)
        .where(
            *common_history_filters,
            GalleryPost.is_active.is_(True),
            UserInteraction.action_type.in_(["like", "apply"]),
        )
        .order_by(UserInteraction.id.desc(), History.id.desc()),
    )

    await collect_source(
        "gallery_prompt_unlocks",
        select(History.id)
        .join(GalleryPost, GalleryPost.task_id == History.task_id)
        .join(GalleryPromptUnlock, GalleryPromptUnlock.post_id == GalleryPost.id)
        .where(*common_history_filters, GalleryPost.is_active.is_(True))
        .order_by(GalleryPromptUnlock.id.desc(), History.id.desc()),
    )

    return selected, source_counts


def select_hotset_batch(
    history_ids: list[int],
    *,
    batch_size: int,
    processed_history_ids: set[int] | None = None,
) -> tuple[list[int], int]:
    processed_history_ids = processed_history_ids or set()
    batch: list[int] = []
    skipped = 0
    for history_id in history_ids:
        if history_id in processed_history_ids:
            skipped += 1
            continue
        batch.append(history_id)
        if len(batch) >= batch_size:
            break
    return batch, skipped


def read_hotset_cursor(cursor_file: Path | None) -> set[int]:
    if cursor_file is None or not cursor_file.exists():
        return set()
    payload = json.loads(cursor_file.read_text(encoding="utf-8"))
    processed = payload.get("processed_history_ids", [])
    return {int(history_id) for history_id in processed}


def write_hotset_cursor(
    cursor_file: Path,
    *,
    profile: str,
    wave: str,
    processed_history_ids: set[int],
) -> None:
    cursor_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile,
        "wave": wave,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "processed_history_ids": sorted(processed_history_ids),
    }
    cursor_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def collect_history_r2_candidates(
    session,
    *,
    history_ids: list[int] | None = None,
    username: str | None = None,
    user_id: int | None = None,
    task_id: str | None = None,
    favorited_only: bool = False,
    source: str | None = None,
    media_type: Literal["all", "video", "image"] = "all",
    visible_scope: Literal["all", "user-visible"] = "all",
    recent_limit: int = 8,
    limit: int | None = None,
    resolve_source_object_func: ResolveSourceObjectFunc = resolve_storage_object,
) -> list[HistoryR2Candidate]:
    stmt = (
        select(
            History.id,
            History.user_id,
            User.username,
            History.task_id,
            History.type,
            History.output_file,
            History.input_file,
        )
        .select_from(History)
        .outerjoin(User, User.id == History.user_id)
        .where(History.output_file.is_not(None), History.output_file != "")
        .order_by(History.created_at.desc(), History.id.desc())
    )

    if visible_scope == "user-visible" and limit is not None:
        limited_history_ids = await collect_limited_user_visible_history_ids(
            session,
            recent_limit=recent_limit,
            limit=limit,
        )
        if not limited_history_ids:
            return []
        stmt = stmt.where(History.id.in_(limited_history_ids))
        limit = None
    elif visible_scope == "user-visible":
        visible_history_ids = build_user_visible_history_ids_stmt(
            recent_limit=recent_limit
        )
        stmt = stmt.join(
            visible_history_ids,
            History.id == visible_history_ids.c.history_id,
        ).where(
            History.is_visible.is_not(False),
        )

    if history_ids is not None:
        if not history_ids:
            return []
        stmt = stmt.where(History.id.in_(history_ids))
        limit = None
    if username is not None:
        stmt = stmt.where(func.lower(User.username) == username.lower())
    if user_id is not None:
        stmt = stmt.where(History.user_id == user_id)
    if task_id is not None:
        stmt = stmt.where(History.task_id == task_id)
    if favorited_only:
        stmt = stmt.where(History.is_favorited.is_(True))
    if source is not None:
        stmt = stmt.where(History.source == source)
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).all()
    candidates = [
        build_history_r2_candidate(
            history_id=history_id,
            user_id=row_user_id,
            username=row_username,
            task_id=row_task_id,
            history_type=row_history_type,
            output_file=row_output_file,
            input_file=row_input_file,
            resolve_source_object_func=resolve_source_object_func,
        )
        for (
            history_id,
            row_user_id,
            row_username,
            row_task_id,
            row_history_type,
            row_output_file,
            row_input_file,
        ) in rows
    ]

    if history_ids is not None:
        history_id_order = {
            history_id: index for index, history_id in enumerate(history_ids)
        }
        candidates.sort(
            key=lambda candidate: history_id_order.get(
                candidate.history_id,
                len(history_id_order),
            )
        )

    if media_type == "all":
        return candidates
    return [candidate for candidate in candidates if candidate.media_type == media_type]


async def process_history_r2_candidate(
    candidate: HistoryR2Candidate,
    *,
    apply_changes: bool,
    media_only: bool,
    generate_missing_thumbnails: bool,
    async_object_exists_func,
    async_r2_object_exists_func,
    async_copy_to_r2_func,
    generate_and_upload_thumbnail_func,
    generate_and_upload_thumbnail_from_r2_media_func,
    include_input_files: bool = False,
) -> CandidateResult:
    async def copy_to_r2_with_retries(
        source_bucket: str,
        source_object: str,
        r2_key: str,
        *,
        attempts: int = 2,
    ) -> bool:
        for attempt in range(1, attempts + 1):
            try:
                uploaded = await asyncio.wait_for(
                    async_copy_to_r2_func(
                        source_bucket,
                        source_object,
                        r2_key,
                    ),
                    timeout=HOTSET_COPY_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Timed out copying to R2 after %ss for key=%s",
                    HOTSET_COPY_TIMEOUT_SECONDS,
                    r2_key,
                )
                uploaded = False
            except Exception:
                logger.exception("Unexpected copy to R2 failure for key=%s", r2_key)
                uploaded = False
            if uploaded:
                return True
            if attempt < attempts:
                logger.warning(
                    "Retrying copy to R2 after failed attempt %s/%s for key=%s",
                    attempt,
                    attempts,
                    r2_key,
                )
                await asyncio.sleep(min(2 * attempt, 5))
        return False

    media_source_exists = await async_object_exists_func(
        candidate.source_bucket,
        candidate.source_object,
    )
    media_r2_exists = await async_r2_object_exists_func(candidate.media_r2_key)

    if media_r2_exists:
        media_status: MediaStatus = "exists"
    elif not media_source_exists:
        media_status = "source_missing"
    elif not apply_changes:
        media_status = "would_upload"
    else:
        uploaded = await copy_to_r2_with_retries(
            candidate.source_bucket,
            candidate.source_object,
            candidate.media_r2_key,
        )
        media_status = "uploaded" if uploaded else "upload_failed"

    if media_only:
        thumbnail_status: ThumbnailStatus = "skipped"
    else:
        thumbnail_r2_exists = await async_r2_object_exists_func(candidate.thumbnail_r2_key)
        if thumbnail_r2_exists:
            thumbnail_status = "exists"
        else:
            thumbnail_source_exists = await async_object_exists_func(
                candidate.thumbnail_source_bucket,
                candidate.thumbnail_source_object,
            )
            if thumbnail_source_exists:
                if not apply_changes:
                    thumbnail_status = "would_copy"
                else:
                    uploaded = await copy_to_r2_with_retries(
                        candidate.thumbnail_source_bucket,
                        candidate.thumbnail_source_object,
                        candidate.thumbnail_r2_key,
                    )
                    thumbnail_status = "copied" if uploaded else "copy_failed"
            elif not generate_missing_thumbnails:
                thumbnail_status = "source_missing"
            elif media_r2_exists:
                if not apply_changes:
                    thumbnail_status = "would_generate"
                else:
                    try:
                        await generate_and_upload_thumbnail_from_r2_media_func(
                            candidate.media_r2_key,
                            candidate.media_type,
                            candidate.thumbnail_r2_key,
                        )
                        thumbnail_status = "generated"
                    except Exception:
                        logger.exception(
                            "Failed to generate thumbnail from R2 for history_id=%s task_id=%s",
                            candidate.history_id,
                            candidate.task_id,
                        )
                        thumbnail_status = "generate_failed"
            elif not media_source_exists:
                thumbnail_status = "source_missing"
            elif not apply_changes:
                thumbnail_status = "would_generate"
            else:
                try:
                    await generate_and_upload_thumbnail_func(
                        candidate.output_file,
                        candidate.media_type,
                        candidate.thumbnail_r2_key,
                    )
                    thumbnail_status = "generated"
                except Exception:
                    logger.exception(
                        "Failed to generate thumbnail for history_id=%s task_id=%s",
                        candidate.history_id,
                        candidate.task_id,
                    )
                    thumbnail_status = "generate_failed"

    input_results: list[InputFileResult] = []
    if include_input_files:
        for input_file in candidate.input_files:
            if input_file.skip_reason == "external":
                input_status: InputStatus = "skipped_external"
            elif (
                not input_file.source_bucket
                or not input_file.source_object
                or not input_file.r2_key
            ):
                input_status = "skipped"
            elif await async_r2_object_exists_func(input_file.r2_key):
                input_status = "exists"
            elif not await async_object_exists_func(
                input_file.source_bucket,
                input_file.source_object,
            ):
                input_status = "source_missing"
            elif not apply_changes:
                input_status = "would_upload"
            else:
                uploaded = await copy_to_r2_with_retries(
                    input_file.source_bucket,
                    input_file.source_object,
                    input_file.r2_key,
                )
                input_status = "uploaded" if uploaded else "upload_failed"
            input_results.append(
                InputFileResult(candidate=input_file, status=input_status)
            )

    return CandidateResult(
        candidate=candidate,
        media_status=media_status,
        thumbnail_status=thumbnail_status,
        input_results=input_results,
    )


async def generate_and_upload_thumbnail_from_r2_media(
    media_r2_key: str,
    media_type: str,
    thumbnail_r2_key: str,
) -> None:
    """Generate a standard history thumbnail from an already-warmed R2 original."""
    if not storage.r2_client or not storage.r2_bucket:
        raise RuntimeError("R2 client 未初始化，无法从 R2 原文件生成缩略图。")

    temp_dir = tempfile.mkdtemp(prefix="r2-thumb-")
    try:
        thumb_ext = ".jpg" if media_type == "video" else ".webp"
        thumb_local_path = os.path.join(temp_dir, f"thumb{thumb_ext}")

        if media_type == "video":
            input_url = await asyncio.to_thread(
                storage.r2_client.generate_presigned_url,
                "get_object",
                Params={"Bucket": storage.r2_bucket, "Key": media_r2_key},
                ExpiresIn=3600,
            )
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                "00:00:00.000",
                "-i",
                input_url,
                "-frames:v",
                "1",
                "-q:v",
                "5",
                thumb_local_path,
            ]
            await asyncio.to_thread(
                subprocess.run,
                ffmpeg_cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            content_type = "image/jpeg"
        else:
            response = await asyncio.to_thread(
                storage.r2_client.get_object,
                Bucket=storage.r2_bucket,
                Key=media_r2_key,
            )
            try:
                media_bytes = await asyncio.to_thread(response["Body"].read)
            finally:
                response["Body"].close()

            def process_image() -> None:
                with Image.open(BytesIO(media_bytes)) as img:
                    img = ImageOps.exif_transpose(img)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    max_width = 600
                    if img.width > max_width:
                        ratio = max_width / img.width
                        img = img.resize(
                            (max_width, int(img.height * ratio)),
                            Image.Resampling.LANCZOS,
                        )
                    img.save(thumb_local_path, "WEBP", quality=80, method=6)

            await asyncio.to_thread(process_image)
            content_type = "image/webp"

        await asyncio.to_thread(
            storage.r2_client.upload_file,
            thumb_local_path,
            storage.r2_bucket,
            thumbnail_r2_key,
            ExtraArgs={"ContentType": content_type},
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def summarize_results(
    results: list[CandidateResult],
    *,
    apply_changes: bool,
) -> BackfillSummary:
    def _count_media(status: MediaStatus) -> int:
        return sum(1 for result in results if result.media_status == status)

    def _count_thumb(status: ThumbnailStatus) -> int:
        return sum(1 for result in results if result.thumbnail_status == status)

    def _count_input(status: InputStatus) -> int:
        return sum(
            1
            for result in results
            for input_result in getattr(result, "input_results", [])
            if input_result.status == status
        )

    return BackfillSummary(
        mode="apply" if apply_changes else "dry-run",
        scanned=len(results),
        media_exists=_count_media("exists"),
        media_missing_on_source=_count_media("source_missing"),
        media_would_upload=_count_media("would_upload"),
        media_uploaded=_count_media("uploaded"),
        media_failed=_count_media("upload_failed"),
        thumbnail_exists=_count_thumb("exists"),
        thumbnail_skipped=_count_thumb("skipped"),
        thumbnail_missing_on_source=_count_thumb("source_missing"),
        thumbnail_would_copy=_count_thumb("would_copy"),
        thumbnail_copied=_count_thumb("copied"),
        thumbnail_would_generate=_count_thumb("would_generate"),
        thumbnail_generated=_count_thumb("generated"),
        thumbnail_failed=_count_thumb("copy_failed")
        + _count_thumb("generate_failed"),
        input_exists=_count_input("exists"),
        input_skipped=_count_input("skipped"),
        input_skipped_external=_count_input("skipped_external"),
        input_missing_on_source=_count_input("source_missing"),
        input_would_upload=_count_input("would_upload"),
        input_uploaded=_count_input("uploaded"),
        input_failed=_count_input("upload_failed"),
    )


def should_mark_hotset_processed(result: CandidateResult) -> bool:
    """Keep transient transfer failures retryable in later hotset batches."""
    if result.media_status == "upload_failed":
        return False
    if result.thumbnail_status in {"copy_failed", "generate_failed"}:
        return False
    if any(
        input_result.status == "upload_failed"
        for input_result in result.input_results
    ):
        return False
    return True


def write_backfill_report(
    *,
    report_dir: Path,
    summary: BackfillSummary,
    results: list[CandidateResult],
    source_storage: Literal["current", "legacy"],
    media_only: bool,
    include_input_files: bool,
    generate_missing_thumbnails: bool,
    concurrency: int,
    hotset_selection: HotsetSelection | None = None,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    profile = hotset_selection.profile if hotset_selection else "standard"
    base_name = f"media_hotset_backfill_{profile}_{timestamp}"
    json_path = report_dir / f"{base_name}.json"
    md_path = report_dir / f"{base_name}.md"

    result_rows = [
        {
            "history_id": result.candidate.history_id,
            "user_id": result.candidate.user_id,
            "task_id": result.candidate.task_id,
            "media_type": result.candidate.media_type,
            "media_status": result.media_status,
            "thumbnail_status": result.thumbnail_status,
            "media_r2_key": result.candidate.media_r2_key,
            "thumbnail_r2_key": result.candidate.thumbnail_r2_key,
            "input_files": [
                {
                    "file_path": input_result.candidate.file_path,
                    "status": input_result.status,
                    "r2_key": input_result.candidate.r2_key,
                    "skip_reason": input_result.candidate.skip_reason,
                }
                for input_result in result.input_results
            ],
        }
        for result in results
    ]
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_storage": source_storage,
        "media_only": media_only,
        "include_input_files": include_input_files,
        "generate_missing_thumbnails": generate_missing_thumbnails,
        "concurrency": concurrency,
        "hotset": hotset_selection.to_dict() if hotset_selection else None,
        "summary": summary.to_dict(),
        "results": result_rows,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Media Hotset Backfill Report",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- mode: `{summary.mode}`",
        f"- source_storage: `{source_storage}`",
        f"- scanned: `{summary.scanned}`",
        f"- media_only: `{media_only}`",
        f"- include_input_files: `{include_input_files}`",
        f"- generate_missing_thumbnails: `{generate_missing_thumbnails}`",
        f"- concurrency: `{concurrency}`",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.to_dict().items():
        lines.append(f"- {key}: `{value}`")
    if hotset_selection:
        lines.extend(["", "## Hotset", ""])
        for key, value in hotset_selection.to_dict().items():
            if key == "source_counts":
                continue
            lines.append(f"- {key}: `{value}`")
        lines.extend(["", "## Source Counts", ""])
        for label, counts in hotset_selection.source_counts.items():
            lines.append(
                f"- {label}: raw `{counts.get('raw', 0)}`, "
                f"added `{counts.get('added', 0)}`"
            )
    lines.extend(["", "## Results", ""])
    for row in result_rows:
        lines.append(
            "- history_id `{history_id}` task `{task_id}` media `{media_type}` "
            "media_status `{media_status}` thumb_status `{thumbnail_status}` "
            "media_key `{media_r2_key}` thumb_key `{thumbnail_r2_key}` "
            "input_files `{input_count}`".format(
                input_count=len(row["input_files"]),
                **row
            )
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


async def process_history_r2_candidates(
    candidates: list[HistoryR2Candidate],
    *,
    concurrency: int,
    apply_changes: bool,
    media_only: bool,
    include_input_files: bool,
    generate_missing_thumbnails: bool,
    async_object_exists_func,
    async_r2_object_exists_func,
    async_copy_to_r2_func,
    generate_and_upload_thumbnail_func,
    generate_and_upload_thumbnail_from_r2_media_func,
) -> list[CandidateResult]:
    safe_concurrency = max(1, concurrency)
    queue: asyncio.Queue[HistoryR2Candidate] = asyncio.Queue()
    for candidate in candidates:
        queue.put_nowait(candidate)

    results: list[CandidateResult] = []
    results_lock = asyncio.Lock()
    total = len(candidates)
    processed = 0

    async def worker() -> None:
        nonlocal processed
        while True:
            try:
                candidate = queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            try:
                result = await process_history_r2_candidate(
                    candidate,
                    apply_changes=apply_changes,
                    media_only=media_only,
                    generate_missing_thumbnails=generate_missing_thumbnails,
                    async_object_exists_func=async_object_exists_func,
                    async_r2_object_exists_func=async_r2_object_exists_func,
                    async_copy_to_r2_func=async_copy_to_r2_func,
                    generate_and_upload_thumbnail_func=(
                        generate_and_upload_thumbnail_func
                    ),
                    generate_and_upload_thumbnail_from_r2_media_func=(
                        generate_and_upload_thumbnail_from_r2_media_func
                    ),
                    include_input_files=include_input_files,
                )
                async with results_lock:
                    results.append(result)
                    processed += 1
                    current = processed
                logger.info(
                    "[%s/%s] history_id=%s task_id=%s user=%s media=%s "
                    "media_status=%s thumb_status=%s r2_media=%s r2_thumb=%s",
                    current,
                    total,
                    candidate.history_id,
                    candidate.task_id,
                    candidate.username or candidate.user_id,
                    candidate.media_type,
                    result.media_status,
                    result.thumbnail_status,
                    candidate.media_r2_key,
                    candidate.thumbnail_r2_key,
                )
            finally:
                queue.task_done()

    await asyncio.gather(*(worker() for _ in range(safe_concurrency)))
    return results


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="扫描 History 表并把缺失的历史原文件/缩略图回填到 R2。默认 dry-run。"
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="在导入项目配置前加载指定 env 文件；不会打印其中的敏感值。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正执行上传；默认只扫描并输出计划。",
    )
    parser.add_argument(
        "--favorited-only",
        action="store_true",
        help="仅扫描已收藏的历史记录，适合先验证收藏视频问题。",
    )
    parser.add_argument(
        "--visible-scope",
        choices=["all", "user-visible"],
        default="all",
        help=(
            "扫描范围。user-visible 仅覆盖最近 8 条闪回瓶、投稿、收藏、"
            "广场 like/apply 和提示词解锁可见历史。"
        ),
    )
    parser.add_argument(
        "--recent-limit",
        type=int,
        default=8,
        help="visible-scope=user-visible 时每个用户纳入的最近原始历史条数。",
    )
    parser.add_argument(
        "--skip-per-user-recent-history",
        action="store_true",
        help=(
            "web-visible-retire-legacy 热集不采集每用户最近 N 条历史，"
            "仅保留 Gallery/收藏/互动/提示词解锁相关历史。"
        ),
    )
    parser.add_argument(
        "--source-storage",
        choices=["current", "legacy"],
        default=None,
        help=(
            "对象复制源。云正式热集模式默认 legacy；非热集模式默认 current。"
        ),
    )
    parser.add_argument(
        "--hotset-profile",
        choices=HOTSET_PROFILES,
        help=(
            "启用固定热集候选采集模式；cloud-prod-lag-fix 用于云正式非全量预热，"
            "web-visible-retire-legacy 用于 legacy 退出前的 Web 可见热集。"
        ),
    )
    parser.add_argument(
        "--hotset-wave",
        choices=["first", "second"],
        default="first",
        help="热集批次范围。first 最多 5000 个候选，second 最多 12000 个候选。",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="热集模式单批处理条数；最大会被限制为 500。",
    )
    parser.add_argument(
        "--cursor-file",
        type=Path,
        help="热集模式游标文件；默认写入 logs/media_hotset_<profile>_<wave>_cursor.json。",
    )
    parser.add_argument(
        "--no-cursor",
        action="store_true",
        help="热集模式不读取/更新游标；仅建议一次性验证时使用。",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("logs"),
        help="热集模式报告输出目录，默认 logs。",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="不写入热集扫描报告。",
    )
    parser.add_argument(
        "--username",
        type=str,
        help='按用户名精确筛选，例如 --username "A A"',
    )
    parser.add_argument("--user-id", type=int, help="按 internal user id 筛选。")
    parser.add_argument("--task-id", type=str, help="仅扫描指定 task_id。")
    parser.add_argument(
        "--source",
        type=str,
        choices=["web", "bot"],
        help="按 history.source 过滤。",
    )
    parser.add_argument(
        "--media-type",
        type=str,
        choices=["all", "video", "image"],
        default="all",
        help="按历史媒体类型过滤，默认 all。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制扫描条数，建议先小批量验证。",
    )
    parser.add_argument(
        "--media-only",
        action="store_true",
        help="仅处理原文件 media R2 回填，不处理缩略图。",
    )
    parser.add_argument(
        "--include-input-files",
        action="store_true",
        help="同时复制 History.input_file 中的本地存储对象，外部 URL 会跳过。",
    )
    parser.add_argument(
        "--generate-missing-thumbnails",
        action="store_true",
        help="当源缩略图不存在但原文件存在时生成缩略图；legacy 批量预热默认不启用。",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help=(
            "并发处理数量。热集模式默认 media/copy 为 3，"
            "generate-missing-thumbnails 为 1；非热集默认 1。"
        ),
    )
    return parser


async def run_backfill(args) -> BackfillSummary:
    if not storage.client:
        raise RuntimeError("MinIO client 未初始化，无法执行回填。")
    if not storage.r2_client or not storage.r2_bucket:
        raise RuntimeError("R2 client 未初始化，无法执行回填。")
    storage._ensure_r2_async_primitives()

    source_storage: Literal["current", "legacy"] = (
        args.source_storage
        or ("legacy" if args.hotset_profile else "current")
    )
    if args.concurrency is not None:
        effective_concurrency = args.concurrency
    elif args.hotset_profile:
        effective_concurrency = 1 if args.generate_missing_thumbnails else 3
    else:
        effective_concurrency = 1

    resolve_source_object_func: ResolveSourceObjectFunc = resolve_storage_object
    async_object_exists_func = storage.async_object_exists
    async_copy_to_r2_func = storage.async_copy_to_r2

    if source_storage == "legacy":
        if args.generate_missing_thumbnails:
            raise RuntimeError(
                "legacy 源批量预热暂不支持生成缺失缩略图；请先复制已有缩略图，"
                "再单独安排缩略图生成批次。"
            )
        has_legacy_storage = getattr(storage, "has_legacy_storage_configured", None)
        if not callable(has_legacy_storage) or not has_legacy_storage():
            raise RuntimeError("LEGACY_MINIO_* 未配置，无法从 legacy MinIO 预热。")
        resolve_source_object_func = resolve_legacy_storage_object
        async_object_exists_func = storage.async_legacy_object_exists
        async_copy_to_r2_func = storage.async_copy_legacy_to_r2

    hotset_selection: HotsetSelection | None = None
    cursor_file: Path | None = None
    processed_history_ids: set[int] = set()
    async with AsyncSessionLocal() as session:
        history_ids = None
        if args.hotset_profile:
            if args.hotset_profile == HOTSET_PROFILE_CLOUD_PROD_LAG_FIX:
                selected_ids, source_counts = await collect_cloud_prod_lag_fix_history_ids(
                    session,
                    wave=args.hotset_wave,
                    total_limit=args.limit,
                )
                candidate_cap = min(
                    HOTSET_WAVE_CAPS[args.hotset_wave],
                    args.limit or HOTSET_WAVE_CAPS[args.hotset_wave],
                )
                default_cursor_name = (
                    f"media_hotset_{args.hotset_profile}_{args.hotset_wave}_cursor.json"
                )
            elif args.hotset_profile == HOTSET_PROFILE_WEB_VISIBLE_RETIRE_LEGACY:
                selected_ids, source_counts = (
                    await collect_web_visible_retire_legacy_history_ids(
                        session,
                        recent_limit=args.recent_limit,
                        include_per_user_recent=(
                            not args.skip_per_user_recent_history
                        ),
                        total_limit=args.limit,
                    )
                )
                candidate_cap = args.limit or len(selected_ids)
                default_cursor_name = f"media_hotset_{args.hotset_profile}_cursor.json"
            else:
                raise RuntimeError(f"Unsupported hotset profile: {args.hotset_profile}")
            batch_size = min(
                max(1, args.batch_size or HOTSET_MAX_BATCH_SIZE),
                HOTSET_MAX_BATCH_SIZE,
            )
            if not args.no_cursor:
                cursor_file = args.cursor_file or Path(
                    "logs",
                    default_cursor_name,
                )
                processed_history_ids = read_hotset_cursor(cursor_file)
            history_ids, skipped_by_cursor = select_hotset_batch(
                selected_ids,
                batch_size=batch_size,
                processed_history_ids=processed_history_ids,
            )
            hotset_selection = HotsetSelection(
                profile=args.hotset_profile,
                wave=args.hotset_wave,
                candidate_cap=candidate_cap,
                selected_count=len(selected_ids),
                batch_count=len(history_ids),
                skipped_by_cursor=skipped_by_cursor,
                source_counts=source_counts,
            )

        candidates = await collect_history_r2_candidates(
            session,
            history_ids=history_ids,
            username=args.username,
            user_id=args.user_id,
            task_id=args.task_id,
            favorited_only=args.favorited_only,
            source=args.source,
            media_type=args.media_type,
            visible_scope=args.visible_scope,
            recent_limit=args.recent_limit,
            limit=None if history_ids is not None else args.limit,
            resolve_source_object_func=resolve_source_object_func,
        )

    logger.info(
        "Collected %s history rows for R2 scan. visible_scope=%s source_storage=%s hotset=%s",
        len(candidates),
        args.visible_scope,
        source_storage,
        args.hotset_profile or "",
    )
    results = await process_history_r2_candidates(
        candidates,
        concurrency=effective_concurrency,
        apply_changes=args.apply,
        media_only=args.media_only,
        include_input_files=args.include_input_files,
        generate_missing_thumbnails=args.generate_missing_thumbnails,
        async_object_exists_func=async_object_exists_func,
        async_r2_object_exists_func=storage._async_r2_object_exists_uncached,
        async_copy_to_r2_func=async_copy_to_r2_func,
        generate_and_upload_thumbnail_func=generate_and_upload_thumbnail,
        generate_and_upload_thumbnail_from_r2_media_func=(
            generate_and_upload_thumbnail_from_r2_media
        ),
    )

    summary = summarize_results(results, apply_changes=args.apply)
    logger.info("Backfill summary: %s", json.dumps(summary.to_dict(), ensure_ascii=False))
    if args.apply and cursor_file and hotset_selection:
        processed_history_ids.update(
            result.candidate.history_id
            for result in results
            if should_mark_hotset_processed(result)
        )
        write_hotset_cursor(
            cursor_file,
            profile=hotset_selection.profile,
            wave=hotset_selection.wave,
            processed_history_ids=processed_history_ids,
        )
        logger.info("Updated hotset cursor: %s", cursor_file)
    if hotset_selection and not args.no_report:
        json_path, md_path = write_backfill_report(
            report_dir=args.report_dir,
            summary=summary,
            results=results,
            source_storage=source_storage,
            media_only=args.media_only,
            include_input_files=args.include_input_files,
            generate_missing_thumbnails=args.generate_missing_thumbnails,
            concurrency=effective_concurrency,
            hotset_selection=hotset_selection,
        )
        logger.info("Wrote hotset reports: %s %s", json_path, md_path)
    return summary


async def main_async():
    parser = build_argument_parser()
    args = parser.parse_args()
    summary = await run_backfill(args)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
