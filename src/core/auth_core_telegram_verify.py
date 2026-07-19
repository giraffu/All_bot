import time


def build_telegram_data_check_string(params: dict) -> str:
    return "\n".join([f"{k}={v}" for k, v in sorted(params.items())])


def is_telegram_auth_date_fresh(
    auth_date,
    *,
    stale_log_message: str,
    logger,
    time_func=None,
    max_age_seconds: int = 900,
) -> bool:
    if time_func is None:
        time_func = time.time

    if not auth_date or time_func() - int(auth_date) > max_age_seconds:
        logger.error(stale_log_message)
        return False
    return True


def get_telegram_tokens_to_try(*, bot_token, logger) -> list[str]:
    tokens_to_try = [bot_token] if bot_token else []
    if not tokens_to_try:
        logger.error("No BOT_TOKEN configured!")
    return tokens_to_try
