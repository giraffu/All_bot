import asyncio
from sqlalchemy import select, desc
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History

async def main():
    async with AsyncSessionLocal() as session:
        query = select(GalleryPost).order_by(desc(GalleryPost.id)).limit(5)
        result = await session.execute(query)
        posts = result.scalars().all()
        for post in posts:
            hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
            history = hist_res.scalar_one_or_none()
            if history:
                output_file = history.output_file
                from config import R2_PUBLIC_DOMAIN
                if R2_PUBLIC_DOMAIN:
                    filename = output_file.split("/")[-1]
                    base_url = R2_PUBLIC_DOMAIN.rstrip("/")
                    url = f"{base_url}/{filename}"
                    print(f"Post {post.id} Media URL: {url}")
                
if __name__ == "__main__":
    asyncio.run(main())
