from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


USER_TIER_POLICY_CONFIG_KEY = "user_tier_policy_config:v1"

CULTIVATION_RANKS = ("凡人", "练气期", "筑基期", "金丹期", "元婴期")
MEMBERSHIP_IDENTITIES = ("外门弟子", "内门弟子", "核心弟子", "真传弟子")
LEGACY_HIGH_RANKS = ("化神期", "炼虚期", "合体期", "大乘期", "渡劫期")
VIDEO_RESOLUTIONS = ("512p", "720p", "1024p")
VIDEO_DURATIONS = ("5s", "8s", "10s")


def _rank(
    *,
    invitations: int,
    checkins: int,
    generations: int,
    channel_member: bool,
    checkin_enabled: bool,
    checkin_credits: int,
    web_access: bool,
    flashback_bottles: int,
    queue_pressure_exempt: bool,
    resolutions: list[str],
    durations: list[str],
    priority_rules: list[dict[str, int | None]],
) -> dict[str, Any]:
    return {
        "upgrade": {
            "invitations": invitations,
            "checkins": checkins,
            "generations": generations,
            "channel_member": channel_member,
        },
        "benefits": {
            "checkin_enabled": checkin_enabled,
            "checkin_credits": checkin_credits,
            "web_access": web_access,
            "flashback_bottles": flashback_bottles,
            "queue_pressure_exempt": queue_pressure_exempt,
        },
        "video": {"resolutions": resolutions, "durations": durations},
        "priority_rules": priority_rules,
    }


def _identity(
    *,
    mortal_checkin_access: bool,
    checkin_bonus: int,
    web_access: bool,
    concurrent_tasks: int,
    favorite_limit: int,
    flashback_bottles: int,
    queue_pressure_exempt: bool,
    resolutions: list[str],
    durations: list[str],
    priority_rules: list[dict[str, int | None]],
) -> dict[str, Any]:
    return {
        "benefits": {
            "mortal_checkin_access": mortal_checkin_access,
            "checkin_bonus": checkin_bonus,
            "web_access": web_access,
            "concurrent_tasks": concurrent_tasks,
            "favorite_limit": favorite_limit,
            "flashback_bottles": flashback_bottles,
            "queue_pressure_exempt": queue_pressure_exempt,
        },
        "video": {"resolutions": resolutions, "durations": durations},
        "priority_rules": priority_rules,
    }


