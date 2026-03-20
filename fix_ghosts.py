import asyncio
from sqlalchemy import select, delete
from src.database.core import AsyncSessionLocal
from src.database.models import TemplateContribution
from dotenv import load_dotenv
import os

load_dotenv()

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(TemplateContribution))
        contributions = result.scalars().all()
        
        # Get all objects from MinIO
        from src.services.storage import storage
        from config import MINIO_TEMPLATE_BUCKET
        
        minio_objects = storage.list_objects("", bucket=MINIO_TEMPLATE_BUCKET)
        minio_filenames = {os.path.basename(o) for o in minio_objects}
        
        missing_ids = []
        for c in contributions:
            filename = os.path.basename(c.file_path.replace('\\', '/'))
            if filename not in minio_filenames:
                missing_ids.append(c.id)
                
        print(f"Total ghosts to delete: {len(missing_ids)}")
        if missing_ids:
            await session.execute(delete(TemplateContribution).where(TemplateContribution.id.in_(missing_ids)))
            await session.commit()
            print("Deleted ghosts.")
        
if __name__ == "__main__":
    asyncio.run(main())
