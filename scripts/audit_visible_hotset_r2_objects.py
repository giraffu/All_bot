import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import desc, func, select


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


_load_env_file_from_argv(sys.argv)

from scripts.backfill_history_r2_objects import (  # noqa: E402
    InputFileCandidate,
    build_history_r2_candidate,
    collect_web_visible_retire_legacy_history_ids,
)
from src.core.media_urls import (  # noqa: E402
    build_r2_media_key_candidates,
    build_r2_thumbnail_info,
)
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

SOURCE_LABELS = [
    "per_user_recent_visible_history",
    "all_gallery_posts",
    "history_favorites",
    "gallery_like_apply_interactions",
    "gallery_prompt_unlocks",
]

R2ProbeStatus = Literal["exists", "missing", "error"]
AuditScope = Literal["runtime", "standard", "input"]


@dataclass(frozen=True)
class R2ProbeResult:
    key: str
    status: R2ProbeStatus
    error_code: str | None = None


@dataclass
class InputAuditResult:
    file_path: str
    r2_key: str | None
    status: R2ProbeStatus | Literal["skipped_external", "skipped"]
    error_code: str | None = None
    skip_reason: str | None = None


@dataclass
class HistoryAuditResult:
    history_id: int
    user_id: int | None
    username: str | None
    task_id: str | None
    history_type: str | None
    history_source: str | None
    media_type: str
    output_file: str
    created_at: str | None
    is_favorited: bool | None
    source_labels: list[str]
    media_standard_key: str
    media_standard_status: R2ProbeStatus
    media_runtime_status: R2ProbeStatus
    media_runtime_found_key: str | None
    media_candidate_keys: list[str]
    thumbnail_standard_key: str
    thumbnail_standard_status: R2ProbeStatus
    thumbnail_runtime_status: R2ProbeStatus
    thumbnail_runtime_found_key: str | None
    thumbnail_candidate_keys: list[str]
    media_error_codes: list[str] = field(default_factory=list)
    thumbnail_error_codes: list[str] = field(default_factory=list)
    input_results: list[InputAuditResult] = field(default_factory=list)


@dataclass
class MissingRecord:
    history_id: int
    user_id: int | None
    username: str | None
    task_id: str | None
    history_type: str | None
    history_source: str | None
    media_type: str
    output_file: str
    created_at: str | None
    source_labels: list[str]
    object_kind: str
    audit_scope: AuditScope
    r2_key: str | None
    runtime_found_key: str | None
    candidate_keys: list[str]
    status: str
    error_code: str | None = None


class R2HeadAuditor:
    def __init__(self, *, concurrency: int):
        self._client = getattr(storage, "r2_head_client", None) or getattr(
            storage, "r2_client", None
        )
        self._bucket = getattr(storage, "r2_bucket", None)
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._cache: dict[str, asyncio.Task[R2ProbeResult]] = {}
        self._cache_lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._client and self._bucket)

    async def probe(self, key: str | None) -> R2ProbeResult:
        if not key:
            return R2ProbeResult(key="", status="missing")
        async with self._cache_lock:
            task = self._cache.get(key)
            if task is None:
                task = asyncio.create_task(self._probe_uncached(key))
                self._cache[key] = task
        return await task

    async def _probe_uncached(self, key: str) -> R2ProbeResult:
        async with self._semaphore:
            return await asyncio.to_thread(self._probe_sync, key)

    def _probe_sync(self, key: str) -> R2ProbeResult:
        if not self._client or not self._bucket:
            return R2ProbeResult(
                key=key,
                status="error",
                error_code="r2_not_configured",
            )
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return R2ProbeResult(key=key, status="exists")
        except ClientError as exc:
            error = exc.response.get("Error", {}) if exc.response else {}
            code = str(error.get("Code", "ClientError"))
            status_code = (
                exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if exc.response
                else None
            )
            if code in {"404", "NoSuchKey", "NotFound"} or status_code == 404:
                return R2ProbeResult(key=key, status="missing")
            return R2ProbeResult(key=key, status="error", error_code=code)
        except BotoCoreError as exc:
            return R2ProbeResult(
                key=key,
                status="error",
                error_code=type(exc).__name__,
            )
        except Exception as exc:
            return R2ProbeResult(
                key=key,
                status="error",
                error_code=type(exc).__name__,
            )


