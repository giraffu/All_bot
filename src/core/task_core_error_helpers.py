TASK_BUSY_ERROR_KEYWORDS = (
    "Circuit is open",
    "All connection attempts failed",
    "Connection refused",
    "timeout",
    "ConnectError",
)


def normalize_terminal_status(status: str | None) -> str | None:
    if status == "success":
        return "done"
    if status == "failed":
        return "error"
    return status


def is_task_backend_busy_error(error: Exception | str) -> bool:
    error_msg = error if isinstance(error, str) else str(error)
    error_type = "" if isinstance(error, str) else str(type(error))
    return any(keyword in error_msg for keyword in TASK_BUSY_ERROR_KEYWORDS) or (
        "CircuitBreaker" in error_type
    )


def build_failed_task_user_message(
    *,
    error: Exception,
    generic_error_prefix: str,
    refunded: bool,
    refund_suffix_mode: str = "if_refunded",
) -> str:
    error_msg = str(error)
    if is_task_backend_busy_error(error):
        user_msg = "当前服务器繁忙，请稍后再试"
    else:
        user_msg = f"{generic_error_prefix}：{error_msg}"

    if refund_suffix_mode == "always":
        user_msg += "，已退还灵石"
    elif refund_suffix_mode == "if_refunded" and refunded:
        user_msg += "，已退还灵石"
    return user_msg
