import asyncio
from src.database.core import AsyncSessionLocal
from sqlalchemy import select
from src.database.models import GalleryPost, History
from src.services.storage import storage
from botocore.exceptions import ClientError

async def check_and_sync():
    async with AsyncSessionLocal() as session:
        posts = (await session.execute(select(GalleryPost))).scalars().all()
        missing_in_r2 = 0
        missing_in_minio = 0
        success_synced = 0
        
        print(f"Found {len(posts)} gallery posts to check...")
        
        # Batch query histories to avoid N+1 problem which might be crashing the DB connection
        post_task_ids = [p.task_id for p in posts]
        histories = (await session.execute(select(History).where(History.task_id.in_(post_task_ids)))).scalars().all()
        history_map = {h.task_id: h for h in histories}
        
        for post in posts:
            hist = history_map.get(post.task_id)
            if not hist or not hist.output_file:
                print(f"❌ Post {post.id} has no history or output_file")
                missing_in_minio += 1
                continue
                
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
            
            # Check if exists in MinIO
            minio_exists = True
            try:
                storage.client.stat_object(bucket_name, object_name)
            except Exception as e:
                minio_exists = False
                
            if not minio_exists:
                print(f"❌ [Missing in MinIO] Post {post.id} (Task: {post.task_id}) file {object_name} missing locally!")
                missing_in_minio += 1
                continue
                
            # Check if exists in R2
            r2_exists = True
            if storage.r2_client:
                try:
                    storage.r2_client.head_object(Bucket=storage.r2_bucket, Key=r2_object_name)
                except ClientError as e:
                    if e.response['Error']['Code'] == '404':
                        r2_exists = False
                        
            if not r2_exists:
                missing_in_r2 += 1
                try:
                    await storage.async_copy_to_r2(bucket_name, object_name, r2_object_name)
                    success_synced += 1
                    print(f"✅ Synced {r2_object_name}")
                except Exception as e:
                    print(f"❌ Failed to sync {r2_object_name}: {e}")
                    
        print(f"\n--- Summary ---")
        print(f"Total posts checked: {len(posts)}")
        print(f"Missing in local MinIO (Irrecoverable): {missing_in_minio}")
        print(f"Missing in R2 (Attempted to sync): {missing_in_r2}")
        print(f"Successfully synced: {success_synced}")

asyncio.run(check_and_sync())
