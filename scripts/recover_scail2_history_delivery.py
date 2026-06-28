import argparse
import asyncio
import json
import logging
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, select


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

from src.core.task_lifecycle_contract import BACKEND_STATUS_DONE  # noqa: E402
from src.core.task_status_mapper import normalize_backend_status  # noqa: E402
from src.database.core import AsyncSessionLocal  # noqa: E402
from src.database.models import History, RuntimeCheckpoint, User  # noqa: E402
from src.services.image_service import image_service  # noqa: E402
from src.services.redis_client import redis_client  # noqa: E402
from src.services.task_web_finalizer import process_pending_web_finalizer  # noqa: E402
from src.web_api.services.history_delivery_service import (  # noqa: E402
    HistoryDeliveryDependencies,
    get_default_history_delivery_dependencies,
    send_history_record_to_telegram,
)


logger = logging.getLogger(__name__)

SCAIL2_TASK_TYPES = frozenset(
    {
        "scail2_action_transfer",
        "scail2_action_transfer_long",
        "scail2_video_replacement",
        "scail2_face_swap_v2",
    }
)
DEFAULT_CHECKPOINT_KEY = "scail2_history_delivery_recovery_20260618"
SNAPSHOT_GLOB = "scail2_history_delivery_snapshot_*.json"


@dataclass(frozen=True)
class FinalizerCandidate:
    registry_task_id: str
    backend_task_id: str | None
    internal_user_id: int | None
    username: str | None
    task_type: str | None
    cost: int | None


@dataclass
class OperationItem:
    registry_task_id: str
    backend_task_id: str | None
    internal_user_id: int | None
    task_type: str | None
    status: str
    detail: str | None = None


def _utcish_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_task_types(raw: str | None) -> frozenset[str]:
    if not raw:
        return SCAIL2_TASK_TYPES
    task_types = {item.strip() for item in raw.split(",") if item.strip()}
    return frozenset(task_types or SCAIL2_TASK_TYPES)


def _record_task_type(record: dict[str, Any]) -> str | None:
    submission_context = record.get("submission_context")
    if isinstance(submission_context, dict):
        task_type = submission_context.get("task_type")
        if task_type:
            return str(task_type)
    task_type = record.get("task_type")
    return str(task_type) if task_type else None


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_finalizer_candidate(
    registry_task_id: str,
    record: dict[str, Any],
) -> FinalizerCandidate:
    return FinalizerCandidate(
        registry_task_id=registry_task_id,
        backend_task_id=record.get("backend_task_id"),
        internal_user_id=_to_int_or_none(record.get("internal_user_id")),
        username=record.get("username"),
        task_type=_record_task_type(record),
        cost=_to_int_or_none(record.get("cost")),
    )


def filter_scail2_candidates(
    pending_finalizers: dict[str, Any],
    *,
    task_types: frozenset[str],
    limit: int | None = None,
) -> list[FinalizerCandidate]:
    candidates: list[FinalizerCandidate] = []
    for registry_task_id, record in pending_finalizers.items():
        if not isinstance(record, dict):
            continue
        candidate = build_finalizer_candidate(registry_task_id, record)
        if candidate.task_type not in task_types:
            continue
        candidates.append(candidate)
        if limit and len(candidates) >= limit:
            break
    return candidates


def _snapshot_payload(
    *,
    candidates: list[FinalizerCandidate],
    task_types: frozenset[str],
    total_pending_count: int,
) -> dict[str, Any]:
    return {
        "created_at": _utcish_now(),
        "source": "pending_web_finalizers",
        "task_types": sorted(task_types),
        "total_pending_count": total_pending_count,
        "candidate_count": len(candidates),
        "records": [asdict(candidate) for candidate in candidates],
    }


async def snapshot_pending_web_finalizers(
    *,
    task_types: frozenset[str],
    output_file: Path,
    limit: int | None = None,
    redis_client_obj=redis_client,
) -> dict[str, Any]:
    pending_finalizers = await redis_client_obj.get_pending_web_finalizers()
    candidates = filter_scail2_candidates(
        pending_finalizers,
        task_types=task_types,
        limit=limit,
    )
    payload = _snapshot_payload(
        candidates=candidates,
        task_types=task_types,
        total_pending_count=len(pending_finalizers),
    )
    payload["snapshot_file"] = str(output_file)
    _write_json_file(output_file, payload)
    return payload


