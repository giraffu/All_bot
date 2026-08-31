from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain_config.task_type_registry import (
    TASK_TYPE_REGISTRY,
    iter_task_type_entries,
)


TASK_PRICING_CONFIG_KEY = "task_pricing_config:v1"
MAX_TASK_PRICE_CREDITS = 100_000
UNIFIED_PRICING_CLIENT_TYPES = frozenset({"web", "bot"})


class TaskPricingConfigValidationError(ValueError):
    pass


def normalize_task_pricing_config(raw: Any) -> dict[str, dict[str, int]]:
    values = raw if isinstance(raw, dict) else {}
    raw_overrides = values.get("overrides")
    raw_overrides = raw_overrides if isinstance(raw_overrides, dict) else {}
    overrides: dict[str, int] = {}
    for raw_task_type, raw_cost in raw_overrides.items():
        task_type = str(raw_task_type or "").strip()
        if task_type not in TASK_TYPE_REGISTRY:
            continue
        if (
            not isinstance(raw_cost, int)
            or isinstance(raw_cost, bool)
            or not 0 <= raw_cost <= MAX_TASK_PRICE_CREDITS
        ):
            continue
        overrides[task_type] = int(raw_cost)
    return {"overrides": overrides}


def validate_task_pricing_config(raw: Any) -> dict[str, dict[str, int]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("overrides"), dict):
        raise TaskPricingConfigValidationError("overrides must be an object")

    for raw_task_type, raw_cost in raw["overrides"].items():
        task_type = str(raw_task_type or "").strip()
        if task_type not in TASK_TYPE_REGISTRY:
            raise TaskPricingConfigValidationError(
                f"unknown task type: {task_type or '<empty>'}"
            )
        if (
            not isinstance(raw_cost, int)
            or isinstance(raw_cost, bool)
            or raw_cost < 0
        ):
            raise TaskPricingConfigValidationError(
                f"{task_type} price must be a non-negative integer"
            )
        if raw_cost > MAX_TASK_PRICE_CREDITS:
            raise TaskPricingConfigValidationError(
                f"{task_type} price must be at most {MAX_TASK_PRICE_CREDITS}"
            )
    return normalize_task_pricing_config(raw)


def build_task_pricing_catalog(raw: Any) -> list[dict[str, Any]]:
    overrides = normalize_task_pricing_config(raw)["overrides"]
    return [
        {
            "task_type": entry.task_type,
            "public_type": entry.public_type,
            "execution_type": entry.execution_type,
            "default_cost": entry.cost,
            "override_cost": overrides.get(entry.task_type),
            "effective_cost": overrides.get(entry.task_type, entry.cost),
            "pricing_mode": "fixed" if entry.cost is not None else "dynamic",
            "is_generation": entry.is_generation,
            "is_video": entry.is_video,
            "legacy_alias_of": entry.legacy_alias_of,
        }
        for entry in iter_task_type_entries()
    ]


def resolve_configured_task_cost(
    raw: Any,
    *,
    task_type: str,
    client_type: str,
    default_cost: int,
) -> int:
    if str(client_type or "").strip() not in UNIFIED_PRICING_CLIENT_TYPES:
        return int(default_cost)
    overrides = normalize_task_pricing_config(raw)["overrides"]
    override = overrides.get(str(task_type or "").strip())
    return int(default_cost if override is None else override)


def _build_response(
    config: Any,
    *,
    updated_at: datetime | None,
) -> dict[str, Any]:
    normalized = normalize_task_pricing_config(config)
    return {
        "key": TASK_PRICING_CONFIG_KEY,
        "overrides": normalized["overrides"],
        "items": build_task_pricing_catalog(normalized),
        "updated_at": updated_at,
    }


async def load_task_pricing_config_payload(db: AsyncSession) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    result = await db.execute(
        select(RuntimeCheckpoint).where(
            RuntimeCheckpoint.key == TASK_PRICING_CONFIG_KEY
        )
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        return _build_response({}, updated_at=None)
    return _build_response(
        checkpoint.value or {},
        updated_at=checkpoint.updated_at,
    )


async def save_task_pricing_config_payload(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    config = validate_task_pricing_config(payload)
    result = await db.execute(
        select(RuntimeCheckpoint)
        .where(RuntimeCheckpoint.key == TASK_PRICING_CONFIG_KEY)
        .with_for_update()
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        checkpoint = RuntimeCheckpoint(
            key=TASK_PRICING_CONFIG_KEY,
            value=config,
        )
        db.add(checkpoint)
    else:
        checkpoint.value = config
    await db.commit()
    await db.refresh(checkpoint)
    return _build_response(
        checkpoint.value or {},
        updated_at=checkpoint.updated_at,
    )


async def resolve_runtime_task_cost(
    *,
    task_type: str,
    inputs: dict[str, Any],
    client_type: str,
    default_cost: int,
) -> int:
    del inputs
    if str(client_type or "").strip() not in UNIFIED_PRICING_CLIENT_TYPES:
        return int(default_cost)

    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        payload = await load_task_pricing_config_payload(db)
    return resolve_configured_task_cost(
        {"overrides": payload["overrides"]},
        task_type=task_type,
        client_type=client_type,
        default_cost=default_cost,
    )
