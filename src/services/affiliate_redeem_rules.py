import os
from decimal import Decimal, ROUND_HALF_UP

from config import BOT_TYPE

REDEEM_USDT_QUANT = Decimal("0.0001")
REDEEM_CREDITS_QUANT = Decimal("1")
AFFILIATE_REDEEM_ROUNDING_MODE = "FIXED_PACKAGE"
AFFILIATE_REDEEM_TYPE_CREDITS = "CREDITS"
AFFILIATE_REDEEM_TYPE_MEMBERSHIP = "MEMBERSHIP"
AFFILIATE_REDEEM_OPTION_FLEXIBLE_USDT = "FLEXIBLE_USDT"
AFFILIATE_REDEEM_SUCCESS = "SUCCESS"
AFFILIATE_MEMBERSHIP_REDEEM_ENABLED_ENV = "AFFILIATE_MEMBERSHIP_REDEEM_ENABLED"
MEMBERSHIP_SETTLEMENT_V2_ENABLED_ENV = "MEMBERSHIP_SETTLEMENT_V2_ENABLED"
AFFILIATE_MEMBERSHIP_REDEEM_RMB_TO_USDT_RATE = Decimal("6.8")
AFFILIATE_CREDITS_REDEEM_PACKAGES = (
    {"amount_usdt": Decimal("1.0000"), "credits": 130},
    {"amount_usdt": Decimal("3.0000"), "credits": 390},
    {"amount_usdt": Decimal("6.0000"), "credits": 780},
    {"amount_usdt": Decimal("10.0000"), "credits": 1800},
    {"amount_usdt": Decimal("15.0000"), "credits": 2700},
    {"amount_usdt": Decimal("20.0000"), "credits": 4000},
)
AFFILIATE_CREDITS_REDEEM_PACKAGE_MAP = {
    package["amount_usdt"]: int(package["credits"])
    for package in AFFILIATE_CREDITS_REDEEM_PACKAGES
}
AFFILIATE_CREDITS_REDEEM_ALLOWED_AMOUNTS_TEXT = "1、3、6、10、15、20 USDT"


def _convert_membership_rmb_price_to_usdt(amount_rmb: str) -> Decimal:
    return (Decimal(amount_rmb) / AFFILIATE_MEMBERSHIP_REDEEM_RMB_TO_USDT_RATE).quantize(
        REDEEM_USDT_QUANT,
        rounding=ROUND_HALF_UP,
    )


AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS = {
    "inner_30d": {
        "schema_version": "affiliate_membership_redeem_v2",
        "plan_id": 1,
        "plan_name": "内门弟子月卡",
        "display_name": "内门弟子 30 天",
        "target_identity": "内门弟子",
        "duration_days": 30,
        "redeem_amount_usdt": _convert_membership_rmb_price_to_usdt("30"),
        "reward_credits": 400,
        "grant_reward_credits": True,
        "allow_pure_credit_plan": False,
        "is_enabled": True,
    },
    "core_30d": {
        "schema_version": "affiliate_membership_redeem_v2",
        "plan_id": 2,
        "plan_name": "核心弟子月卡",
        "display_name": "核心弟子 30 天",
        "target_identity": "核心弟子",
        "duration_days": 30,
        "redeem_amount_usdt": _convert_membership_rmb_price_to_usdt("70"),
        "reward_credits": 1200,
        "grant_reward_credits": True,
        "allow_pure_credit_plan": False,
        "is_enabled": True,
    },
    "true_30d": {
        "schema_version": "affiliate_membership_redeem_v2",
        "plan_id": 3,
        "plan_name": "真传弟子月卡",
        "display_name": "真传弟子 30 天",
        "target_identity": "真传弟子",
        "duration_days": 30,
        "redeem_amount_usdt": _convert_membership_rmb_price_to_usdt("120"),
        "reward_credits": 3000,
        "grant_reward_credits": True,
        "allow_pure_credit_plan": False,
        "is_enabled": True,
    },
}


def _is_feature_enabled(name: str) -> bool:
    if BOT_TYPE == "TEST":
        test_value = os.getenv(f"{name}_TEST")
        if test_value not in (None, ""):
            return test_value.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_membership_settlement_v2_enabled() -> bool:
    return _is_feature_enabled(MEMBERSHIP_SETTLEMENT_V2_ENABLED_ENV)


def is_affiliate_membership_redeem_enabled() -> bool:
    return _is_feature_enabled(AFFILIATE_MEMBERSHIP_REDEEM_ENABLED_ENV)


def normalize_redeem_amount_usdt(amount_usdt: Decimal) -> Decimal:
    normalized = Decimal(str(amount_usdt)).quantize(REDEEM_USDT_QUANT)
    if normalized <= 0:
        raise ValueError("amount_usdt must be positive")
    return normalized


def build_exchange_rate_snapshot(amount_usdt: Decimal, credits_granted: int) -> str:
    return f"{amount_usdt:.4f} USDT = {credits_granted} credits"


def get_affiliate_credits_redeem_package(amount_usdt: Decimal) -> tuple[Decimal, int]:
    normalized = normalize_redeem_amount_usdt(amount_usdt)
    credits = AFFILIATE_CREDITS_REDEEM_PACKAGE_MAP.get(normalized)
    if credits is None:
        raise ValueError(
            f"返佣兑灵石仅支持固定套餐：{AFFILIATE_CREDITS_REDEEM_ALLOWED_AMOUNTS_TEXT}"
        )
    return normalized, credits


def calculate_redeem_credits(amount_usdt: Decimal) -> int:
    _, credits = get_affiliate_credits_redeem_package(amount_usdt)
    return credits


def list_affiliate_credits_redeem_packages() -> tuple[dict, ...]:
    return tuple(
        {
            "amount_usdt": Decimal(str(package["amount_usdt"])).quantize(REDEEM_USDT_QUANT),
            "credits": int(package["credits"]),
        }
        for package in AFFILIATE_CREDITS_REDEEM_PACKAGES
    )


def get_membership_option(option_key: str) -> dict:
    option = AFFILIATE_MEMBERSHIP_REDEEM_OPTIONS.get(option_key)
    if option is None:
        raise ValueError("unsupported membership redeem option")
    return option