def load_snapshot_candidates(snapshot_file: Path) -> list[FinalizerCandidate]:
    payload = _read_json_file(snapshot_file)
    records = payload.get("records") or []
    candidates: list[FinalizerCandidate] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        candidates.append(
            FinalizerCandidate(
                registry_task_id=str(record.get("registry_task_id") or ""),
                backend_task_id=record.get("backend_task_id"),
                internal_user_id=_to_int_or_none(record.get("internal_user_id")),
                username=record.get("username"),
                task_type=record.get("task_type"),
                cost=_to_int_or_none(record.get("cost")),
            )
        )
    return [candidate for candidate in candidates if candidate.registry_task_id]


async def fetch_history_with_output(db, candidate: FinalizerCandidate) -> History | None:
    if candidate.internal_user_id is None:
        return None
    result = await db.execute(
        select(History)
        .where(
            History.task_id == candidate.registry_task_id,
            History.user_id == candidate.internal_user_id,
            History.source == "web",
        )
        .order_by(desc(History.id))
    )
    for history in result.scalars().all():
        if history.output_file:
            return history
    return None


async def _history_exists(
    candidate: FinalizerCandidate,
    *,
    session_factory=AsyncSessionLocal,
) -> bool:
    async with session_factory() as db:
        return await fetch_history_with_output(db, candidate) is not None


async def _get_backend_status(
    candidate: FinalizerCandidate,
    *,
    get_task_status_func=image_service.get_task_status,
) -> dict[str, Any] | None:
    if not candidate.backend_task_id:
        return None
    return await get_task_status_func(candidate.backend_task_id)


async def recover_snapshot_histories(
    *,
    candidates: list[FinalizerCandidate],
    execute: bool,
    session_factory=AsyncSessionLocal,
    process_finalizer_func=process_pending_web_finalizer,
    get_task_status_func=image_service.get_task_status,
) -> dict[str, Any]:
    items: list[OperationItem] = []
    counters: Counter[str] = Counter()

    for candidate in candidates:
        if candidate.task_type not in SCAIL2_TASK_TYPES:
            counters["skipped_non_scail2"] += 1
            items.append(_operation_item(candidate, "skipped_non_scail2"))
            continue

        if candidate.internal_user_id is None:
            counters["skipped_missing_user"] += 1
            items.append(_operation_item(candidate, "skipped_missing_user"))
            continue

        if await _history_exists(candidate, session_factory=session_factory):
            counters["history_already_exists"] += 1
            items.append(_operation_item(candidate, "history_already_exists"))
            continue

        status_data = await _get_backend_status(
            candidate,
            get_task_status_func=get_task_status_func,
        )
        if not status_data:
            counters["skipped_missing_backend_status"] += 1
            items.append(_operation_item(candidate, "skipped_missing_backend_status"))
            continue

        backend_status = normalize_backend_status(status_data.get("status"))
        result_path = status_data.get("result_path")
        if backend_status != BACKEND_STATUS_DONE:
            counters["audit_backend_not_success"] += 1
            items.append(
                _operation_item(
                    candidate,
                    "audit_backend_not_success",
                    detail=str(status_data.get("error") or status_data.get("error_msg") or backend_status),
                )
            )
            continue

        if not result_path:
            counters["audit_done_without_result_path"] += 1
            items.append(_operation_item(candidate, "audit_done_without_result_path"))
            continue

        if not execute:
            counters["would_recover"] += 1
            items.append(_operation_item(candidate, "would_recover"))
            continue

        try:
            finalized = await process_finalizer_func(candidate.registry_task_id)
        except Exception as exc:
            logger.exception(
                "Failed to recover SCAIL-2 finalizer for %s",
                candidate.registry_task_id,
            )
            counters["recover_failed"] += 1
            items.append(_operation_item(candidate, "recover_failed", detail=str(exc)))
            continue

        if await _history_exists(candidate, session_factory=session_factory):
            counters["recovered"] += 1
            detail = "finalizer_processed" if finalized else "history_confirmed"
            items.append(_operation_item(candidate, "recovered", detail=detail))
        else:
            counters["recover_unconfirmed"] += 1
            detail = "finalizer_processed" if finalized else "finalizer_skipped"
            items.append(_operation_item(candidate, "recover_unconfirmed", detail=detail))

    return _operation_report("recover", execute=execute, counters=counters, items=items)


def _operation_item(
    candidate: FinalizerCandidate,
    status: str,
    *,
    detail: str | None = None,
) -> OperationItem:
    return OperationItem(
        registry_task_id=candidate.registry_task_id,
        backend_task_id=candidate.backend_task_id,
        internal_user_id=candidate.internal_user_id,
        task_type=candidate.task_type,
        status=status,
        detail=detail,
    )


