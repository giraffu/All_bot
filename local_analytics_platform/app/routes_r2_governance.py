from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .routes_archive import require_archive_auth


router = APIRouter()


def _parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _summary(document: dict[str, Any], path: Path) -> dict[str, Any]:
    failures = document.get("probe_failures") or []
    return {
        "evidence_file": path.name,
        "batch_id": document.get("batch_id"),
        "generated_at": document.get("generated_at"),
        "mode": document.get("mode"),
        "status": document.get("status"),
        "candidate_count": int(document.get("candidate_count") or 0),
        "verified_count": int(document.get("verified_count") or 0),
        "delete_count": int(document.get("delete_count") or 0),
        "delete_bytes": int(document.get("delete_bytes") or 0),
        "post_delete_verified_count": int(
            document.get("post_delete_verified_count") or 0
        ),
        "referenced_blocked_count": int(
            document.get("referenced_blocked_count") or 0
        ),
        "referenced_blocked_bytes": int(
            document.get("referenced_blocked_bytes") or 0
        ),
        "probe_failure_count": len(failures),
        "plan_sha256": document.get("plan_sha256"),
        "approved_plan_sha256": document.get("approved_plan_sha256"),
    }


def load_governance_status(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    rows: list[tuple[datetime, dict[str, Any], dict[str, Any]]] = []
    for path in root.rglob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict) or document.get("mode") not in {
            "dry-run", "execute"
        }:
            continue
        generated = _parse_time(document.get("generated_at")) or datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        )
        rows.append((generated, _summary(document, path), document))
    rows.sort(key=lambda item: item[0], reverse=True)
    latest_summary = rows[0][1] if rows else {}
    latest_document = rows[0][2] if rows else {}
    staging = latest_document.get("staging") or {}
    inventory = latest_document.get("inventory") or {}
    web_uploads = latest_document.get("legacy_web_uploads_report_only") or {}
    persistence_metrics: dict[str, Any] = {}
    metrics_path = root / "central-result-storage-metrics.json"
    if metrics_path.is_file():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            if isinstance(metrics, dict):
                counts = metrics.get("failure_counts")
                if isinstance(counts, dict):
                    persistence_metrics = {
                        str(key): int(value) for key, value in counts.items()
                    }
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            persistence_metrics = {}
    oldest = _parse_time(staging.get("oldest_last_modified"))
    oldest_age_hours = (
        (datetime.now(timezone.utc) - oldest).total_seconds() / 3600 if oldest else None
    )
    inventory_mtime = inventory.get("mtime")
    inventory_age_hours = None
    if inventory_mtime is not None:
        try:
            inventory_age_hours = (
                datetime.now(timezone.utc).timestamp() - float(inventory_mtime)
            ) / 3600
        except (TypeError, ValueError):
            inventory_age_hours = None
    return {
        "latest": latest_summary,
        "batches": [item[1] for item in rows[:30]],
        "inventory": {**inventory, "age_hours": inventory_age_hours},
        "staging": {**staging, "oldest_age_hours": oldest_age_hours},
        "web_uploads_report_only": web_uploads,
        "persistence_failure_counts": persistence_metrics,
        "alerts": {
            "probe_failure": bool(latest_summary.get("probe_failure_count")),
            "cleanup_incomplete": bool(rows and latest_summary.get("mode") == "execute"
                and latest_summary.get("status") != "completed"),
            "staging_older_than_24h": bool(
                oldest_age_hours is not None and oldest_age_hours > 24
            ),
            "inventory_older_than_36h": bool(
                inventory_age_hours is not None and inventory_age_hours > 36
            ),
            "blocked_bytes_present": bool(
                latest_summary.get("referenced_blocked_bytes")
            ),
        },
    }


@router.get(
    "/api/r2-governance/status",
    dependencies=[Depends(require_archive_auth)],
)
async def governance_status(_request: Request):
    root = Path(os.getenv(
        "R2_TEMP_CLEANUP_EVIDENCE_ROOT", "/var/lib/allbot-r2-temp-cleanup"
    ))
    try:
        return load_governance_status(root)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="R2 governance evidence is unavailable") from exc
