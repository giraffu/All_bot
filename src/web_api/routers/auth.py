import logging

from fastapi import APIRouter, HTTPException, status, Request, Depends

from src.core.auth_core import (
    InvalidSignatureError,
    authenticate_and_get_user,
    authenticate_user_by_password,
    bind_user_password,
    InvalidCredentialsError,
    RateLimitError,
    InsufficientPermissionError,
    AuthCoreError
)
from src.services.permission_service import permission_service
from src.web_api.core.security import create_access_token
from src.web_api.schemas.auth_schema import (
    InvitationRechargeStats,
    TelegramLoginRequest,
    UserResponse,
    UserLoginRequest,
    UserBindPasswordRequest
)
from src.web_api.dependencies import get_current_user
from src.database.models import User

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/telegram", response_model=dict)
async def login_telegram(req: TelegramLoginRequest):
    """
    Login or register via Telegram Web App or Login Widget.
    """
    try:
        init_data = req.initData
        widget_data = req.model_dump(exclude_unset=True, exclude={"initData"}) if not init_data else None
        
        user, stats = await authenticate_and_get_user(init_data=init_data, widget_data=widget_data)
        
        # Check web access permission
        if not await permission_service.check_web_access(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足：只有练气期及以上境界，或内门及以上身份的弟子才能登录 Web 端"
            )
        
        # Issue JWT
        access_token = create_access_token(subject=user.id, pwd_ver=user.password_version)
        current_identity = stats.get("identity", user.current_identity)
        
        user_response_data = UserResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            full_name=user.full_name,
            language_code=user.language_code,
            credits=stats.get("credits", user.credits),
            user_group=stats.get("group", user.user_group),
            current_identity=current_identity,
            priority=stats.get("priority", 0),
            identity_expire_at=stats.get("identity_expire_at"),
            total_contributions=stats.get("total_contributions", 0),
            generation_count=stats.get("generations", 0),
            checkin_count=stats.get("checkins", 0),
            invitation_count=stats.get("invitations", 0),
            invitation_recharge=InvitationRechargeStats(**stats.get("invitation_recharge", {})) if stats.get("invitation_recharge") else None
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_response_data.model_dump()
        }
    except InvalidSignatureError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during Telegram login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during authentication."
        )

@router.post("/login")
async def login_with_password(req: UserLoginRequest, request: Request):
    """
    Login with username (道号) and password (密咒).
    """
    client_ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or request.client.host or "unknown"
    
    try:
        user, stats = await authenticate_user_by_password(req.username, req.password, client_ip)
        
        # Issue JWT
        access_token = create_access_token(subject=user.id, pwd_ver=user.password_version, channel="password")
        current_identity = stats.get("identity", user.current_identity)
        
        user_response_data = UserResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            full_name=user.full_name,
            language_code=user.language_code,
            credits=stats.get("credits", user.credits),
            user_group=stats.get("group", user.user_group),
            current_identity=current_identity,
            priority=stats.get("priority", 0),
            identity_expire_at=stats.get("identity_expire_at"),
            total_contributions=stats.get("total_contributions", 0),
            generation_count=stats.get("generations", 0),
            checkin_count=stats.get("checkins", 0),
            invitation_count=stats.get("invitations", 0),
            invitation_recharge=InvitationRechargeStats(**stats.get("invitation_recharge", {})) if stats.get("invitation_recharge") else None
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_response_data.model_dump()
        }
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except RateLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except InsufficientPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Error during password login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during authentication."
        )

@router.post("/bind-password")
async def bind_password(req: UserBindPasswordRequest, request: Request, current_user: User = Depends(get_current_user)):
    """
    Bind or update username and password for currently logged-in user.
    """
    client_ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or request.client.host or "unknown"
    
    try:
        await bind_user_password(current_user.id, req.username, req.password, client_ip)
        return {"status": "success", "message": "密咒设置成功。请使用新密咒重新登录。"}
    except InsufficientPermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except RateLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))
    except AuthCoreError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error binding password for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during password binding."
        )
