from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.core.task_core import finalize_task_failure_with_notice


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
    finalize_task_failure_with_notice_func=finalize_task_failure_with_notice,
):
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