def _operation_report(
    command: str,
    *,
    execute: bool,
    counters: Counter[str],
    items: list[OperationItem],
) -> dict[str, Any]:
    return {
        "command": command,
        "execute": execute,
        "created_at": _utcish_now(),
        "summary": dict(sorted(counters.items())),
        "items": [asdict(item) for item in items],
    }


async def _noop_rate_limit(_user_id: int) -> None:
    return None


def build_recovery_delivery_dependencies(
    dependencies: HistoryDeliveryDependencies | None = None,
) -> HistoryDeliveryDependencies:
    dependencies = dependencies or get_default_history_delivery_dependencies()
    return replace(dependencies, acquire_rate_limit_func=_noop_rate_limit)


def _normalize_checkpoint(value: Any) -> dict[str, Any]:
    checkpoint = dict(value) if isinstance(value, dict) else {}
    for key in ("sent_task_ids", "failed_task_ids"):
        raw_items = checkpoint.get(key) or []
        checkpoint[key] = sorted({str(item) for item in raw_items if item})
    failed_details = checkpoint.get("failed_details")
    checkpoint["failed_details"] = failed_details if isinstance(failed_details, dict) else {}
    return checkpoint


async def load_delivery_checkpoint(
    *,
    key: str,
    session_factory=AsyncSessionLocal,
) -> dict[str, Any]:
    async with session_factory() as db:
        checkpoint = await db.get(RuntimeCheckpoint, key)
        return _normalize_checkpoint(getattr(checkpoint, "value", None))


async def save_delivery_checkpoint(
    *,
    key: str,
    value: dict[str, Any],
    session_factory=AsyncSessionLocal,
) -> None:
    normalized = _normalize_checkpoint(value)
    async with session_factory() as db:
        checkpoint = await db.get(RuntimeCheckpoint, key)
        if checkpoint is None:
            checkpoint = RuntimeCheckpoint(key=key, value=normalized)
            db.add(checkpoint)
        else:
            checkpoint.value = normalized
            checkpoint.updated_at = datetime.now()
        await db.commit()


async def _load_user_for_candidate(db, candidate: FinalizerCandidate) -> User | None:
    if candidate.internal_user_id is None:
        return None
    return await db.get(User, candidate.internal_user_id)


async def send_recovered_histories(
    *,
    candidates: list[FinalizerCandidate],
    execute: bool,
    checkpoint_key: str = DEFAULT_CHECKPOINT_KEY,
    sleep_seconds: float = 0.0,
    session_factory=AsyncSessionLocal,
    delivery_dependencies: HistoryDeliveryDependencies | None = None,
    send_service_func=send_history_record_to_telegram,
) -> dict[str, Any]:
    items: list[OperationItem] = []
    counters: Counter[str] = Counter()
    checkpoint = await load_delivery_checkpoint(
        key=checkpoint_key,
        session_factory=session_factory,
    )
    sent_task_ids = set(checkpoint["sent_task_ids"])
    failed_task_ids = set(checkpoint["failed_task_ids"])
    failed_details = dict(checkpoint["failed_details"])
    delivery_dependencies = build_recovery_delivery_dependencies(delivery_dependencies)

    for candidate in candidates:
        if candidate.task_type not in SCAIL2_TASK_TYPES:
            counters["skipped_non_scail2"] += 1
            items.append(_operation_item(candidate, "skipped_non_scail2"))
            continue

        if candidate.registry_task_id in sent_task_ids:
            counters["already_sent"] += 1
            items.append(_operation_item(candidate, "already_sent"))
            continue

        async with session_factory() as db:
            history = await fetch_history_with_output(db, candidate)
            if not history:
                counters["skipped_no_history_output"] += 1
                items.append(_operation_item(candidate, "skipped_no_history_output"))
                continue

            user = await _load_user_for_candidate(db, candidate)
            telegram_id = getattr(user, "telegram_id", None)
            if not telegram_id:
                counters["skipped_no_telegram"] += 1
                items.append(_operation_item(candidate, "skipped_no_telegram"))
                continue

            if not execute:
                counters["would_send"] += 1
                items.append(_operation_item(candidate, "would_send"))
                continue

            current_user = SimpleNamespace(id=user.id, telegram_id=telegram_id)
            try:
                await send_service_func(
                    task_id=candidate.registry_task_id,
                    current_user=current_user,
                    db=db,
                    dependencies=delivery_dependencies,
                )
            except HTTPException as exc:
                counters["failed_send"] += 1
                failed_task_ids.add(candidate.registry_task_id)
                failed_details[candidate.registry_task_id] = {
                    "at": _utcish_now(),
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
                items.append(
                    _operation_item(
                        candidate,
                        "failed_send",
                        detail=f"{exc.status_code}: {exc.detail}",
                    )
                )
            except Exception as exc:
                logger.exception(
                    "Failed to send recovered SCAIL-2 result for %s",
                    candidate.registry_task_id,
                )
                counters["failed_send"] += 1
                failed_task_ids.add(candidate.registry_task_id)
                failed_details[candidate.registry_task_id] = {
                    "at": _utcish_now(),
                    "detail": str(exc),
                }
                items.append(_operation_item(candidate, "failed_send", detail=str(exc)))
            else:
                counters["sent"] += 1
                sent_task_ids.add(candidate.registry_task_id)
                failed_task_ids.discard(candidate.registry_task_id)
                failed_details.pop(candidate.registry_task_id, None)
                items.append(_operation_item(candidate, "sent"))

        if execute:
            checkpoint = {
                **checkpoint,
                "sent_task_ids": sorted(sent_task_ids),
                "failed_task_ids": sorted(failed_task_ids),
                "failed_details": failed_details,
                "updated_at": _utcish_now(),
            }
            await save_delivery_checkpoint(
                key=checkpoint_key,
                value=checkpoint,
                session_factory=session_factory,
            )

        if execute and sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)

    return _operation_report("send", execute=execute, counters=counters, items=items)


