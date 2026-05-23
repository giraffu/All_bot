from fastapi import APIRouter, Depends, Request

from src.web_api.schemas.auth_schema import (
    TelegramLoginRequest,
    UserLoginRequest,
    UserBindPasswordRequest,
)
from src.web_api.dependencies import get_current_user
from src.database.models import User
from src.web_api.services.auth_api_service import (
    bind_password_payload,
    login_telegram_payload,
    login_with_password_payload,
)

router = APIRouter()


@router.post("/telegram", response_model=dict)
async def login_telegram(req: TelegramLoginRequest):
    """
    Login or register via Telegram Web App or Login Widget.
    """
    return await login_telegram_payload(req=req)


@router.post("/login")
async def login_with_password(req: UserLoginRequest, request: Request):
    """
    Login with username (道号) and password (密咒).
    """
    return await login_with_password_payload(req=req, request=request)


@router.post("/bind-password")
async def bind_password(
    req: UserBindPasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Bind or update username and password for currently logged-in user.
    """
    return await bind_password_payload(
        req=req,
        request=request,
        current_user=current_user,
    )
