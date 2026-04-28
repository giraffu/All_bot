import hashlib
import hmac
import json
import logging
import urllib.parse
from typing import Optional, Tuple

from config import BOT_TOKEN, BOT_TOKEN_TEST
from src.core.user_core import get_or_create_user_by_telegram
from src.database.models import User
from src.services.permission_service import permission_service

logger = logging.getLogger(__name__)

class AuthCoreError(Exception):
    pass

class InvalidSignatureError(AuthCoreError):
    pass

class InsufficientPermissionError(AuthCoreError):
    pass

def verify_telegram_authorization(data: dict) -> bool:
    """Verify the hash of the Telegram auth data (Widget format)."""
    received_hash = data.pop("hash", None)
    if not received_hash:
        return False

    import time
    auth_date = data.get("auth_date")
    if not auth_date or time.time() - int(auth_date) > 86400:
        logger.error("Telegram auth_date is too old or missing (Replay attack prevention).")
        return False

    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(data.items())])
    
    tokens_to_try = [t for t in [BOT_TOKEN, BOT_TOKEN_TEST] if t]
    if not tokens_to_try:
        logger.error("No BOT_TOKEN or BOT_TOKEN_TEST configured!")
        return False

    for token in tokens_to_try:
        secret_key = hashlib.sha256(token.encode()).digest()
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
    params = dict(urllib.parse.parse_qsl(init_data))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return None

    import time
    auth_date = params.get("auth_date")
    if not auth_date or time.time() - int(auth_date) > 86400:
        logger.error("Telegram WebApp auth_date is too old or missing.")
        return None

    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(params.items())])
    
    tokens_to_try = [t for t in [BOT_TOKEN, BOT_TOKEN_TEST] if t]
    if not tokens_to_try:
        logger.error("No BOT_TOKEN or BOT_TOKEN_TEST configured!")
        return None

    is_valid = False
    for token in tokens_to_try:
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
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

async def authenticate_and_get_user(
    init_data: Optional[str] = None,
    widget_data: Optional[dict] = None
) -> Tuple[User, dict]:
    """
    Authenticate user via initData or widget_data, and return (user_model, stats).
    Raises InvalidSignatureError if auth fails.
    """
    if init_data:
        user_data = verify_telegram_webapp_initdata(init_data)
        if not user_data:
            raise InvalidSignatureError("Invalid Telegram WebApp authentication signature.")
            
        tg_id = user_data.get("id")
        first_name = user_data.get("first_name", "")
        last_name = user_data.get("last_name", "")
        username = user_data.get("username", "")
        
        full_name = first_name
        if last_name:
            full_name += f" {last_name}"
        full_name = full_name.strip()
    elif widget_data:
        if not widget_data.get("id") or not widget_data.get("hash") or not widget_data.get("auth_date"):
            raise InvalidSignatureError("Missing required fields for Login Widget auth.")
            
        if not verify_telegram_authorization(widget_data):
            raise InvalidSignatureError("Invalid Telegram authentication signature.")
            
        tg_id = widget_data.get("id")
        first_name = widget_data.get("first_name", "")
        last_name = widget_data.get("last_name", "")
        username = widget_data.get("username", "")
        
        full_name = first_name
        if last_name:
            full_name += f" {last_name}"
        full_name = full_name.strip()
    else:
        raise InvalidSignatureError("No authentication data provided.")

    user, is_new = await get_or_create_user_by_telegram(
        tg_id=tg_id, 
        username=username, 
        full_name=full_name
    )
    
    stats = await permission_service.get_user_detailed_stats(user.telegram_id)
        
    return user, stats
