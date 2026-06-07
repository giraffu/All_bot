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
from io import BytesIO
from pathlib import Path
from typing import Callable, Literal

from PIL import Image, ImageOps
from sqlalchemy import desc, func, select, union


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.media_paths import (  # noqa: E402
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_legacy_r2_key,
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


@dataclass
class CandidateResult:
    candidate: HistoryR2Candidate
    media_status: MediaStatus
    thumbnail_status: ThumbnailStatus


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
    )


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


async def collect_history_r2_candidates(
    session,
    *,
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
            resolve_source_object_func=resolve_source_object_func,
        )
        for (
            history_id,
            row_user_id,
            row_username,
            row_task_id,
            row_history_type,
            row_output_file,
        ) in rows
    ]

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
) -> CandidateResult:
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
        uploaded = await async_copy_to_r2_func(
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
                    uploaded = await async_copy_to_r2_func(
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

    return CandidateResult(
        candidate=candidate,
        media_status=media_status,
        thumbnail_status=thumbnail_status,
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
    )


async def process_history_r2_candidates(
    candidates: list[HistoryR2Candidate],
    *,
    concurrency: int,
    apply_changes: bool,
    media_only: bool,
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
        "--source-storage",
        choices=["current", "legacy"],
        default="current",
        help="对象复制源。云正式预热旧数据时使用 legacy。",
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
        "--generate-missing-thumbnails",
        action="store_true",
        help="当源缩略图不存在但原文件存在时生成缩略图；legacy 批量预热默认不启用。",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="并发处理数量；大批预热建议从 4-8 开始。",
    )
    return parser


async def run_backfill(args) -> BackfillSummary:
    if not storage.client:
        raise RuntimeError("MinIO client 未初始化，无法执行回填。")
    if not storage.r2_client or not storage.r2_bucket:
        raise RuntimeError("R2 client 未初始化，无法执行回填。")
    storage._ensure_r2_async_primitives()

    resolve_source_object_func: ResolveSourceObjectFunc = resolve_storage_object
    async_object_exists_func = storage.async_object_exists
    async_copy_to_r2_func = storage.async_copy_to_r2

    if args.source_storage == "legacy":
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

    async with AsyncSessionLocal() as session:
        candidates = await collect_history_r2_candidates(
            session,
            username=args.username,
            user_id=args.user_id,
            task_id=args.task_id,
            favorited_only=args.favorited_only,
            source=args.source,
            media_type=args.media_type,
            visible_scope=args.visible_scope,
            recent_limit=args.recent_limit,
            limit=args.limit,
            resolve_source_object_func=resolve_source_object_func,
        )

    logger.info(
        "Collected %s history rows for R2 scan. visible_scope=%s source_storage=%s",
        len(candidates),
        args.visible_scope,
        args.source_storage,
    )
    results = await process_history_r2_candidates(
        candidates,
        concurrency=args.concurrency,
        apply_changes=args.apply,
        media_only=args.media_only,
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
