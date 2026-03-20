import asyncio
import os
from sqlalchemy import select, desc
from src.database.core import AsyncSessionLocal
from src.database.models import TemplateContribution
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET
from dotenv import load_dotenv

load_dotenv()

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TemplateContribution)
            .order_by(desc(TemplateContribution.id))
        )
        contributions = result.scalars().all()
        
        missing_count = 0
        uploaded_count = 0
        
        for c in contributions:
            filename = os.path.basename(c.file_path.replace('\\', '/'))
            minio_path = f"temps/{filename}" if not c.is_reviewed else (
                f"video_nice/{filename}" if c.file_type == 'video' else f"quick_face/{filename}"
            )
            
            # Check if exists in MinIO
            try:
                storage.client.stat_object(MINIO_TEMPLATE_BUCKET, minio_path)
            except Exception:
                # Missing in MinIO!
                missing_count += 1
                
                # Check if it exists on disk
                # Replace /app/templates with ./templates for local host paths
                local_disk_path = c.file_path.replace('/app/templates', './templates')
                if not os.path.exists(local_disk_path):
                    # Try another way: maybe it's in ./templates/temps/
                    local_disk_path = f"./templates/temps/{filename}"
                    
                if os.path.exists(local_disk_path):
                    print(f"Uploading missing file: {local_disk_path} -> {minio_path}")
                    try:
                        storage.upload_file(local_disk_path, minio_path, bucket=MINIO_TEMPLATE_BUCKET)
                        uploaded_count += 1
                    except Exception as upload_err:
                        print(f"Failed to upload {local_disk_path}: {upload_err}")
                else:
                    # Maybe it is inside the container, let's try to copy it out? No, the volume should be mounted.
                    # Let's check if the path exists in the host machine where the docker container maps it
                    print(f"Missing file not found on host disk: {local_disk_path}")
        
        print(f"Total missing: {missing_count}, Uploaded: {uploaded_count}")

if __name__ == "__main__":
    asyncio.run(main())
