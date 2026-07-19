import logging
from typing import Optional

from src.runtime_environment import require_env
from src.core.auth_core_dependencies import build_auth_core_dependencies
from src.core.auth_core_flows import (
    authenticate_and_get_user_flow,
    authenticate_user_by_password_flow,
    bind_user_password_flow,
)
from src.core.auth_core_password_binding import bind_password_to_user, get_bindable_user
from src.core.auth_core_password_hash import (
    get_password_hash as get_password_hash_impl,
    verify_password as verify_password_impl,
)
from src.core.auth_core_password_login import authenticate_password_credentials
from src.core.auth_core_telegram_auth import build_telegram_auth_profile
from src.core.auth_core_telegram_validation import (
    verify_telegram_authorization as verify_telegram_authorization_impl,
    verify_telegram_webapp_initdata as verify_telegram_webapp_initdata_impl,
)
from src.core.auth_core_telegram_verify import (
    build_telegram_data_check_string,
    get_telegram_tokens_to_try,
    is_telegram_auth_date_fresh,
)
from src.core.auth_core_password_version import blacklist_password_version
from src.core.auth_core_rate_limit import (
    build_bind_rate_limit_keys,
    build_login_rate_limit_keys,
    clear_rate_limit,
    increment_rate_limit,
    is_rate_limited,
)

logger = logging.getLogger(__name__)
BOT_TOKEN = require_env("BOT_TOKEN")


class AuthCoreError(Exception):
    pass


class InvalidSignatureError(AuthCoreError):
    pass


class InvalidCredentialsError(AuthCoreError):
    pass


class InsufficientPermissionError(AuthCoreError):
    pass


class RateLimitError(AuthCoreError):
    pass


CHECK_RATE_LIMIT_SCRIPT = """
local ip_key = KEYS[1]
local user_key = KEYS[2]
local max_attempts = tonumber(ARGV[1])

local ip_attempts = tonumber(redis.call('GET', ip_key) or '0')
local user_attempts = tonumber(redis.call('GET', user_key) or '0')

if ip_attempts >= max_attempts or user_attempts >= max_attempts then
    return 1
end
return 0
"""

INCR_RATE_LIMIT_SCRIPT = """
local ip_key = KEYS[1]
local user_key = KEYS[2]
local expire_time = tonumber(ARGV[1])

local ip_new = redis.call('INCR', ip_key)
if ip_new == 1 then
    redis.call('EXPIRE', ip_key, expire_time)
end

local user_new = redis.call('INCR', user_key)
if user_new == 1 then
    redis.call('EXPIRE', user_key, expire_time)
end
return 1
"""


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    return await verify_password_impl(plain_password, hashed_password)


async def get_password_hash(password: str) -> str:
    return await get_password_hash_impl(password)


def verify_telegram_authorization(data: dict) -> bool:
    return verify_telegram_authorization_impl(
        data,
        bot_token=BOT_TOKEN,
        logger=logger,
        build_data_check_string_func=build_telegram_data_check_string,
        get_tokens_to_try_func=get_telegram_tokens_to_try,
        is_auth_date_fresh_func=is_telegram_auth_date_fresh,
    )


def verify_telegram_webapp_initdata(init_data: str) -> Optional[dict]:
    return verify_telegram_webapp_initdata_impl(
        init_data,
        bot_token=BOT_TOKEN,
        logger=logger,
        build_data_check_string_func=build_telegram_data_check_string,
        get_tokens_to_try_func=get_telegram_tokens_to_try,
        is_auth_date_fresh_func=is_telegram_auth_date_fresh,
    )


async def authenticate_and_get_user(
    init_data: Optional[str] = None, widget_data: Optional[dict] = None
) -> tuple[object, dict]:
    dependencies = build_auth_core_dependencies()
    return await authenticate_and_get_user_flow(
        init_data=init_data,
        widget_data=widget_data,
        verify_telegram_webapp_initdata_func=verify_telegram_webapp_initdata,
        verify_telegram_authorization_func=verify_telegram_authorization,
        build_telegram_auth_profile_func=build_telegram_auth_profile,
        get_or_create_user_by_telegram_func=(
            dependencies.get_or_create_user_by_telegram_func
        ),
        get_user_detailed_stats_func=dependencies.get_user_detailed_stats_func,
        invalid_signature_error_factory=InvalidSignatureError,
    )


async def authenticate_user_by_password(
    username: str, password: str, client_ip: str
) -> tuple[object, dict]:
    dependencies = build_auth_core_dependencies()
    return await authenticate_user_by_password_flow(
        username=username,
        password=password,
        client_ip=client_ip,
        redis=dependencies.redis,
        session_factory=dependencies.session_factory,
        build_login_rate_limit_keys_func=build_login_rate_limit_keys,
        is_rate_limited_func=is_rate_limited,
        authenticate_password_credentials_func=authenticate_password_credentials,
        verify_password_func=verify_password,
        get_user_by_username_func=dependencies.get_user_by_username_func,
        increment_rate_limit_func=increment_rate_limit,
        check_web_access_func=dependencies.check_web_access_func,
        clear_rate_limit_func=clear_rate_limit,
        get_user_detailed_stats_func=dependencies.get_user_detailed_stats_func,
        rate_limit_error_factory=RateLimitError,
        invalid_credentials_error_factory=InvalidCredentialsError,
        insufficient_permission_error_factory=InsufficientPermissionError,
        check_script=CHECK_RATE_LIMIT_SCRIPT,
        incr_script=INCR_RATE_LIMIT_SCRIPT,
    )


async def bind_user_password(
    user_id: int, username: str, password: str, client_ip: str
) -> None:
    dependencies = build_auth_core_dependencies()
    return await bind_user_password_flow(
        user_id=user_id,
        username=username,
        password=password,
        client_ip=client_ip,
        redis=dependencies.redis,
        session_factory=dependencies.session_factory,
        build_bind_rate_limit_keys_func=build_bind_rate_limit_keys,
        is_rate_limited_func=is_rate_limited,
        get_bindable_user_func=get_bindable_user,
        check_web_access_func=dependencies.check_web_access_func,
        bind_password_to_user_func=bind_password_to_user,
        get_password_hash_func=get_password_hash,
        get_user_by_id_func=dependencies.get_user_by_id_func,
        increment_rate_limit_func=increment_rate_limit,
        clear_rate_limit_func=clear_rate_limit,
        blacklist_password_version_func=blacklist_password_version,
        rate_limit_error_factory=RateLimitError,
        auth_core_error_factory=AuthCoreError,
        insufficient_permission_error_factory=InsufficientPermissionError,
        check_script=CHECK_RATE_LIMIT_SCRIPT,
        incr_script=INCR_RATE_LIMIT_SCRIPT,
    )
