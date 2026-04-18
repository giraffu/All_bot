import asyncio
from src.database.core import AsyncSessionLocal
from sqlalchemy import select
from src.database.models import GalleryPost, History
from src.services.storage import storage

async def sync_all_to_r2():
    async with AsyncSessionLocal() as session:
        posts = (await session.execute(select(GalleryPost))).scalars().all()
        for post in posts:
            hist = (await session.execute(select(History).where(History.task_id == post.task_id))).scalar_one_or_none()
            if hist and hist.output_file:
                parts = hist.output_file.split("/")
                if len(parts) > 1 and parts[0] in ["bot-data", "comfyui-temp"]:
                    bucket_name = parts[0]
                    object_name = "/".join(parts[1:])
                elif "comfyui-temp" not in hist.output_file and "bot-data" not in hist.output_file:
                    bucket_name = "comfyui-temp" if not "/" in hist.output_file else "bot-data"
                    object_name = hist.output_file
                else:
                    bucket_name = "bot-data"
                    object_name = hist.output_file
                
                r2_object_name = parts[-1]
                print(f"Syncing {object_name} from {bucket_name} to R2 as {r2_object_name}...")
                await storage.async_copy_to_r2(bucket_name, object_name, r2_object_name)

asyncio.run(sync_all_to_r2())
