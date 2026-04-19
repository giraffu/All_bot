import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.database.models import User
from src.web_api.core.security import create_access_token
from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def main():
    async with async_session() as session:
        # Get first user
        from sqlalchemy import select, update
        result = await session.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if user:
            await session.execute(update(User).where(User.id == user.id).values(current_identity="真传弟子"))
            await session.commit()
            token = create_access_token(str(user.id))
            print(token)
            
if __name__ == "__main__":
    asyncio.run(main())
