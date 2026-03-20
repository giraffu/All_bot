import asyncio
from sqlalchemy import select
from src.database.core import AsyncSessionLocal
from src.database.models import TemplateContribution
from dotenv import load_dotenv
import os

load_dotenv()

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TemplateContribution))
        contributions = result.scalars().all()
        
        db_filenames = {os.path.basename(c.file_path.replace('\\', '/')) for c in contributions}
        
        # Get all objects from MinIO
        from src.services.storage import storage
        from config import MINIO_TEMPLATE_BUCKET
        
        minio_objects = storage.list_objects("", bucket=MINIO_TEMPLATE_BUCKET)
        minio_filenames = {os.path.basename(o) for o in minio_objects}
        
        missing_in_minio = db_filenames - minio_filenames
        
        print(f"Total in DB: {len(db_filenames)}")
        print(f"Total in MinIO: {len(minio_filenames)}")
        print(f"In DB but not in MinIO: {len(missing_in_minio)}")
        
if __name__ == "__main__":
    asyncio.run(main())
