import hashlib
import hmac
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from config import BOT_TOKEN
from src.core.user_core import get_or_create_user_by_telegram
from src.web_api.core.security import create_access_token
from src.web_api.schemas.auth_schema import TelegramLoginRequest, Token, UserResponse

router = APIRouter()
logger = logging.getLogger(__name__)

def verify_telegram_authorization(data: dict) -> bool:
    """Verify the hash of the Telegram auth data."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set!")
        return False
        
    received_hash = data.pop("hash", None)
    if not received_hash:
        return False

    # Sort data keys alphabetically and join them as key=value separated by newline
    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(data.items())])
    
    # Generate secret key from bot token
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    
    # Calculate HMAC-SHA256 signature
    expected_hash = hmac.new(
        secret_key, 
        data_check_string.encode(), 
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_hash, received_hash)

@router.post("/telegram", response_model=dict)
async def login_telegram(req: TelegramLoginRequest):
    """
    Login or register via Telegram Web App or Login Widget.
    """
    data = req.model_dump(exclude_unset=True)
    
    # For development/testing purposes, if hash is "debug_mode" bypass validation
    # IN PRODUCTION: Remove this bypass!
    if req.hash != "debug_mode" and not verify_telegram_authorization(data):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram authentication signature."
        )

    full_name = ""
    if req.first_name:
        full_name += req.first_name
    if req.last_name:
        full_name += f" {req.last_name}"
    full_name = full_name.strip()

    try:
        # Core business logic decoupled in Phase 1
        user, is_new = await get_or_create_user_by_telegram(
            tg_id=req.id, 
            username=req.username, 
            full_name=full_name
        )
        
        # Issue JWT
        access_token = create_access_token(subject=user.id)
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user).model_dump()
        }
        
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