def _default_snapshot_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return ROOT / "logs" / f"scail2_history_delivery_snapshot_{stamp}.json"


def _default_report_path(command: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return ROOT / "logs" / f"scail2_history_delivery_{command}_report_{stamp}.json"


def _latest_snapshot_path() -> Path:
    candidates = sorted((ROOT / "logs").glob(SNAPSHOT_GLOB), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(
            "No snapshot found in logs/. Run snapshot first or pass --snapshot-file."
        )
    return candidates[-1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recover SCAIL-2 web History rows and optionally send results to Telegram."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--env-file", help="Optional env file. Compose env can be used instead.")
    common.add_argument("--snapshot-file", help="Snapshot JSON file path.")
    common.add_argument("--report-file", help="Optional operation report JSON path.")
    common.add_argument(
        "--task-types",
        default=",".join(sorted(SCAIL2_TASK_TYPES)),
        help="Comma-separated task types to include.",
    )
    common.add_argument("--limit", type=int, default=None)
    common.add_argument("--execute", action="store_true", help="Allow DB/TG mutations.")
    common.add_argument("--dry-run", action="store_true", help="Accepted for explicit read-only runs.")

    subparsers.add_parser("snapshot", parents=[common])
    subparsers.add_parser("recover", parents=[common])
    send_parser = subparsers.add_parser("send", parents=[common])
    send_parser.add_argument("--checkpoint-key", default=DEFAULT_CHECKPOINT_KEY)
    send_parser.add_argument("--sleep-seconds", type=float, default=1.0)
    return parser


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    task_types = parse_task_types(args.task_types)

    if args.command == "snapshot":
        snapshot_file = Path(args.snapshot_file) if args.snapshot_file else _default_snapshot_path()
        return await snapshot_pending_web_finalizers(
            task_types=task_types,
            output_file=snapshot_file,
            limit=args.limit,
        )

    snapshot_file = Path(args.snapshot_file) if args.snapshot_file else _latest_snapshot_path()
    candidates = load_snapshot_candidates(snapshot_file)
    if args.limit:
        candidates = candidates[: args.limit]

    if args.command == "recover":
        report = await recover_snapshot_histories(
            candidates=candidates,
            execute=args.execute,
        )
    elif args.command == "send":
        report = await send_recovered_histories(
            candidates=candidates,
            execute=args.execute,
            checkpoint_key=args.checkpoint_key,
            sleep_seconds=args.sleep_seconds,
        )
    else:
        raise ValueError(f"Unsupported command: {args.command}")

    report["snapshot_file"] = str(snapshot_file)
    if args.report_file:
        _write_json_file(Path(args.report_file), report)
        report["report_file"] = args.report_file
    else:
        report_file = _default_report_path(args.command)
        _write_json_file(report_file, report)
        report["report_file"] = str(report_file)
    return report


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    parser = build_parser()
    args = parser.parse_args()
    if args.dry_run and args.execute:
        parser.error("--dry-run and --execute cannot be used together")

    report = asyncio.run(_run(args))
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
