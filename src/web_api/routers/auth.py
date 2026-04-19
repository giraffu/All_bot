import hashlib
import hmac
import logging
import urllib.parse
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from config import BOT_TOKEN, BOT_TOKEN_TEST
from src.core.user_core import get_or_create_user_by_telegram
from src.web_api.core.security import create_access_token
from src.web_api.schemas.auth_schema import TelegramLoginRequest, Token, UserResponse, InvitationRechargeStats

router = APIRouter()
logger = logging.getLogger(__name__)

def verify_telegram_authorization(data: dict) -> bool:
    """Verify the hash of the Telegram auth data (Widget format)."""
    received_hash = data.pop("hash", None)
    if not received_hash:
        return False

    # Check auth_date to prevent replay attacks (e.g. older than 24 hours)
    import time
    auth_date = data.get("auth_date")
    if not auth_date or time.time() - int(auth_date) > 86400:
        logger.error("Telegram auth_date is too old or missing (Replay attack prevention).")
        return False

    # Sort data keys alphabetically and join them as key=value separated by newline
    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(data.items())])
    
    tokens_to_try = [t for t in [BOT_TOKEN, BOT_TOKEN_TEST] if t]
    if not tokens_to_try:
        logger.error("No BOT_TOKEN or BOT_TOKEN_TEST configured!")
        return False

    for token in tokens_to_try:
        # Generate secret key from bot token
        secret_key = hashlib.sha256(token.encode()).digest()
        
        # Calculate HMAC-SHA256 signature
        expected_hash = hmac.new(
            secret_key, 
            data_check_string.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        if hmac.compare_digest(expected_hash, received_hash):
            return True
            
    return False

def verify_telegram_webapp_initdata(init_data: str) -> Optional[dict]:
    """
    Verify the initData string passed from Telegram Mini App.
    Returns parsed user dict if valid, else None.
    """
    # Parse query string into dict
    params = dict(urllib.parse.parse_qsl(init_data))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return None

    # Check auth_date
    import time
    auth_date = params.get("auth_date")
    if not auth_date or time.time() - int(auth_date) > 86400:
        logger.error("Telegram WebApp auth_date is too old or missing.")
        return None

    # Sort parameters
    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(params.items())])
    
    tokens_to_try = [t for t in [BOT_TOKEN, BOT_TOKEN_TEST] if t]
    if not tokens_to_try:
        logger.error("No BOT_TOKEN or BOT_TOKEN_TEST configured!")
        return None

    is_valid = False
    for token in tokens_to_try:
        # WebApp signature uses "WebAppData" and bot token to generate the secret key
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        
        # Calculate HMAC-SHA256 signature
        expected_hash = hmac.new(
            secret_key, 
            data_check_string.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        if hmac.compare_digest(expected_hash, received_hash):
            is_valid = True
            break
            
    if not is_valid:
        return None
        
    user_str = params.get("user")
    if not user_str:
        return None
        
    try:
        return json.loads(user_str)
    except Exception as e:
        logger.error(f"Failed to parse user from initData: {e}")
        return None

@router.post("/telegram", response_model=dict)
async def login_telegram(req: TelegramLoginRequest):
    """
    Login or register via Telegram Web App or Login Widget.
    """
    if req.initData:
        # Mini App (WebApp) Login Flow
        user_data = verify_telegram_webapp_initdata(req.initData)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Telegram WebApp authentication signature."
            )
        tg_id = user_data.get("id")
        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")
        username = user_data.get("username", "")
        
        full_name = first_name
        if last_name:
            full_name += f" {last_name}"
        full_name = full_name.strip()
        
    else:
        # Traditional Login Widget Flow
        if not req.id or not req.hash or not req.auth_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields for Login Widget auth."
            )
            
        data = req.model_dump(exclude_unset=True, exclude={"initData"})
        
        # Strict HMAC-SHA256 validation
        if not verify_telegram_authorization(data):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Telegram authentication signature."
            )
            
        tg_id = req.id
        first_name = req.first_name or ""
        last_name = req.last_name or ""
        username = req.username or ""
        
        full_name = first_name
        if last_name:
            full_name += f" {last_name}"
        full_name = full_name.strip()

    try:
        # Core business logic decoupled in Phase 1
        user, is_new = await get_or_create_user_by_telegram(
            tg_id=tg_id, 
            username=username, 
            full_name=full_name
        )
        
        from src.services.permission_service import permission_service
        stats = await permission_service.get_user_detailed_stats(user.telegram_id)
        current_identity = stats.get("identity", user.current_identity)
        current_group = stats.get("group", user.user_group)
        
        allowed_identities = ["内门弟子", "核心弟子", "真传弟子"]
        allowed_groups = ["金丹期", "元婴期", "化神期", "炼虚期", "合体期", "大乘期", "渡劫期"]
        
        is_allowed_identity = current_identity in allowed_identities
        is_allowed_group = current_group in allowed_groups
        
        if not (is_allowed_identity or is_allowed_group):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足：只有金丹期及以上境界，或内门及以上身份的弟子才能登录 Web 端"
            )
        
        # Issue JWT
        access_token = create_access_token(subject=user.id)
        
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
