from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import AsyncSessionLocal
from src.database.models import User
from src.web_api.core.security import verify_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def get_token(request: Request, token: str = Depends(oauth2_scheme)) -> str:
    if token:
        return token
    
    query_token = request.query_params.get("token")
    if query_token:
        return query_token
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(get_token)
) -> User:
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
        
    # Check dynamic permission (Persistent Privilege Check)
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
            detail="您的权限已变更：目前境界或身份已不满足访问 Web 端的要求"
        )
        
    return user
