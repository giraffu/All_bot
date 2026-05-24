from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_core_password_version import is_password_version_blacklisted
from src.database.core import AsyncSessionLocal
from src.database.models import User
from src.web_api.core.security import verify_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


import asyncio
import logging

logger = logging.getLogger(__name__)

async def get_db():
    session = AsyncSessionLocal()
    try:
        yield session
    except asyncio.CancelledError:
        logger.warning("Request was cancelled by the client. Cleaning up session.")
        try:
            await session.rollback()
        except Exception as e:
            logger.error(f"Failed to rollback session on request cancel: {e}")
        raise
    except Exception as e:
        logger.error(f"Unhandled error in request, rolling back session: {e}")
        try:
            await session.rollback()
        except Exception as rollback_err:
            logger.error(f"Failed to rollback session on error: {rollback_err}")
        raise
    finally:
        try:
            await session.close()
        except Exception as close_err:
            logger.error(f"Failed to close session during cleanup: {close_err}")


async def get_bearer_token(token: str = Depends(oauth2_scheme)) -> str:
    if token:
        return token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _get_current_user_from_session(db: AsyncSession, token: str) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = verify_token(token)
    if payload is None:
        raise credentials_exception

    internal_id_str: str = payload.get("sub")
    if internal_id_str is None:
        raise credentials_exception

    try:
        internal_id = int(internal_id_str)
    except ValueError:
        raise credentials_exception

    stmt = select(User).where(User.id == internal_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    # Check if the token's password version is blacklisted (if they changed password recently)
    token_pwd_ver = payload.get("pwd_ver", 0)
    if token_pwd_ver:
        from src.services.redis_client import redis_client

        redis = redis_client.redis
        if await is_password_version_blacklisted(
            redis=redis,
            user_id=user.id,
            password_version=token_pwd_ver,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="密咒已变更，当前结界已失效，请重新登录。",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Check dynamic permission (Persistent Privilege Check)
    from src.services.permission_service import permission_service

    stats = await permission_service.get_user_detailed_stats_by_user_id(user.id)
    current_identity = stats.get("identity", user.current_identity)
    current_group = stats.get("group", user.user_group)

    from src.constants import WEB_ACCESS_ALLOWED_IDENTITIES, WEB_ACCESS_ALLOWED_GROUPS

    has_web_access = (
        current_identity in WEB_ACCESS_ALLOWED_IDENTITIES
        or current_group in WEB_ACCESS_ALLOWED_GROUPS
    )

    if not has_web_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您的权限已变更：目前境界或身份已不满足访问 Web 端的要求",
        )

    return user


async def get_current_user(
    db: AsyncSession = Depends(get_db), token: str = Depends(get_bearer_token)
) -> User:
    return await _get_current_user_from_session(db, token)


async def get_current_user_once(
    token: str = Depends(get_bearer_token),
) -> User:
    async with AsyncSessionLocal() as session:
        return await _get_current_user_from_session(session, token)


CurrentUserDep = Annotated[User, Depends(get_current_user)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]
