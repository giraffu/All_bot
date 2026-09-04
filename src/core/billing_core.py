import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Tuple

from src.constants import CONCURRENT_TASK_LIMITS_BY_IDENTITY
from src.constants import MAX_CONCURRENT_TASKS
from src.core.billing_core_membership import DEFAULT_IDENTITY
from src.core.billing_core_membership import IDENTITY_PRIORITY
from src.core.billing_core_membership import IDENTITY_RATIO
from src.core.billing_core_membership import MembershipSettlementResult
from src.core.billing_core_membership import calculate_identity_conversion
from src.core.billing_core_membership import calculate_identity_manual_conversion
from src.core.billing_core_membership import calculate_membership_settlement
from src.core.billing_core_membership import normalize_membership_identity
from src.core.exceptions import InsufficientCreditsError
from src.domain_config.worker_pool_registry import get_worker_pool_profile

logger = logging.getLogger(__name__)
_configured_billing_core_providers = None
LOW_TIER_PENDING_PER_WORKER_LIMIT = 50


__all__ = [
    "BillingCoreDependencies",
    "BillingCoreProviders",
    "DEFAULT_IDENTITY",
    "IDENTITY_PRIORITY",
    "IDENTITY_RATIO",
    "LOW_TIER_PENDING_PER_WORKER_LIMIT",
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
    "get_concurrent_task_limit_for_identity",
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
    rollback_user_concurrency_acquire_func: Callable[..., Awaitable[int]]
    deduct_credits_func: Callable[..., Awaitable[Any]]
    add_credits_func: Callable[..., Awaitable[Any]]
    get_concurrent_task_limit_func: Callable[[str], Awaitable[int]] | None = None
    is_queue_pressure_exempt_func: Callable[[str, str], Awaitable[bool]] | None = None


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
        rollback_user_concurrency_acquire_func=(
            redis_client_impl.rollback_user_concurrency_acquire
        ),
        deduct_credits_func=quota_manager_impl.deduct_credits,
        add_credits_func=quota_manager_impl.add_credits,
        get_concurrent_task_limit_func=getattr(
            permission_service_impl, "get_concurrent_task_limit", None
        ),
        is_queue_pressure_exempt_func=getattr(
            permission_service_impl, "is_queue_pressure_exempt", None
        ),
    )


def get_concurrent_task_limit_for_identity(identity: str | None) -> int:
    normalized_identity = normalize_membership_identity(identity)
    return CONCURRENT_TASK_LIMITS_BY_IDENTITY.get(
        normalized_identity,
        MAX_CONCURRENT_TASKS,
    )


