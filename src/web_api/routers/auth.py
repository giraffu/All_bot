import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from src.web_api.core.security import create_access_token
from src.web_api.schemas.auth_schema import TelegramLoginRequest, Token, UserResponse, InvitationRechargeStats
from src.core.auth_core import authenticate_and_get_user, AuthCoreError

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
        
        # Issue JWT
        access_token = create_access_token(subject=user.id)
        current_identity = stats.get("identity", user.current_identity)
        
        user_response_data = UserResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            full_name=user.full_name,
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
    except AuthCoreError as e:
        status_code = e.args[1] if len(e.args) > 1 else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during Telegram login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during authentication."
        )

@router.post("/login")
async def default_login_form():
    """
    Placeholder for standard OAuth2PasswordBearer form.
    For Swagger UI compatibility.
    """
    raise HTTPException(status_code=501, detail="Please use /telegram login endpoint.")