DEFAULT_USER_TIER_POLICY_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "capacity_combination_rule": "max",
    "cultivation_ranks": {
        "凡人": _rank(
            invitations=0,
            checkins=0,
            generations=0,
            channel_member=False,
            checkin_enabled=False,
            checkin_credits=10,
            web_access=False,
            flashback_bottles=8,
            queue_pressure_exempt=False,
            resolutions=["512p"],
            durations=["5s"],
            priority_rules=[],
        ),
        "练气期": _rank(
            invitations=0,
            checkins=0,
            generations=0,
            channel_member=True,
            checkin_enabled=True,
            checkin_credits=10,
            web_access=True,
            flashback_bottles=9,
            queue_pressure_exempt=False,
            resolutions=["512p"],
            durations=["5s"],
            priority_rules=[
                {"daily_usage_lt": 10, "priority": 3},
                {"daily_usage_lt": 50, "priority": 1},
            ],
        ),
        "筑基期": _rank(
            invitations=2,
            checkins=4,
            generations=11,
            channel_member=False,
            checkin_enabled=True,
            checkin_credits=12,
            web_access=True,
            flashback_bottles=10,
            queue_pressure_exempt=True,
            resolutions=["512p", "720p"],
            durations=["5s", "8s"],
            priority_rules=[
                {"daily_usage_lt": 10, "priority": 5},
                {"daily_usage_lt": 50, "priority": 1},
            ],
        ),
        "金丹期": _rank(
            invitations=11,
            checkins=31,
            generations=101,
            channel_member=False,
            checkin_enabled=True,
            checkin_credits=15,
            web_access=True,
            flashback_bottles=12,
            queue_pressure_exempt=True,
            resolutions=["512p", "720p", "1024p"],
            durations=["5s", "8s", "10s"],
            priority_rules=[
                {"daily_usage_lt": 10, "priority": 8},
                {"daily_usage_lt": 50, "priority": 3},
                {"daily_usage_lt": 100, "priority": 1},
            ],
        ),
        "元婴期": _rank(
            invitations=101,
            checkins=301,
            generations=1001,
            channel_member=False,
            checkin_enabled=True,
            checkin_credits=20,
            web_access=True,
            flashback_bottles=14,
            queue_pressure_exempt=True,
            resolutions=["512p", "720p", "1024p"],
            durations=["5s", "8s", "10s"],
            priority_rules=[
                {"daily_usage_lt": 10, "priority": 12},
                {"daily_usage_lt": 50, "priority": 5},
                {"daily_usage_lt": 100, "priority": 1},
            ],
        ),
    },
    "membership_identities": {
        "外门弟子": _identity(
            mortal_checkin_access=False,
            checkin_bonus=0,
            web_access=False,
            concurrent_tasks=3,
            favorite_limit=100,
            flashback_bottles=8,
            queue_pressure_exempt=False,
            resolutions=["512p"],
            durations=["5s"],
            priority_rules=[],
        ),
        "内门弟子": _identity(
            mortal_checkin_access=True,
            checkin_bonus=30,
            web_access=True,
            concurrent_tasks=5,
            favorite_limit=300,
            flashback_bottles=10,
            queue_pressure_exempt=True,
            resolutions=["512p", "720p"],
            durations=["5s", "8s"],
            priority_rules=[
                {"daily_usage_lt": 20, "priority": 20},
                {"daily_usage_lt": 50, "priority": 8},
                {"daily_usage_lt": None, "priority": 1},
            ],
        ),
        "核心弟子": _identity(
            mortal_checkin_access=True,
            checkin_bonus=40,
            web_access=True,
            concurrent_tasks=8,
            favorite_limit=600,
            flashback_bottles=12,
            queue_pressure_exempt=True,
            resolutions=["512p", "720p", "1024p"],
            durations=["5s", "8s", "10s"],
            priority_rules=[
                {"daily_usage_lt": 30, "priority": 30},
                {"daily_usage_lt": 60, "priority": 12},
                {"daily_usage_lt": None, "priority": 1},
            ],
        ),
        "真传弟子": _identity(
            mortal_checkin_access=True,
            checkin_bonus=50,
            web_access=True,
            concurrent_tasks=12,
            favorite_limit=1000,
            flashback_bottles=14,
            queue_pressure_exempt=True,
            resolutions=["512p", "720p", "1024p"],
            durations=["5s", "8s", "10s"],
            priority_rules=[
                {"daily_usage_lt": 40, "priority": 45},
                {"daily_usage_lt": 70, "priority": 20},
                {"daily_usage_lt": None, "priority": 1},
            ],
        ),
    },
    "low_trust": {
        "enabled": True,
        "checkin_threshold": 7,
        "successful_order_exempt": True,
        "referral_count_threshold": 100,
        "successful_invitee_rate_percent_threshold": 3,
        "trusted_priority_bonus": 40,
        "new_user_generation_threshold": 2,
        "new_user_base_priority": 30,
    },
}


