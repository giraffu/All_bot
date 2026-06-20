import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Tuple

from src.constants import MAX_CONCURRENT_TASKS
from src.core.billing_core_membership import DEFAULT_IDENTITY
from src.core.billing_core_membership import IDENTITY_PRIORITY
from src.core.billing_core_membership import IDENTITY_RATIO
from src.core.billing_core_membership import MembershipSettlementResult
from src.core.billing_core_membership import calculate_identity_conversion
from src.core.billing_core_membership import calculate_identity_manual_conversion
from src.core.billing_core_membership import calculate_membership_settlement
from src.core.exceptions import InsufficientCreditsError
from src.core.billing_core_membership import normalize_membership_identity

logger = logging.getLogger(__name__)
_configured_billing_core_providers = None
LOW_TIER_QUEUE_SIZE_LIMIT = 300


__all__ = [
    "BillingCoreDependencies",
    "BillingCoreProviders",
    "DEFAULT_IDENTITY",
    "IDENTITY_PRIORITY",
    "IDENTITY_RATIO",
    "LOW_TIER_QUEUE_SIZE_LIMIT",
    "MembershipSettlementResult",
    "build_default_billing_core_dependencies",
    "build_default_billing_core_providers",
    "configure_billing_core_providers",
    "get_default_billing_core_dependencies",
    "get_configured_billing_core_providers",
    "calculate_identity_conversion",
    "calculate_identity_manual_conversion",
    "calculate_membership_settlement",
    "check_and_deduct_credits",
    "check_concurrency_lock",
    "get_user_priority_and_identity",
    "normalize_membership_identity",
    "refund_credits",
    "release_concurrency_lock",
]


@dataclass(frozen=True)
class BillingCoreDependencies:
    get_system_status_func: Callable[[], Awaitable[dict[str, Any] | None]]
    get_user_identity_func: Callable[[int], Awaitable[str]]
    get_user_group_func: Callable[[int], Awaitable[str]]
    calculate_user_priority_func: Callable[[int], Awaitable[int]]
    increment_user_concurrency_func: Callable[[int], Awaitable[int]]
    decrement_user_concurrency_func: Callable[[int], Awaitable[int]]
    deduct_credits_func: Callable[..., Awaitable[Any]]
    add_credits_func: Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class BillingCoreProviders:
    get_system_status_func: Callable[[], Awaitable[dict[str, Any] | None]]
    get_permission_service_func: Callable[[], Any]
    get_redis_client_func: Callable[[], Any]
    get_quota_manager_func: Callable[[], Any]


def configure_billing_core_providers(
    providers: BillingCoreProviders,
) -> BillingCoreProviders:
    global _configured_billing_core_providers
    _configured_billing_core_providers = providers
    return providers


def get_configured_billing_core_providers() -> BillingCoreProviders | None:
    return _configured_billing_core_providers


def get_default_billing_core_providers() -> BillingCoreProviders:
    providers = get_configured_billing_core_providers()
    if providers is None:
        raise RuntimeError(
            "Billing core providers 未注册，请先在应用入口调用 configure_billing_core_providers(...)。"
        )
    return providers


def build_default_billing_core_providers(
    *,
    get_system_status_func,
    get_permission_service_func,
    get_redis_client_func,
    get_quota_manager_func,
) -> BillingCoreProviders:
    return BillingCoreProviders(
        get_system_status_func=get_system_status_func,
        get_permission_service_func=get_permission_service_func,
        get_redis_client_func=get_redis_client_func,
        get_quota_manager_func=get_quota_manager_func,
    )


def get_default_billing_core_dependencies(
    *,
    providers: BillingCoreProviders | None = None,
) -> BillingCoreDependencies:
    return build_default_billing_core_dependencies(
        providers=providers or get_default_billing_core_providers()
    )


def build_default_billing_core_dependencies(
    *,
    providers: BillingCoreProviders,
) -> BillingCoreDependencies:
    permission_service_impl = providers.get_permission_service_func()
    redis_client_impl = providers.get_redis_client_func()
    quota_manager_impl = providers.get_quota_manager_func()

    return BillingCoreDependencies(
        get_system_status_func=providers.get_system_status_func,
        get_user_identity_func=permission_service_impl.get_user_identity,
        get_user_group_func=permission_service_impl.get_user_group,
        calculate_user_priority_func=permission_service_impl.calculate_user_priority,
        increment_user_concurrency_func=redis_client_impl.increment_user_concurrency,
        decrement_user_concurrency_func=redis_client_impl.decrement_user_concurrency,
        deduct_credits_func=quota_manager_impl.deduct_credits,
        add_credits_func=quota_manager_impl.add_credits,
    )


