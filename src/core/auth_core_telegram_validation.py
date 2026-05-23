import hashlib
import hmac
import json
import urllib.parse
from typing import Optional

from src.core.auth_core_telegram_verify import (
    build_telegram_data_check_string,
    get_telegram_tokens_to_try,
    is_telegram_auth_date_fresh,
)


def verify_telegram_authorization(
    data: dict,
    *,
    bot_token,
    bot_token_test,
    logger,
    build_data_check_string_func=None,
    get_tokens_to_try_func=None,
    is_auth_date_fresh_func=None,
) -> bool:
    """Verify the hash of the Telegram auth data (Widget format)."""
    if build_data_check_string_func is None:
        build_data_check_string_func = build_telegram_data_check_string
    if get_tokens_to_try_func is None:
        get_tokens_to_try_func = get_telegram_tokens_to_try
    if is_auth_date_fresh_func is None:
        is_auth_date_fresh_func = is_telegram_auth_date_fresh

    received_hash = data.pop("hash", None)
    if not received_hash:
        return False

    auth_date = data.get("auth_date")
    if not is_auth_date_fresh_func(
        auth_date,
        stale_log_message="Telegram auth_date is too old or missing (Replay attack prevention).",
        logger=logger,
    ):
        return False

    data_check_string = build_data_check_string_func(data)

    tokens_to_try = get_tokens_to_try_func(
        bot_token=bot_token,
        bot_token_test=bot_token_test,
        logger=logger,
    )
    if not tokens_to_try:
        return False

    for token in tokens_to_try:
        secret_key = hashlib.sha256(token.encode()).digest()
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(expected_hash, received_hash):
            return True

    return False


def verify_telegram_webapp_initdata(
    init_data: str,
    *,
    bot_token,
    bot_token_test,
    logger,
    build_data_check_string_func=None,
    get_tokens_to_try_func=None,
    is_auth_date_fresh_func=None,
) -> Optional[dict]:
    """
    Verify the initData string passed from Telegram Mini App.
    Returns parsed user dict if valid, else None.
    """
    if build_data_check_string_func is None:
        build_data_check_string_func = build_telegram_data_check_string
    if get_tokens_to_try_func is None:
        get_tokens_to_try_func = get_telegram_tokens_to_try
    if is_auth_date_fresh_func is None:
        is_auth_date_fresh_func = is_telegram_auth_date_fresh

    params = dict(urllib.parse.parse_qsl(init_data))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return None

    auth_date = params.get("auth_date")
    if not is_auth_date_fresh_func(
        auth_date,
        stale_log_message="Telegram WebApp auth_date is too old or missing.",
        logger=logger,
    ):
        return None

    data_check_string = build_data_check_string_func(params)

    tokens_to_try = get_tokens_to_try_func(
        bot_token=bot_token,
        bot_token_test=bot_token_test,
        logger=logger,
    )
    if not tokens_to_try:
        return None

    for token in tokens_to_try:
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_hash, received_hash):
            continue

        user_str = params.get("user")
        if not user_str:
            return None

        try:
            return json.loads(user_str)
        except Exception as exc:
            logger.error(f"Failed to parse user from initData: {exc}")
            return None

    return None
