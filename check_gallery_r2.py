import asyncio
from sqlalchemy import select, desc
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History

async def main():
    async with AsyncSessionLocal() as session:
        query = select(GalleryPost).order_by(desc(GalleryPost.id)).limit(100)
        result = await session.execute(query)
        posts = result.scalars().all()
        for post in posts:
            hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
            history = hist_res.scalar_one_or_none()
            if not history or not history.output_file:
                print(f"Post {post.id} (Task: {post.task_id}) HAS EMPTY OUTPUT_FILE!")
                
if __name__ == "__main__":
    asyncio.run(main())
