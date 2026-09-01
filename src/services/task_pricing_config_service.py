from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain_config.task_pricing_catalog import (
    build_base_task_pricing_catalog,
    pricing_variant_index,
    pricing_variants_for_task_type,
)
from src.domain_config.task_pricing_matcher import matching_pricing_variant


TASK_PRICING_CONFIG_KEY = "task_pricing_config:v1"
TASK_PRICING_SCHEMA_VERSION = 2
MAX_TASK_PRICE_CREDITS = 100_000
UNIFIED_PRICING_CLIENT_TYPES = frozenset({"web", "bot"})


class TaskPricingConfigValidationError(ValueError):
    pass


def _is_valid_price(raw_cost: Any) -> bool:
    return (
        isinstance(raw_cost, int)
        and not isinstance(raw_cost, bool)
        and 0 <= raw_cost <= MAX_TASK_PRICE_CREDITS
    )


def _expand_legacy_overrides(raw_overrides: Any) -> dict[str, int]:
    if not isinstance(raw_overrides, dict):
        return {}
    prices: dict[str, int] = {}
    for raw_task_type, raw_cost in raw_overrides.items():
        if not _is_valid_price(raw_cost):
            continue
        for variant in pricing_variants_for_task_type(str(raw_task_type or "").strip()):
            prices[variant["variant_id"]] = int(raw_cost)
    return prices


def normalize_task_pricing_config(raw: Any) -> dict[str, Any]:
    values = raw if isinstance(raw, dict) else {}
    known_variants = pricing_variant_index()
    prices = _expand_legacy_overrides(values.get("overrides"))
    raw_prices = values.get("prices")
    if isinstance(raw_prices, dict):
        for raw_variant_id, raw_cost in raw_prices.items():
            variant_id = str(raw_variant_id or "").strip()
            if variant_id in known_variants and _is_valid_price(raw_cost):
                prices[variant_id] = int(raw_cost)
    return {"schema_version": TASK_PRICING_SCHEMA_VERSION, "prices": prices}


def validate_task_pricing_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TaskPricingConfigValidationError("prices must be an object")
    raw_prices = raw.get("prices")
    if not isinstance(raw_prices, dict):
        # A rolling deployment may still send the former request shape.
        if isinstance(raw.get("overrides"), dict):
            return normalize_task_pricing_config(raw)
        raise TaskPricingConfigValidationError("prices must be an object")

    known_variants = pricing_variant_index()
    for raw_variant_id, raw_cost in raw_prices.items():
        variant_id = str(raw_variant_id or "").strip()
        if not _is_valid_price(raw_cost):
            if (
                not isinstance(raw_cost, int)
                or isinstance(raw_cost, bool)
                or raw_cost < 0
            ):
                raise TaskPricingConfigValidationError(
                    f"{variant_id or '<empty>'} price must be a non-negative integer"
                )
            raise TaskPricingConfigValidationError(
                f"{variant_id} price must be at most {MAX_TASK_PRICE_CREDITS}"
            )
        if variant_id not in known_variants:
            raise TaskPricingConfigValidationError(
                f"unknown pricing variant: {variant_id or '<empty>'}"
            )
    return normalize_task_pricing_config(raw)


def build_task_pricing_catalog(raw: Any) -> list[dict[str, Any]]:
    prices = normalize_task_pricing_config(raw)["prices"]
    catalog = deepcopy(build_base_task_pricing_catalog())
    for category in catalog:
        for offer in category["offers"]:
            for variant in offer["variants"]:
                override = prices.get(variant["variant_id"])
                variant["override_cost"] = override
                variant["effective_cost"] = (
                    variant["default_cost"] if override is None else override
                )
    return catalog


def resolve_configured_task_cost(
    raw: Any,
    *,
    task_type: str,
    inputs: dict[str, Any] | None = None,
    client_type: str,
    default_cost: int,
) -> int:
    if str(client_type or "").strip() not in UNIFIED_PRICING_CLIENT_TYPES:
        return int(default_cost)
    prices = normalize_task_pricing_config(raw)["prices"]
    variant = matching_pricing_variant(
        str(task_type or "").strip(),
        inputs if isinstance(inputs, dict) else {},
    )
    if variant is not None:
        configured = prices.get(variant["variant_id"])
        return int(default_cost if configured is None else configured)

    # Bot preflight checks run before every FSM has complete condition data. A
    # lower-bound check avoids incorrectly rejecting a task whose selected
    # variant is cheaper; TaskApplication repeats the authoritative check with
    # complete inputs immediately before debit.
    candidate_prices = [
        prices[item["variant_id"]]
        for item in pricing_variants_for_task_type(task_type)
        if item["variant_id"] in prices
    ]
    return int(min([default_cost, *candidate_prices]))


def _build_legacy_static_overrides(config: Any) -> dict[str, int]:
    """Compatibility map for old Web bundles during a rolling test deploy."""
    normalized = normalize_task_pricing_config(config)
    prices = normalized["prices"]
    result: dict[str, int] = {}
    task_types = {
        task_type
        for variant in pricing_variant_index().values()
        for task_type in variant["task_types"]
    }
    for task_type in task_types:
        variants = pricing_variants_for_task_type(task_type)
        if len(variants) == 1 and variants[0]["variant_id"] in prices:
            result[task_type] = prices[variants[0]["variant_id"]]
    return result


def _build_response(
    config: Any,
    *,
    updated_at: datetime | None,
) -> dict[str, Any]:
    normalized = normalize_task_pricing_config(config)
    return {
        "key": TASK_PRICING_CONFIG_KEY,
        "schema_version": normalized["schema_version"],
        "prices": normalized["prices"],
        "categories": build_task_pricing_catalog(normalized),
        "overrides": _build_legacy_static_overrides(normalized),
        "updated_at": updated_at,
    }


def build_public_task_pricing_payload(config: Any) -> dict[str, Any]:
    """Compile the small read-only matcher contract used by the public Web UI."""
    normalized = normalize_task_pricing_config(config)
    return {
        "schema_version": normalized["schema_version"],
        "prices": normalized["prices"],
        "variants": [
            {
                "variant_id": variant["variant_id"],
                "task_types": variant["task_types"],
                "conditions": variant["conditions"],
            }
            for variant in pricing_variant_index().values()
        ],
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
    if str(client_type or "").strip() not in UNIFIED_PRICING_CLIENT_TYPES:
        return int(default_cost)

    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        payload = await load_task_pricing_config_payload(db)
    return resolve_configured_task_cost(
        {"prices": payload["prices"]},
        task_type=task_type,
        inputs=inputs,
        client_type=client_type,
        default_cost=default_cost,
    )
