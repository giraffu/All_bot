import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.media_paths import (  # noqa: E402
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_legacy_r2_key,
    get_media_type_from_history,
    resolve_storage_object,
)
from src.core.media_processor import generate_and_upload_thumbnail  # noqa: E402
from src.core.media_urls import build_thumbnail_file_path  # noqa: E402
from src.database.core import AsyncSessionLocal  # noqa: E402
from src.database.models import History, User  # noqa: E402
from src.services.storage import storage  # noqa: E402

logger = logging.getLogger(__name__)

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
) -> HistoryR2Candidate:
    media_type = get_media_type_from_history(history_type)
    source_bucket, source_object = resolve_storage_object(output_file)
    thumbnail_file = build_thumbnail_file_path(output_file, media_type)
    thumbnail_source_bucket, thumbnail_source_object = resolve_storage_object(
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


async def collect_history_r2_candidates(
    session,
    *,
    username: str | None = None,
    user_id: int | None = None,
    task_id: str | None = None,
    favorited_only: bool = False,
    source: str | None = None,
    media_type: Literal["all", "video", "image"] = "all",
    limit: int | None = None,
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
    async_object_exists_func,
    async_r2_object_exists_func,
    async_copy_to_r2_func,
    generate_and_upload_thumbnail_func,
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
    return parser


async def run_backfill(args) -> BackfillSummary:
    if not storage.client:
        raise RuntimeError("MinIO client 未初始化，无法执行回填。")
    if not storage.r2_client or not storage.r2_bucket:
        raise RuntimeError("R2 client 未初始化，无法执行回填。")
    storage._ensure_r2_async_primitives()

    async with AsyncSessionLocal() as session:
        candidates = await collect_history_r2_candidates(
            session,
            username=args.username,
            user_id=args.user_id,
            task_id=args.task_id,
            favorited_only=args.favorited_only,
            source=args.source,
            media_type=args.media_type,
            limit=args.limit,
        )

    logger.info("Collected %s history rows for R2 scan.", len(candidates))
    results: list[CandidateResult] = []
    for idx, candidate in enumerate(candidates, 1):
        logger.info(
            "[%s/%s] Scan history_id=%s task_id=%s user=%s media=%s",
            idx,
            len(candidates),
            candidate.history_id,
            candidate.task_id,
            candidate.username or candidate.user_id,
            candidate.media_type,
        )
        result = await process_history_r2_candidate(
            candidate,
            apply_changes=args.apply,
            media_only=args.media_only,
            async_object_exists_func=storage.async_object_exists,
            async_r2_object_exists_func=storage._async_r2_object_exists_uncached,
            async_copy_to_r2_func=storage.async_copy_to_r2,
            generate_and_upload_thumbnail_func=generate_and_upload_thumbnail,
        )
        results.append(result)
        logger.info(
            "   media=%s thumb=%s r2_media=%s r2_thumb=%s",
            result.media_status,
            result.thumbnail_status,
            candidate.media_r2_key,
            candidate.thumbnail_r2_key,
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