async def check_concurrency_lock(
    internal_user_id: int,
    *,
    dependencies: BillingCoreDependencies | None = None,
) -> Tuple[bool, str]:
    """
    检查用户并发锁及队列限制。
    返回 (是否允许执行, 错误信息)
    """
    dependencies = dependencies or get_default_billing_core_dependencies()

    # 1. 检查队列长度与身份
    identity_str = await dependencies.get_user_identity_func(internal_user_id)
    if identity_str == "外门弟子":
        # 补充检查修为境界：凡人、练气期不可突破排队限制，筑基期及以上可以
        user_group = await dependencies.get_user_group_func(internal_user_id)
        if user_group in ["凡人", "练气期"]:
            sys_status = await dependencies.get_system_status_func()
            if (
                sys_status
                and sys_status.get("queue_size", 0) > LOW_TIER_QUEUE_SIZE_LIMIT
            ):
                return (
                    False,
                    (
                        "⚠️ **服务器繁忙**\n\n"
                        f"当前排队任务已超过 {LOW_TIER_QUEUE_SIZE_LIMIT} 个，"
                        "为了保证服务稳定性，**练气期及以下外门弟子**暂不可提交新任务。\n\n"
                        "💡 请稍后再试，或努力提升修为至**筑基期**，"
                        "也可通过「个人中心」升级至内门弟子及以上身份获取特权！"
                    ),
                )

    # 2. 原有并发锁检查
    active_tasks = await dependencies.increment_user_concurrency_func(internal_user_id)
    if active_tasks > MAX_CONCURRENT_TASKS:
        await dependencies.decrement_user_concurrency_func(internal_user_id)
        return (
            False,
            f"您当前已有 {MAX_CONCURRENT_TASKS} 个任务正在处理中，请等待其中一个完成后再试！",
        )
    return True, ""


async def release_concurrency_lock(
    internal_user_id: int,
    *,
    dependencies: BillingCoreDependencies | None = None,
):
    """释放用户并发锁"""
    dependencies = dependencies or get_default_billing_core_dependencies()
    await dependencies.decrement_user_concurrency_func(internal_user_id)


async def check_and_deduct_credits(
    internal_user_id: int,
    cost: int,
    task_type: str,
    username: str = None,
    *,
    dependencies: BillingCoreDependencies | None = None,
) -> Tuple[bool, str]:
    """
    检查灵石余额并扣除。
    返回 (是否成功, 错误信息)
    """
    if cost <= 0:
        return True, ""

    dependencies = dependencies or get_default_billing_core_dependencies()
    try:
        await dependencies.deduct_credits_func(
            internal_user_id, cost, username=username, task_type=task_type
        )
        return True, ""
    except InsufficientCreditsError as e:
        return (
            False,
            f"🚫 **灵石不足**\n\n当前余额: `{e.current}` 灵石\n本次需要: `{e.cost}` 灵石\n请获取更多灵石。",
        )
    except Exception as e:
        logger.error(f"Error deducting credits for user {internal_user_id}: {e}")
        return False, "系统错误，扣费失败"


async def refund_credits(
    internal_user_id: int,
    cost: int,
    task_type: str = "refund",
    username: str = None,
    *,
    dependencies: BillingCoreDependencies | None = None,
):
    """退还灵石"""
    if cost > 0:
        dependencies = dependencies or get_default_billing_core_dependencies()
        await dependencies.add_credits_func(
            internal_user_id, cost, username=username, task_type=task_type
        )


async def get_user_priority_and_identity(
    internal_user_id: int,
    *,
    dependencies: BillingCoreDependencies | None = None,
) -> Tuple[int, str, str]:
    """
    获取用户的优先级、身份和组。
    """
    dependencies = dependencies or get_default_billing_core_dependencies()

    priority = await dependencies.calculate_user_priority_func(internal_user_id)
    identity_str = await dependencies.get_user_identity_func(internal_user_id)
    user_group = await dependencies.get_user_group_func(internal_user_id)
    return priority, identity_str, user_group
