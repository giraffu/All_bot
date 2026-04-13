from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import AsyncSessionLocal
from src.database.models import User
from src.web_api.core.config import settings
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
        
    return user
