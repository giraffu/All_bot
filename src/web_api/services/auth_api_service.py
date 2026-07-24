import logging

from fastapi import HTTPException, status

from src.core.auth_core import (
    AuthCoreError,
    InsufficientPermissionError,
    InvalidCredentialsError,
    InvalidSignatureError,
    RateLimitError,
    authenticate_and_get_user,
    authenticate_user_by_password,
    bind_user_password,
)
from src.services.auth_security_notification_service import (
    schedule_password_changed_notification,
    schedule_password_login_notification,
)
from src.services.permission_service import permission_service
from src.web_api.core.security import create_access_token
from src.web_api.presenters.user_presenter import (
    build_token_user_payload,
    build_user_response_from_auth_stats,
)

logger = logging.getLogger(__name__)

WEB_ACCESS_DENIED_MESSAGE = (
    "权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录 Web 端"
)


def extract_client_ip(request) -> str:
    return (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For")
        or request.client.host
        or "unknown"
    )


def build_auth_token_payload(*, user, stats, channel: str = "telegram") -> dict:
    access_token = create_access_token(
        subject=user.id,
        pwd_ver=user.password_version,
        channel=channel,
    )
    user_response_data = build_user_response_from_auth_stats(user, stats)
    return build_token_user_payload(
        access_token=access_token,
        user_response=user_response_data,
    )


async def login_telegram_payload(*, req) -> dict:
    try:
        init_data = req.initData
        widget_data = (
            req.model_dump(exclude_unset=True, exclude={"initData"})
            if not init_data
            else None
        )
        user, stats = await authenticate_and_get_user(
            init_data=init_data,
            widget_data=widget_data,
        )

        if not await permission_service.check_web_access(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=WEB_ACCESS_DENIED_MESSAGE,
            )

        return build_auth_token_payload(user=user, stats=stats)
    except InvalidSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error during Telegram login: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during authentication.",
        ) from exc


async def login_telegram_payment_payload(*, req) -> dict:
    try:
        init_data = req.initData
        widget_data = (
            req.model_dump(exclude_unset=True, exclude={"initData"})
            if not init_data
            else None
        )
        user, stats = await authenticate_and_get_user(
            init_data=init_data,
            widget_data=widget_data,
        )
        return build_auth_token_payload(
            user=user,
            stats=stats,
            channel="telegram_payment",
        )
    except InvalidSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error during Telegram payment login: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during authentication.",
        ) from exc


async def login_with_password_payload(*, req, request) -> dict:
    client_ip = extract_client_ip(request)

    try:
        user, stats = await authenticate_user_by_password(
            req.username,
            req.password,
            client_ip,
        )
        schedule_password_login_notification(user.telegram_id, client_ip)
        return build_auth_token_payload(user=user, stats=stats, channel="password")
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except RateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except InsufficientPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Error during password login: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during authentication.",
        ) from exc


async def bind_password_payload(*, req, request, current_user) -> dict:
    client_ip = extract_client_ip(request)

    try:
        await bind_user_password(current_user.id, req.username, req.password, client_ip)
        schedule_password_changed_notification(current_user.telegram_id)
        return {"status": "success", "message": "密咒设置成功。请使用新密咒重新登录。"}
    except InsufficientPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except RateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except AuthCoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "Error binding password for user %s: %s",
            current_user.id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during password binding.",
        ) from exc