async def check_concurrency_lock(
    internal_user_id: int,
    idempotency_key: str | None = None,
    *,
    task_type: str | None = None,
    dependencies: BillingCoreDependencies | None = None,
) -> Tuple[bool, str]:
    """
    检查用户并发锁及队列限制。
    返回 (是否允许执行, 错误信息)
    """
    dependencies = dependencies or get_default_billing_core_dependencies()

    # 1. 检查目标执行池的排队压力与身份
    identity_str = await dependencies.get_user_identity_func(internal_user_id)
    normalized_identity = normalize_membership_identity(identity_str)
    concurrent_limit_loader = getattr(
        dependencies, "get_concurrent_task_limit_func", None
    )
    if concurrent_limit_loader is not None:
        concurrent_task_limit = await concurrent_limit_loader(
            normalized_identity
        )
    else:
        concurrent_task_limit = get_concurrent_task_limit_for_identity(normalized_identity)

    queue_exemption_loader = getattr(
        dependencies, "is_queue_pressure_exempt_func", None
    )
    if queue_exemption_loader is not None:
        user_group = await dependencies.get_user_group_func(internal_user_id)
        queue_pressure_exempt = await queue_exemption_loader(
            user_group, normalized_identity
        )
    elif normalized_identity == "外门弟子":
        user_group = await dependencies.get_user_group_func(internal_user_id)
        queue_pressure_exempt = user_group not in ["凡人", "练气期"]
    else:
        queue_pressure_exempt = True
    if not queue_pressure_exempt:
            profile = get_worker_pool_profile(task_type)
            if profile is None:
                logger.warning(
                    "queue_admission_fail_open reason=unmapped_task_type task_type=%s",
                    task_type,
                )
            else:
                try:
                    sys_status = await dependencies.get_system_status_func()
                except Exception:
                    logger.warning(
                        "queue_admission_fail_open reason=status_request_failed "
                        "task_type=%s profile=%s",
                        task_type,
                        profile.name,
                        exc_info=True,
                    )
                    sys_status = None

                pressure_by_profile = (
                    sys_status.get("queue_pressure_by_worker_profile")
                    if isinstance(sys_status, dict)
                    else None
                )
                pressure = (
                    pressure_by_profile.get(profile.name)
                    if isinstance(pressure_by_profile, dict)
                    else None
                )
                try:
                    pending_count = int(pressure["pending_count"])
                    accepting_worker_count = int(
                        pressure["accepting_worker_count"]
                    )
                    if pending_count < 0 or accepting_worker_count < 0:
                        raise ValueError("queue pressure counts must be non-negative")
                except (KeyError, TypeError, ValueError):
                    logger.warning(
                        "queue_admission_fail_open reason=invalid_pool_metrics "
                        "task_type=%s profile=%s",
                        task_type,
                        profile.name,
                    )
                else:
                    effective_worker_count = max(accepting_worker_count, 1)
                    projected_pending_count = pending_count + 1
                    if projected_pending_count > (
                        LOW_TIER_PENDING_PER_WORKER_LIMIT
                        * effective_worker_count
                    ):
                        return (
                            False,
                            (
                                "⚠️ **服务器繁忙**\n\n"
                                "当前任务类型排队已达到"
                                f"每台可接单服务器 {LOW_TIER_PENDING_PER_WORKER_LIMIT} 个"
                                "的容量上限，**练气期及以下外门弟子**暂不可提交新任务。\n\n"
                                "💡 请稍后再试，或努力提升修为至**筑基期**，"
                                "也可通过「个人中心」升级至内门弟子及以上身份获取特权！"
                            ),
                        )

    # 2. 原有并发锁检查
    increment_kwargs = (
        {"idempotency_key": idempotency_key} if idempotency_key else {}
    )
    increment_result = await dependencies.increment_user_concurrency_func(
        internal_user_id,
        **increment_kwargs,
    )
    if isinstance(increment_result, tuple):
        active_tasks, acquired_new = increment_result
    else:
        active_tasks, acquired_new = increment_result, True
    if idempotency_key and not acquired_new:
        return True, ""
    if active_tasks > concurrent_task_limit:
        if idempotency_key:
            await dependencies.rollback_user_concurrency_acquire_func(
                internal_user_id,
                idempotency_key=idempotency_key,
            )
        else:
            await dependencies.decrement_user_concurrency_func(internal_user_id)
        return (
            False,
            f"您当前已有 {concurrent_task_limit} 个任务正在处理中，请等待其中一个完成后再试！",
        )
    return True, ""


async def release_concurrency_lock(
    internal_user_id: int,
    idempotency_key: str | None = None,
    *,
    dependencies: BillingCoreDependencies | None = None,
):
    """释放用户并发锁"""
    dependencies = dependencies or get_default_billing_core_dependencies()
    kwargs = {"idempotency_key": idempotency_key} if idempotency_key else {}
    await dependencies.decrement_user_concurrency_func(internal_user_id, **kwargs)


async def check_and_deduct_credits(
    internal_user_id: int,
    cost: int,
    task_type: str,
    username: str = None,
    idempotency_key: str | None = None,
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
        kwargs = {"idempotency_key": idempotency_key} if idempotency_key else {}
        await dependencies.deduct_credits_func(
            internal_user_id,
            cost,
            username=username,
            task_type=task_type,
            **kwargs,
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
    idempotency_key: str | None = None,
    *,
    dependencies: BillingCoreDependencies | None = None,
) -> bool:
    """退还灵石"""
    if cost <= 0:
        return False

    dependencies = dependencies or get_default_billing_core_dependencies()
    kwargs: dict[str, Any] = {
        "username": username,
        "task_type": task_type,
    }
    if idempotency_key:
        kwargs["idempotency_key"] = idempotency_key
        kwargs["extra_info"] = {"credit_idempotency_key": idempotency_key}

    result = await dependencies.add_credits_func(internal_user_id, cost, **kwargs)
    if idempotency_key:
        old_balance = getattr(result, "old_balance", None)
        new_balance = getattr(result, "new_balance", None)
        if isinstance(old_balance, int) and isinstance(new_balance, int):
            return new_balance != old_balance
    return True


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