def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if minimum <= parsed <= maximum else default


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _choice_list(value: Any, default: list[str], allowed: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    selected = {item for item in value if isinstance(item, str) and item in allowed}
    selected.add(allowed[0])
    result = [item for item in allowed if item in selected]
    return result or list(default)


def _priority_rules(value: Any, default: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return deepcopy(default)
    rules: list[dict[str, Any]] = []
    previous_limit = -1
    candidates = value[:4]
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            return deepcopy(default)
        raw_limit = item.get("daily_usage_lt")
        limit = None if raw_limit is None else _int(raw_limit, -1, 1, 100_000)
        priority = _int(item.get("priority"), -1, 0, 500)
        if priority < 0 or (limit is not None and limit <= previous_limit):
            return deepcopy(default)
        if limit is None and index != len(candidates) - 1:
            return deepcopy(default)
        rules.append({"daily_usage_lt": limit, "priority": priority})
        if limit is not None:
            previous_limit = limit
    return rules


def normalize_user_tier_policy_config(raw: Any) -> dict[str, Any]:
    values = raw if isinstance(raw, dict) else {}
    defaults = DEFAULT_USER_TIER_POLICY_CONFIG
    rank_values = values.get("cultivation_ranks")
    rank_values = rank_values if isinstance(rank_values, dict) else {}
    identity_values = values.get("membership_identities")
    identity_values = identity_values if isinstance(identity_values, dict) else {}

    ranks: dict[str, Any] = {}
    for key in CULTIVATION_RANKS:
        default = defaults["cultivation_ranks"][key]
        item = rank_values.get(key)
        item = item if isinstance(item, dict) else {}
        upgrade = item.get("upgrade") if isinstance(item.get("upgrade"), dict) else {}
        benefits = item.get("benefits") if isinstance(item.get("benefits"), dict) else {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        ranks[key] = {
            "upgrade": {
                "invitations": _int(upgrade.get("invitations"), default["upgrade"]["invitations"], 0, 1_000_000),
                "checkins": _int(upgrade.get("checkins"), default["upgrade"]["checkins"], 0, 1_000_000),
                "generations": _int(upgrade.get("generations"), default["upgrade"]["generations"], 0, 10_000_000),
                "channel_member": _bool(upgrade.get("channel_member"), default["upgrade"]["channel_member"]),
            },
            "benefits": {
                "checkin_enabled": _bool(benefits.get("checkin_enabled"), default["benefits"]["checkin_enabled"]),
                "checkin_credits": _int(benefits.get("checkin_credits"), default["benefits"]["checkin_credits"], 0, 10_000),
                "web_access": _bool(benefits.get("web_access"), default["benefits"]["web_access"]),
                "flashback_bottles": _int(benefits.get("flashback_bottles"), default["benefits"]["flashback_bottles"], 1, 100),
                "queue_pressure_exempt": _bool(benefits.get("queue_pressure_exempt"), default["benefits"]["queue_pressure_exempt"]),
            },
            "video": {
                "resolutions": _choice_list(video.get("resolutions"), default["video"]["resolutions"], VIDEO_RESOLUTIONS),
                "durations": _choice_list(video.get("durations"), default["video"]["durations"], VIDEO_DURATIONS),
            },
            "priority_rules": _priority_rules(item.get("priority_rules"), default["priority_rules"]),
        }

    identities: dict[str, Any] = {}
    for key in MEMBERSHIP_IDENTITIES:
        default = defaults["membership_identities"][key]
        item = identity_values.get(key)
        item = item if isinstance(item, dict) else {}
        benefits = item.get("benefits") if isinstance(item.get("benefits"), dict) else {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}
        identities[key] = {
            "benefits": {
                "mortal_checkin_access": _bool(benefits.get("mortal_checkin_access"), default["benefits"]["mortal_checkin_access"]),
                "checkin_bonus": _int(benefits.get("checkin_bonus"), default["benefits"]["checkin_bonus"], 0, 10_000),
                "web_access": _bool(benefits.get("web_access"), default["benefits"]["web_access"]),
                "concurrent_tasks": _int(benefits.get("concurrent_tasks"), default["benefits"]["concurrent_tasks"], 1, 100),
                "favorite_limit": _int(benefits.get("favorite_limit"), default["benefits"]["favorite_limit"], 1, 100_000),
                "flashback_bottles": _int(benefits.get("flashback_bottles"), default["benefits"]["flashback_bottles"], 1, 100),
                "queue_pressure_exempt": _bool(benefits.get("queue_pressure_exempt"), default["benefits"]["queue_pressure_exempt"]),
            },
            "video": {
                "resolutions": _choice_list(video.get("resolutions"), default["video"]["resolutions"], VIDEO_RESOLUTIONS),
                "durations": _choice_list(video.get("durations"), default["video"]["durations"], VIDEO_DURATIONS),
            },
            "priority_rules": _priority_rules(item.get("priority_rules"), default["priority_rules"]),
        }

    low_values = values.get("low_trust")
    low_values = low_values if isinstance(low_values, dict) else {}
    low_defaults = defaults["low_trust"]
    return {
        "schema_version": 1,
        "capacity_combination_rule": "max",
        "cultivation_ranks": ranks,
        "membership_identities": identities,
        "low_trust": {
            "enabled": _bool(low_values.get("enabled"), low_defaults["enabled"]),
            "checkin_threshold": _int(low_values.get("checkin_threshold"), low_defaults["checkin_threshold"], 0, 100_000),
            "successful_order_exempt": _bool(low_values.get("successful_order_exempt"), low_defaults["successful_order_exempt"]),
            "referral_count_threshold": _int(low_values.get("referral_count_threshold"), low_defaults["referral_count_threshold"], 0, 1_000_000),
            "successful_invitee_rate_percent_threshold": _int(low_values.get("successful_invitee_rate_percent_threshold"), low_defaults["successful_invitee_rate_percent_threshold"], 0, 100),
            "trusted_priority_bonus": _int(low_values.get("trusted_priority_bonus"), low_defaults["trusted_priority_bonus"], 0, 500),
            "new_user_generation_threshold": _int(low_values.get("new_user_generation_threshold"), low_defaults["new_user_generation_threshold"], 0, 10_000),
            "new_user_base_priority": _int(low_values.get("new_user_base_priority"), low_defaults["new_user_base_priority"], 0, 500),
        },
    }


def validate_user_tier_policy_config(config: dict[str, Any]) -> None:
    ranks = config["cultivation_ranks"]
    for lower_key, higher_key in zip(CULTIVATION_RANKS[1:-1], CULTIVATION_RANKS[2:]):
        lower = ranks[lower_key]
        higher = ranks[higher_key]
        for field in ("invitations", "checkins", "generations"):
            if higher["upgrade"][field] < lower["upgrade"][field]:
                raise ValueError(f"{higher_key}的{field}门槛不能低于{lower_key}")
        for field in ("checkin_credits", "flashback_bottles"):
            if higher["benefits"][field] < lower["benefits"][field]:
                raise ValueError(f"{higher_key}的{field}权益不能低于{lower_key}")
        for field in ("resolutions", "durations"):
            if not set(lower["video"][field]).issubset(higher["video"][field]):
                raise ValueError(f"{higher_key}的{field}不能少于{lower_key}")

    identities = config["membership_identities"]
    for lower_key, higher_key in zip(MEMBERSHIP_IDENTITIES[:-1], MEMBERSHIP_IDENTITIES[1:]):
        lower = identities[lower_key]
        higher = identities[higher_key]
        for field in ("checkin_bonus", "concurrent_tasks", "favorite_limit", "flashback_bottles"):
            if higher["benefits"][field] < lower["benefits"][field]:
                raise ValueError(f"{higher_key}的{field}权益不能低于{lower_key}")
        for field in ("resolutions", "durations"):
            if not set(lower["video"][field]).issubset(higher["video"][field]):
                raise ValueError(f"{higher_key}的{field}不能少于{lower_key}")


def get_rank_policy(config: dict[str, Any], rank: str | None) -> dict[str, Any]:
    normalized = normalize_user_tier_policy_config(config)
    if rank in LEGACY_HIGH_RANKS:
        rank = "元婴期"
    return normalized["cultivation_ranks"].get(rank or "", normalized["cultivation_ranks"]["凡人"])


def get_identity_policy(config: dict[str, Any], identity: str | None) -> dict[str, Any]:
    normalized = normalize_user_tier_policy_config(config)
    return normalized["membership_identities"].get(identity or "", normalized["membership_identities"]["外门弟子"])


def get_priority_for_usage(rules: list[dict[str, Any]], usage: int) -> int:
    for rule in rules:
        limit = rule["daily_usage_lt"]
        if limit is None or usage < limit:
            return int(rule["priority"])
    return 0


def resolve_flashback_limit(config: dict[str, Any], rank: str | None, identity: str | None) -> int:
    return max(
        get_rank_policy(config, rank)["benefits"]["flashback_bottles"],
        get_identity_policy(config, identity)["benefits"]["flashback_bottles"],
    )


def resolve_effective_identity(user: Any, *, now: datetime | None = None) -> str:
    identity = getattr(user, "current_identity", None) or "外门弟子"
    if identity == "外门弟子":
        return identity
    expires_at = getattr(user, "identity_expire_at", None)
    comparison_now = now
    if comparison_now is None:
        comparison_now = datetime.now(tz=expires_at.tzinfo) if expires_at is not None and expires_at.tzinfo else datetime.now()
    if expires_at is not None and expires_at <= comparison_now:
        return "外门弟子"
    return identity if identity in MEMBERSHIP_IDENTITIES else "外门弟子"


def resolve_video_permissions(config: dict[str, Any], rank: str | None, identity: str | None) -> tuple[list[str], list[str]]:
    rank_video = get_rank_policy(config, rank)["video"]
    identity_video = get_identity_policy(config, identity)["video"]
    resolutions = [value for value in VIDEO_RESOLUTIONS if value in set(rank_video["resolutions"] + identity_video["resolutions"])]
    durations = [value for value in VIDEO_DURATIONS if value in set(rank_video["durations"] + identity_video["durations"])]
    return resolutions, durations


def _build_response(config: Any, updated_at: datetime | None) -> dict[str, Any]:
    return {
        "key": USER_TIER_POLICY_CONFIG_KEY,
        "config": normalize_user_tier_policy_config(config),
        "updated_at": updated_at,
    }


async def load_user_tier_policy_config_payload(db: AsyncSession) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    result = await db.execute(select(RuntimeCheckpoint).where(RuntimeCheckpoint.key == USER_TIER_POLICY_CONFIG_KEY))
    checkpoint = result.scalar_one_or_none()
    return _build_response(checkpoint.value if checkpoint else {}, checkpoint.updated_at if checkpoint else None)


async def save_user_tier_policy_config_payload(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    from src.database.models import RuntimeCheckpoint

    config = normalize_user_tier_policy_config(payload)
    validate_user_tier_policy_config(config)
    result = await db.execute(
        select(RuntimeCheckpoint).where(RuntimeCheckpoint.key == USER_TIER_POLICY_CONFIG_KEY).with_for_update()
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        checkpoint = RuntimeCheckpoint(key=USER_TIER_POLICY_CONFIG_KEY, value=config)
        db.add(checkpoint)
    else:
        checkpoint.value = config
    await db.commit()
    await db.refresh(checkpoint)
    return _build_response(checkpoint.value, checkpoint.updated_at)


async def resolve_user_flashback_limit(db: AsyncSession, user_id: int) -> int:
    from src.database.models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return DEFAULT_USER_TIER_POLICY_CONFIG["cultivation_ranks"]["凡人"]["benefits"]["flashback_bottles"]
    payload = await load_user_tier_policy_config_payload(db)
    return resolve_flashback_limit(
        payload["config"],
        getattr(user, "user_group", None),
        resolve_effective_identity(user),
    )


async def load_user_tier_policy_config() -> dict[str, Any]:
    from src.database.core import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            payload = await load_user_tier_policy_config_payload(db)
        return payload["config"]
    except Exception:
        logger.warning("user_tier_policy_load_failed_using_defaults", exc_info=True)
        return deepcopy(DEFAULT_USER_TIER_POLICY_CONFIG)
