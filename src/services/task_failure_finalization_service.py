from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.core.task_core_finalization import finalize_task_failure_with_notice
from src.core.task_core_runtime import cancel_backend_task_best_effort


@dataclass(frozen=True, slots=True)
class TaskFailureFinalizationPolicy:
    refund_task_type: str
    explicit_user_message: str
    notice_failure_log_message: str


def build_credit_refund_suffix(cost: int) -> str:
    return f" 预扣的 {cost} 灵石已退回。" if cost > 0 else ""


def build_zombie_cleanup_user_message(cost: int) -> str:
    return (
        "您的任务由于等待/执行时间过长，已被系统自动清理。"
        + build_credit_refund_suffix(cost)
    )


def build_recovery_failure_policy(
    *, reason: str, chat_id: int | None
) -> TaskFailureFinalizationPolicy:
    return TaskFailureFinalizationPolicy(
        refund_task_type="refund_restart",
        explicit_user_message=reason,
        notice_failure_log_message=f"Failed to send refund notice to {chat_id}",
    )


def build_zombie_cleanup_failure_policy(
    *, cost: int, chat_id: int | None
) -> TaskFailureFinalizationPolicy:
    return TaskFailureFinalizationPolicy(
        refund_task_type="refund_zombie_cleanup",
        explicit_user_message=build_zombie_cleanup_user_message(cost),
        notice_failure_log_message=f"Failed to send zombie cleanup notice to {chat_id}",
    )


def build_task_failure_notice_sender(
    *,
    bot,
    chat_id: int | None,
) -> Callable[[str], Awaitable[None]] | None:
    if bot is None or not chat_id:
        return None

    async def _send_notice(message: str):
        from src.utils import robust_send_message

        await robust_send_message(bot, chat_id, message)

    return _send_notice


async def finalize_task_failure_for_task_record(
    *,
    registry_task_id: str,
    task_data: dict,
    policy: TaskFailureFinalizationPolicy,
    bot=None,
    logger_override,
    finalize_task_failure_with_notice_func=None,
):
    if finalize_task_failure_with_notice_func is None:
        finalize_task_failure_with_notice_func = finalize_task_failure_with_notice

    chat_id = task_data.get("chat_id")
    return await finalize_task_failure_with_notice_func(
        internal_user_id=task_data.get("user_id"),
        username=task_data.get("username"),
        cost=task_data.get("cost", 0),
        should_refund=task_data.get("cost", 0) > 0,
        registry_task_id=registry_task_id,
        refund_task_type=policy.refund_task_type,
        explicit_user_message=policy.explicit_user_message,
        send_user_notice_func=build_task_failure_notice_sender(
            bot=bot,
            chat_id=chat_id,
        ),
        logger_override=logger_override,
        notice_failure_log_message=policy.notice_failure_log_message,
    )


async def _finalize_task_record_with_policy(
    *,
    registry_task_id: str,
    task_data: dict,
    policy: TaskFailureFinalizationPolicy,
    bot=None,
    logger_override,
    backend_task_id: str | None = None,
    finalize_task_failure_for_task_record_func=None,
    cancel_backend_task_best_effort_func=None,
):
    if finalize_task_failure_for_task_record_func is None:
        finalize_task_failure_for_task_record_func = finalize_task_failure_for_task_record

    result = await finalize_task_failure_for_task_record_func(
        registry_task_id=registry_task_id,
        task_data=task_data,
        policy=policy,
        bot=bot,
        logger_override=logger_override,
    )
    if backend_task_id is None:
        return result

    if cancel_backend_task_best_effort_func is None:
        cancel_backend_task_best_effort_func = cancel_backend_task_best_effort

    cancelled = await cancel_backend_task_best_effort_func(
        backend_task_id=backend_task_id,
        registry_task_id=registry_task_id,
        logger_override=logger_override,
    )
    return result, cancelled


async def finalize_recovery_failure_for_task_record(
    *,
    registry_task_id: str,
    task_data: dict,
    reason: str,
    bot=None,
    logger_override,
    finalize_task_failure_for_task_record_func=None,
):
    policy = build_recovery_failure_policy(
        reason=reason,
        chat_id=task_data.get("chat_id"),
    )
    return await _finalize_task_record_with_policy(
        registry_task_id=registry_task_id,
        task_data=task_data,
        policy=policy,
        bot=bot,
        logger_override=logger_override,
        finalize_task_failure_for_task_record_func=(
            finalize_task_failure_for_task_record_func
        ),
    )


async def finalize_zombie_cleanup_for_task_record(
    *,
    registry_task_id: str,
    task_data: dict,
    bot=None,
    logger_override,
    finalize_task_failure_for_task_record_func=None,
    cancel_backend_task_best_effort_func=None,
):
    policy = build_zombie_cleanup_failure_policy(
        cost=task_data.get("cost", 0),
        chat_id=task_data.get("chat_id"),
    )
    return await _finalize_task_record_with_policy(
        registry_task_id=registry_task_id,
        task_data=task_data,
        policy=policy,
        bot=bot,
        logger_override=logger_override,
        backend_task_id=task_data.get("backend_task_id"),
        finalize_task_failure_for_task_record_func=(
            finalize_task_failure_for_task_record_func
        ),
        cancel_backend_task_best_effort_func=cancel_backend_task_best_effort_func,
    )