def _isoformat(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [item for item in items if item and not (item in seen or seen.add(item))]


def _chunked(items: list[int], size: int) -> list[list[int]]:
    chunk_size = max(1, size)
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


async def collect_visible_hotset_source_memberships(
    session,
    *,
    recent_limit: int,
    include_per_user_recent: bool,
    selected_history_ids: set[int],
) -> dict[int, list[str]]:
    common_history_filters = (
        History.output_file.is_not(None),
        History.output_file != "",
        History.is_visible.is_not(False),
    )
    source_statements = []

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
        source_statements.append(
            (
                "per_user_recent_visible_history",
                select(recent_ranked.c.history_id).where(
                    recent_ranked.c.row_number <= recent_limit
                ),
            )
        )
    else:
        source_statements.append(
            ("per_user_recent_visible_history", select(History.id).where(False))
        )

    source_statements.extend(
        [
            (
                "all_gallery_posts",
                select(History.id)
                .join(GalleryPost, GalleryPost.task_id == History.task_id)
                .where(*common_history_filters),
            ),
            (
                "history_favorites",
                select(History.id).where(
                    *common_history_filters,
                    History.is_favorited.is_(True),
                ),
            ),
            (
                "gallery_like_apply_interactions",
                select(History.id)
                .join(GalleryPost, GalleryPost.task_id == History.task_id)
                .join(UserInteraction, UserInteraction.post_id == GalleryPost.id)
                .where(
                    *common_history_filters,
                    GalleryPost.is_active.is_(True),
                    UserInteraction.action_type.in_(["like", "apply"]),
                ),
            ),
            (
                "gallery_prompt_unlocks",
                select(History.id)
                .join(GalleryPost, GalleryPost.task_id == History.task_id)
                .join(GalleryPromptUnlock, GalleryPromptUnlock.post_id == GalleryPost.id)
                .where(*common_history_filters, GalleryPost.is_active.is_(True)),
            ),
        ]
    )

    memberships: dict[int, list[str]] = defaultdict(list)
    for label, stmt in source_statements:
        rows = (await session.execute(stmt)).scalars().all()
        for history_id in rows:
            if history_id in selected_history_ids:
                memberships[int(history_id)].append(label)
    return dict(memberships)


async def collect_audit_candidates(
    session,
    *,
    history_ids: list[int],
    source_memberships: dict[int, list[str]],
    db_batch_size: int,
) -> list[dict]:
    if not history_ids:
        return []
    rows_by_id = {}
    for batch_ids in _chunked(history_ids, db_batch_size):
        stmt = (
            select(
                History.id,
                History.user_id,
                User.username,
                History.task_id,
                History.type,
                History.source,
                History.output_file,
                History.input_file,
                History.created_at,
                History.is_favorited,
            )
            .select_from(History)
            .outerjoin(User, User.id == History.user_id)
            .where(History.id.in_(batch_ids))
        )
        rows = (await session.execute(stmt)).all()
        rows_by_id.update({int(row.id): row for row in rows})

    candidates: list[dict] = []
    for history_id in history_ids:
        row = rows_by_id.get(int(history_id))
        if not row or not row.output_file:
            continue
        r2_candidate = build_history_r2_candidate(
            history_id=int(row.id),
            user_id=row.user_id,
            username=row.username,
            task_id=row.task_id,
            history_type=row.type,
            output_file=row.output_file,
            input_file=row.input_file,
        )
        _, thumbnail_candidate_keys = build_r2_thumbnail_info(
            output_file=row.output_file,
            media_type=r2_candidate.media_type,
            task_id=row.task_id,
        )
        candidates.append(
            {
                "history_id": int(row.id),
                "user_id": row.user_id,
                "username": row.username,
                "task_id": row.task_id,
                "history_type": row.type,
                "history_source": row.source,
                "output_file": row.output_file,
                "created_at": _isoformat(row.created_at),
                "is_favorited": bool(row.is_favorited),
                "media_type": r2_candidate.media_type,
                "source_labels": source_memberships.get(int(row.id), []),
                "media_standard_key": r2_candidate.media_r2_key,
                "media_candidate_keys": build_r2_media_key_candidates(
                    output_file=row.output_file,
                    task_id=row.task_id,
                ),
                "thumbnail_standard_key": r2_candidate.thumbnail_r2_key,
                "thumbnail_candidate_keys": thumbnail_candidate_keys,
                "input_files": r2_candidate.input_files,
            }
        )
    return candidates


async def probe_runtime_keys(
    keys: list[str],
    *,
    auditor: R2HeadAuditor,
) -> tuple[R2ProbeStatus, str | None, list[R2ProbeResult]]:
    checked: list[R2ProbeResult] = []
    for key in _dedupe(keys):
        result = await auditor.probe(key)
        checked.append(result)
        if result.status == "exists":
            return "exists", key, checked
    if any(result.status == "error" for result in checked):
        return "error", None, checked
    return "missing", None, checked


async def audit_candidate(
    candidate: dict,
    *,
    auditor: R2HeadAuditor,
    include_input_files: bool,
) -> HistoryAuditResult:
    media_runtime_status, media_found_key, media_checked = await probe_runtime_keys(
        candidate["media_candidate_keys"],
        auditor=auditor,
    )
    media_standard = next(
        (
            item
            for item in media_checked
            if item.key == candidate["media_standard_key"]
        ),
        None,
    )
    if media_standard is None:
        media_standard = await auditor.probe(candidate["media_standard_key"])

    thumbnail_runtime_status, thumbnail_found_key, thumbnail_checked = (
        await probe_runtime_keys(candidate["thumbnail_candidate_keys"], auditor=auditor)
    )
    thumbnail_standard = next(
        (
            item
            for item in thumbnail_checked
            if item.key == candidate["thumbnail_standard_key"]
        ),
        None,
    )
    if thumbnail_standard is None:
        thumbnail_standard = await auditor.probe(candidate["thumbnail_standard_key"])

    input_results: list[InputAuditResult] = []
    if include_input_files:
        for input_file in candidate["input_files"]:
            input_results.append(await audit_input_file(input_file, auditor=auditor))

    return HistoryAuditResult(
        history_id=candidate["history_id"],
        user_id=candidate["user_id"],
        username=candidate["username"],
        task_id=candidate["task_id"],
        history_type=candidate["history_type"],
        history_source=candidate["history_source"],
        media_type=candidate["media_type"],
        output_file=candidate["output_file"],
        created_at=candidate["created_at"],
        is_favorited=candidate["is_favorited"],
        source_labels=candidate["source_labels"],
        media_standard_key=candidate["media_standard_key"],
        media_standard_status=media_standard.status,
        media_runtime_status=media_runtime_status,
        media_runtime_found_key=media_found_key,
        media_candidate_keys=candidate["media_candidate_keys"],
        media_error_codes=[
            result.error_code
            for result in media_checked
            if result.status == "error" and result.error_code
        ],
        thumbnail_standard_key=candidate["thumbnail_standard_key"],
        thumbnail_standard_status=thumbnail_standard.status,
        thumbnail_runtime_status=thumbnail_runtime_status,
        thumbnail_runtime_found_key=thumbnail_found_key,
        thumbnail_candidate_keys=candidate["thumbnail_candidate_keys"],
        thumbnail_error_codes=[
            result.error_code
            for result in thumbnail_checked
            if result.status == "error" and result.error_code
        ],
        input_results=input_results,
    )


async def audit_input_file(
    input_file: InputFileCandidate,
    *,
    auditor: R2HeadAuditor,
) -> InputAuditResult:
    if input_file.skip_reason == "external":
        return InputAuditResult(
            file_path=input_file.file_path,
            r2_key=None,
            status="skipped_external",
            skip_reason="external",
        )
    if not input_file.r2_key:
        return InputAuditResult(
            file_path=input_file.file_path,
            r2_key=None,
            status="skipped",
            skip_reason=input_file.skip_reason,
        )
    result = await auditor.probe(input_file.r2_key)
    return InputAuditResult(
        file_path=input_file.file_path,
        r2_key=input_file.r2_key,
        status=result.status,
        error_code=result.error_code,
    )


async def audit_candidates(
    candidates: list[dict],
    *,
    auditor: R2HeadAuditor,
    include_input_files: bool,
    concurrency: int,
    progress_interval: int,
) -> list[HistoryAuditResult]:
    queue: asyncio.Queue[dict] = asyncio.Queue()
    for candidate in candidates:
        queue.put_nowait(candidate)

    results: list[HistoryAuditResult] = []
    results_lock = asyncio.Lock()
    completed = 0
    total = len(candidates)

    async def worker() -> None:
        nonlocal completed
        while True:
            try:
                candidate = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                result = await audit_candidate(
                    candidate,
                    auditor=auditor,
                    include_input_files=include_input_files,
                )
                async with results_lock:
                    results.append(result)
                    completed += 1
                    if progress_interval > 0 and (
                        completed == total or completed % progress_interval == 0
                    ):
                        logger.info(
                            "Audited %s/%s visible hotset histories",
                            completed,
                            total,
                        )
            finally:
                queue.task_done()

    await asyncio.gather(*(worker() for _ in range(max(1, concurrency))))
    order = {candidate["history_id"]: index for index, candidate in enumerate(candidates)}
    results.sort(key=lambda result: order.get(result.history_id, len(order)))
    return results


def build_missing_records(results: list[HistoryAuditResult]) -> list[MissingRecord]:
    records: list[MissingRecord] = []

    def add_record(
        result: HistoryAuditResult,
        *,
        object_kind: str,
        audit_scope: AuditScope,
        r2_key: str | None,
        runtime_found_key: str | None,
        candidate_keys: list[str],
        status: str,
        error_code: str | None = None,
    ) -> None:
        records.append(
            MissingRecord(
                history_id=result.history_id,
                user_id=result.user_id,
                username=result.username,
                task_id=result.task_id,
                history_type=result.history_type,
                history_source=result.history_source,
                media_type=result.media_type,
                output_file=result.output_file,
                created_at=result.created_at,
                source_labels=result.source_labels,
                object_kind=object_kind,
                audit_scope=audit_scope,
                r2_key=r2_key,
                runtime_found_key=runtime_found_key,
                candidate_keys=candidate_keys,
                status=status,
                error_code=error_code,
            )
        )

    for result in results:
        if result.media_runtime_status != "exists":
            add_record(
                result,
                object_kind="media",
                audit_scope="runtime",
                r2_key=result.media_standard_key,
                runtime_found_key=result.media_runtime_found_key,
                candidate_keys=result.media_candidate_keys,
                status=result.media_runtime_status,
                error_code=";".join(result.media_error_codes) or None,
            )
        elif result.media_standard_status != "exists":
            add_record(
                result,
                object_kind="media",
                audit_scope="standard",
                r2_key=result.media_standard_key,
                runtime_found_key=result.media_runtime_found_key,
                candidate_keys=result.media_candidate_keys,
                status=result.media_standard_status,
                error_code=";".join(result.media_error_codes) or None,
            )

        if result.thumbnail_runtime_status != "exists":
            add_record(
                result,
                object_kind="thumbnail",
                audit_scope="runtime",
                r2_key=result.thumbnail_standard_key,
                runtime_found_key=result.thumbnail_runtime_found_key,
                candidate_keys=result.thumbnail_candidate_keys,
                status=result.thumbnail_runtime_status,
                error_code=";".join(result.thumbnail_error_codes) or None,
            )
        elif result.thumbnail_standard_status != "exists":
            add_record(
                result,
                object_kind="thumbnail",
                audit_scope="standard",
                r2_key=result.thumbnail_standard_key,
                runtime_found_key=result.thumbnail_runtime_found_key,
                candidate_keys=result.thumbnail_candidate_keys,
                status=result.thumbnail_standard_status,
                error_code=";".join(result.thumbnail_error_codes) or None,
            )

        for input_result in result.input_results:
            if input_result.status in {"missing", "error"}:
                add_record(
                    result,
                    object_kind="input_file",
                    audit_scope="input",
                    r2_key=input_result.r2_key,
                    runtime_found_key=None,
                    candidate_keys=[input_result.r2_key] if input_result.r2_key else [],
                    status=input_result.status,
                    error_code=input_result.error_code,
                )

    return records


def summarize_audit_results(
    results: list[HistoryAuditResult],
    *,
    selected_count: int,
    source_counts: dict[str, dict[str, int]],
    include_input_files: bool,
) -> dict:
    missing_records = build_missing_records(results)
    by_media_type: dict[str, Counter] = defaultdict(Counter)
    by_history_source: dict[str, Counter] = defaultdict(Counter)
    by_source_label: dict[str, Counter] = defaultdict(Counter)
    object_counts: Counter = Counter()
    status_counts: Counter = Counter()

    for result in results:
        labels = result.source_labels or ["unclassified"]
        groups = [
            by_media_type[result.media_type],
            by_history_source[result.history_source or "unknown"],
        ]
        for label in labels:
            groups.append(by_source_label[label])
        for group in groups:
            group["histories"] += 1
            if result.media_runtime_status != "exists":
                group["media_runtime_missing"] += 1
            if result.thumbnail_runtime_status != "exists":
                group["thumbnail_runtime_missing"] += 1
            if result.media_standard_status != "exists":
                group["media_standard_missing"] += 1
            if result.thumbnail_standard_status != "exists":
                group["thumbnail_standard_missing"] += 1
            if any(item.status == "missing" for item in result.input_results):
                group["input_missing_histories"] += 1
            if (
                result.media_runtime_status != "exists"
                or result.thumbnail_runtime_status != "exists"
                or any(item.status == "missing" for item in result.input_results)
            ):
                group["any_runtime_or_input_missing"] += 1

        object_counts[f"media_runtime_{result.media_runtime_status}"] += 1
        object_counts[f"media_standard_{result.media_standard_status}"] += 1
        object_counts[f"thumbnail_runtime_{result.thumbnail_runtime_status}"] += 1
        object_counts[f"thumbnail_standard_{result.thumbnail_standard_status}"] += 1
        for input_result in result.input_results:
            object_counts[f"input_{input_result.status}"] += 1

    for record in missing_records:
        status_counts[f"{record.object_kind}_{record.audit_scope}_{record.status}"] += 1

    return {
        "selected_count": selected_count,
        "scanned_histories": len(results),
        "include_input_files": include_input_files,
        "source_counts": source_counts,
        "object_counts": dict(sorted(object_counts.items())),
        "missing_record_counts": dict(sorted(status_counts.items())),
        "by_media_type": {
            key: dict(value) for key, value in sorted(by_media_type.items())
        },
        "by_history_source": {
            key: dict(value) for key, value in sorted(by_history_source.items())
        },
        "by_source_label": {
            key: dict(value) for key, value in sorted(by_source_label.items())
        },
        "appendix_missing_records": len(missing_records),
    }


def write_reports(
    *,
    report_dir: Path,
    summary: dict,
    missing_records: list[MissingRecord],
    args: argparse.Namespace,
) -> tuple[Path, Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"r2_visible_hotset_audit_{timestamp}"
    json_path = report_dir / f"{base_name}.json"
    md_path = report_dir / f"{base_name}.md"
    appendix_path = report_dir / f"{base_name}_missing_appendix.csv"

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "profile": "web-visible-r2-audit",
            "recent_limit": args.recent_limit,
            "include_per_user_recent": not args.skip_per_user_recent_history,
            "include_input_files": not args.skip_input_files,
            "limit": args.limit,
            "db_batch_size": args.db_batch_size,
            "r2_candidate_mode": "runtime_and_standard",
        },
        "summary": summary,
        "missing_records": [asdict(record) for record in missing_records],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with appendix_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "history_id",
            "user_id",
            "username",
            "task_id",
            "history_type",
            "history_source",
            "media_type",
            "output_file",
            "created_at",
            "source_labels",
            "object_kind",
            "audit_scope",
            "status",
            "r2_key",
            "runtime_found_key",
            "candidate_keys",
            "error_code",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for record in missing_records:
            row = asdict(record)
            row["source_labels"] = "|".join(record.source_labels)
            row["candidate_keys"] = "|".join(record.candidate_keys)
            writer.writerow({field: row.get(field) for field in fieldnames})

    md_lines = [
        "# R2 Visible Hotset Audit",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        "- profile: `web-visible-r2-audit`",
        f"- include_per_user_recent: `{not args.skip_per_user_recent_history}`",
        f"- recent_limit: `{args.recent_limit}`",
        f"- include_input_files: `{not args.skip_input_files}`",
        f"- selected_count: `{summary['selected_count']}`",
        f"- scanned_histories: `{summary['scanned_histories']}`",
        f"- appendix_missing_records: `{summary['appendix_missing_records']}`",
        f"- json_report: `{json_path.name}`",
        f"- missing_appendix_csv: `{appendix_path.name}`",
        "",
        "## Object Counts",
        "",
    ]
    for key, value in summary["object_counts"].items():
        md_lines.append(f"- `{key}`: `{value}`")
    md_lines.extend(["", "## Missing Record Counts", ""])
    for key, value in summary["missing_record_counts"].items():
        md_lines.append(f"- `{key}`: `{value}`")
    md_lines.extend(["", "## By Media Type", ""])
    for key, value in summary["by_media_type"].items():
        md_lines.append(f"- `{key}`: `{json.dumps(value, ensure_ascii=False)}`")
    md_lines.extend(["", "## By Source Label", ""])
    for key in SOURCE_LABELS:
        value = summary["by_source_label"].get(key, {})
        md_lines.append(f"- `{key}`: `{json.dumps(value, ensure_ascii=False)}`")
    md_lines.extend(
        [
            "",
            "## Appendix",
            "",
            "Full missing object details are in the CSV appendix. The JSON report also embeds `missing_records` for AI-assisted summarization and follow-up backfill planning.",
            "",
        ]
    )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return json_path, md_path, appendix_path


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "只读审计 Web 可见热集在 R2 中的原文件、缩略图和 input_file 缺失情况。"
        )
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="在导入项目配置前加载指定 env 文件；不会打印其中的敏感值。",
    )
    parser.add_argument(
        "--recent-limit",
        type=int,
        default=8,
        help="每个用户最近可见历史条数，默认 8。",
    )
    parser.add_argument(
        "--skip-per-user-recent-history",
        action="store_true",
        help="不纳入每用户最近 N 条历史，仅审计社区强可见集合。",
    )
    parser.add_argument(
        "--skip-input-files",
        action="store_true",
        help="不审计 History.input_file 的 R2 对象。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制审计 history 数量，适合本地或云端小样本验证。",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=48,
        help="R2 HEAD 并发数与线程池 worker 数，默认 48。",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=1000,
        help="每审计多少条 History 输出一次进度日志；0 表示关闭，默认 1000。",
    )
    parser.add_argument(
        "--db-batch-size",
        type=int,
        default=1000,
        help="History 详情查询的数据库分批大小，默认 1000，避免超大 IN 查询。",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("logs"),
        help="报告输出目录，默认 logs。",
    )
    return parser


