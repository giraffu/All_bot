from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.database.models import User


async def authenticate_and_get_user_flow(
    *,
    init_data: str | None,
    widget_data: dict | None,
    verify_telegram_webapp_initdata_func: Callable[[str], dict | None],
    verify_telegram_authorization_func: Callable[[dict], bool],
    build_telegram_auth_profile_func,
    get_or_create_user_by_telegram_func,
    get_user_detailed_stats_func: Callable[[int], Awaitable[dict]],
    invalid_signature_error_factory: Callable[[str], Exception],
) -> tuple[User, dict]:
    if init_data:
        user_data = verify_telegram_webapp_initdata_func(init_data)
        if not user_data:
            raise invalid_signature_error_factory(
                "Invalid Telegram WebApp authentication signature."
            )
        profile = build_telegram_auth_profile_func(user_data)
    elif widget_data:
        if (
            not widget_data.get("id")
            or not widget_data.get("hash")
            or not widget_data.get("auth_date")
        ):
            raise invalid_signature_error_factory(
                "Missing required fields for Login Widget auth."
            )

        if not verify_telegram_authorization_func(widget_data):
            raise invalid_signature_error_factory(
                "Invalid Telegram authentication signature."
            )
        profile = build_telegram_auth_profile_func(widget_data)
    else:
        raise invalid_signature_error_factory("No authentication data provided.")

    user, _is_new = await get_or_create_user_by_telegram_func(
        tg_id=profile.tg_id,
        username=profile.username,
        full_name=profile.full_name,
        language_code=profile.language_code,
    )
    stats = await get_user_detailed_stats_func(user.telegram_id)
    return user, stats


async def authenticate_user_by_password_flow(
    *,
    username: str,
    password: str,
    client_ip: str,
    redis,
    session_factory,
    build_login_rate_limit_keys_func: Callable[..., tuple[str, str]],
    is_rate_limited_func,
    authenticate_password_credentials_func,
    verify_password_func,
    increment_rate_limit_func,
    check_web_access_func: Callable[[int], Awaitable[bool]],
    clear_rate_limit_func,
    get_user_detailed_stats_func: Callable[[int], Awaitable[dict]],
    rate_limit_error_factory: Callable[[str], Exception],
    invalid_credentials_error_factory: Callable[[str], Exception],
    insufficient_permission_error_factory: Callable[[str], Exception],
    check_script: str,
    incr_script: str,
) -> tuple[User, dict]:
    ip_key, user_key = build_login_rate_limit_keys_func(
        client_ip=client_ip,
        username=username,
    )

    if await is_rate_limited_func(
        redis=redis,
        ip_key=ip_key,
        user_key=user_key,
        max_attempts=5,
        check_script=check_script,
    ):
        raise rate_limit_error_factory("请求过于频繁，请稍后再试。")

    async with session_factory() as session:
        login_attempt = await authenticate_password_credentials_func(
            session=session,
            username=username,
            password=password,
            verify_password_func=verify_password_func,
        )

        if not login_attempt.is_valid or login_attempt.user is None:
            await increment_rate_limit_func(
                redis=redis,
                ip_key=ip_key,
                user_key=user_key,
                expire_seconds=900,
                incr_script=incr_script,
            )
            raise invalid_credentials_error_factory("道号或密咒错误，或尝试次数过多。")

        user = login_attempt.user
        if not await check_web_access_func(user.id):
            raise insufficient_permission_error_factory(
                "权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录 Web 端"
            )

        await clear_rate_limit_func(redis=redis, ip_key=ip_key, user_key=user_key)
        stats = await get_user_detailed_stats_func(user.telegram_id)
        return user, stats


async def bind_user_password_flow(
    *,
    user_id: int,
    username: str,
    password: str,
    client_ip: str,
    redis,
    session_factory,
    build_bind_rate_limit_keys_func: Callable[..., tuple[str, str]],
    is_rate_limited_func,
    get_bindable_user_func,
    check_web_access_func: Callable[[int], Awaitable[bool]],
    bind_password_to_user_func,
    get_password_hash_func,
    increment_rate_limit_func,
    clear_rate_limit_func,
    blacklist_password_version_func,
    rate_limit_error_factory: Callable[[str], Exception],
    auth_core_error_factory: Callable[[str], Exception],
    insufficient_permission_error_factory: Callable[[str], Exception],
    check_script: str,
    incr_script: str,
) -> None:
    ip_key, user_key = build_bind_rate_limit_keys_func(
        client_ip=client_ip,
        user_id=user_id,
    )

    if await is_rate_limited_func(
        redis=redis,
        ip_key=ip_key,
        user_key=user_key,
        max_attempts=5,
        check_script=check_script,
    ):
        raise rate_limit_error_factory("操作过于频繁，请稍后再试。")

    async with session_factory() as session:
        user = await get_bindable_user_func(
            session=session,
            user_id=user_id,
            check_web_access_func=check_web_access_func,
            user_not_found_error_factory=lambda: auth_core_error_factory("用户不存在。"),
            insufficient_permission_error_factory=lambda: insufficient_permission_error_factory(
                "权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能绑定 Web 端账号"
            ),
        )

        try:
            previous_password_version = await bind_password_to_user_func(
                session=session,
                user=user,
                username=username,
                password=password,
                get_password_hash_func=get_password_hash_func,
            )
        except IntegrityError:
            await session.rollback()
            await increment_rate_limit_func(
                redis=redis,
                ip_key=ip_key,
                user_key=user_key,
                expire_seconds=900,
                incr_script=incr_script,
            )
            raise auth_core_error_factory("道号已被其他道友占用，请重新选择。")

        await session.commit()
        await clear_rate_limit_func(redis=redis, ip_key=ip_key, user_key=user_key)
        await blacklist_password_version_func(
            redis=redis,
            user_id=user.id,
            password_version=previous_password_version,
        )
