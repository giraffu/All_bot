from datetime import datetime, timedelta
from typing import Any, Optional, Union

from jose import jwt

from src.web_api.core.config import settings


def create_access_token(
    subject: Union[str, Any], expires_delta: timedelta = None, pwd_ver: int = 1, channel: str = "telegram"
) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject), "pwd_ver": pwd_ver, "channel": channel}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return decoded_token
    except jwt.JWTError:
        return None