async def async_main(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    if not getattr(storage, "r2_client", None) or not getattr(storage, "r2_bucket", None):
        raise RuntimeError("R2 client 未初始化，无法审计 R2 对象。")

    async with AsyncSessionLocal() as session:
        history_ids, source_counts = await collect_web_visible_retire_legacy_history_ids(
            session,
            recent_limit=args.recent_limit,
            include_per_user_recent=not args.skip_per_user_recent_history,
            total_limit=args.limit,
        )
        selected_history_ids = set(history_ids)
        memberships = await collect_visible_hotset_source_memberships(
            session,
            recent_limit=args.recent_limit,
            include_per_user_recent=not args.skip_per_user_recent_history,
            selected_history_ids=selected_history_ids,
        )
        candidates = await collect_audit_candidates(
            session,
            history_ids=history_ids,
            source_memberships=memberships,
            db_batch_size=args.db_batch_size,
        )

    auditor = R2HeadAuditor(concurrency=args.concurrency)
    if not auditor.configured:
        raise RuntimeError("R2 HEAD client 未初始化，无法审计 R2 对象。")

    executor = ThreadPoolExecutor(
        max_workers=max(1, args.concurrency),
        thread_name_prefix="r2-head-audit",
    )
    try:
        asyncio.get_running_loop().set_default_executor(executor)
        results = await audit_candidates(
            candidates,
            auditor=auditor,
            include_input_files=not args.skip_input_files,
            concurrency=args.concurrency,
            progress_interval=args.progress_interval,
        )
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    summary = summarize_audit_results(
        results,
        selected_count=len(history_ids),
        source_counts=source_counts,
        include_input_files=not args.skip_input_files,
    )
    missing_records = build_missing_records(results)
    return write_reports(
        report_dir=args.report_dir,
        summary=summary,
        missing_records=missing_records,
        args=args,
    )


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("bot.database").setLevel(logging.CRITICAL)
    logging.getLogger("bot.database").propagate = False
    json_path, md_path, appendix_path = asyncio.run(async_main(args))
    print(
        json.dumps(
            {
                "json_report": str(json_path),
                "markdown_report": str(md_path),
                "missing_appendix_csv": str(appendix_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
