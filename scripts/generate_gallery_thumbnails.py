import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History
from src.core.media_processor import generate_and_upload_thumbnail

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ThumbnailGenerator")

async def main():
    logger.info("Starting historical thumbnail generation...")
    
    # We must fetch all necessary data in one go and close the session,
    # because the processing takes a very long time and the asyncpg connection 
    # will time out or get closed by the server.
    async with AsyncSessionLocal() as session:
        # Fetch all active gallery posts with their history to get the output_file
        query = (
            select(GalleryPost.id, GalleryPost.media_type, History.output_file)
            .join(History, GalleryPost.task_id == History.task_id)
            .where(GalleryPost.is_active == True)
        )
        
        result = await session.execute(query)
        # Fetch all rows into memory as simple tuples (id, media_type, output_file)
        rows = result.all()
        
    total = len(rows)
    logger.info(f"Found {total} active gallery posts to process. Database connection closed safely.")
    
    success = 0
    failed = 0
    
    for idx, (post_id, media_type, output_file) in enumerate(rows, 1):
        if not output_file:
            logger.warning(f"[{idx}/{total}] Post {post_id} has no output_file. Skipping.")
            failed += 1
            continue
            
        logger.info(f"[{idx}/{total}] Processing Post {post_id} | Media Type: {media_type}")
        try:
            await generate_and_upload_thumbnail(output_file, media_type)
            success += 1
        except FileNotFoundError as e:
            if 'ffmpeg' in str(e):
                logger.error(f"[{idx}/{total}] 致命错误：当前环境未安装 ffmpeg，请在 docker 容器内运行本脚本！")
                break
            logger.error(f"[{idx}/{total}] Failed to process Post {post_id}: {e}")
            failed += 1
        except Exception as e:
            logger.error(f"[{idx}/{total}] Failed to process Post {post_id}: {e}")
            failed += 1
            
    logger.info(f"Finished! Total: {total} | Success: {success} | Failed: {failed}")

if __name__ == "__main__":
    asyncio.run(main())
