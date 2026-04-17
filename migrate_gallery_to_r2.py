import asyncio
import io
import time
import sys
import logging
import botocore.exceptions
from boto3.s3.transfer import TransferConfig

# Configure standard logging instead of loguru
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History
from sqlalchemy import select

from src.services.storage import storage
from config import R2_BUCKET

# 设置限速：1 MB/s (1024 * 1024 字节)
RATE_LIMIT_BPS = 1024 * 1024

class ThrottledBytesIO(io.BytesIO):
    """
    自定义的 BytesIO 包装器，用于在读取数据时进行限速。
    配合 boto3 的 upload_fileobj 使用。
    """
    def __init__(self, initial_bytes, rate_limit_bps):
        super().__init__(initial_bytes)
        self.rate_limit_bps = rate_limit_bps
        self.start_time = time.time()
        self.bytes_read = 0

    def read(self, size=-1):
        chunk = super().read(size)
        if chunk:
            self.bytes_read += len(chunk)
            elapsed = time.time() - self.start_time
            # 预期应该花费的时间
            expected = self.bytes_read / self.rate_limit_bps
            # 如果读取过快，则休眠补齐时间
            if expected > elapsed:
                time.sleep(expected - elapsed)
        return chunk

async def main():
    logger.info("=== 开始检查未迁移到 R2 的画廊数据 ===")
    
    if not storage.r2_client:
        logger.error("❌ R2 客户端未初始化，请检查 .env 配置！")
        return

    # 1. 从数据库获取所有已经发布在画廊的帖子及其源文件路径
    async with AsyncSessionLocal() as session:
        stmt = select(GalleryPost, History).join(
            History, GalleryPost.task_id == History.task_id
        ).where(History.output_file.isnot(None))
        
        result = await session.execute(stmt)
        records = result.all()
        
    logger.info(f"📦 共找到 {len(records)} 条画廊记录，开始逐一检查/迁移...")
    
    success_count = 0
    skip_count = 0
    fail_count = 0

    # 禁用多线程上传，确保自定义的限速 IO 对象按顺序被读取
    transfer_config = TransferConfig(use_threads=False)

    for post, history in records:
        output_file = history.output_file
        
        # 解析 MinIO 路径逻辑 (与 callback_handler.py 保持一致)
        parts = output_file.split("/")
        if len(parts) > 1 and parts[0] in ["bot-data", "comfyui-temp"]:
            bucket_name = parts[0]
            object_name = "/".join(parts[1:])
        elif "comfyui-temp" not in output_file and "bot-data" not in output_file:
            bucket_name = "comfyui-temp" if not "/" in output_file else "bot-data"
            object_name = output_file
        else:
            bucket_name = "bot-data"
            object_name = output_file
            
        r2_object_name = parts[-1]
        
        # 2. 检查 R2 中是否已存在该文件 (利用 head_object)
        try:
            storage.r2_client.head_object(Bucket=R2_BUCKET, Key=r2_object_name)
            # 如果不报错，说明文件已存在
            logger.info(f"⏩ 文件已存在，跳过: {r2_object_name}")
            skip_count += 1
            continue
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == '404':
                # 404 说明文件不存在，需要执行迁移
                pass
            else:
                logger.error(f"❌ 检查 R2 状态失败 {r2_object_name}: {e}")
                fail_count += 1
                continue

        # 3. 需要迁移，从本地 MinIO 读取
        logger.info(f"⏳ 正在拉取: {object_name} (Bucket: {bucket_name})")
        response = None
        try:
            # 读入内存
            response = storage.client.get_object(bucket_name, object_name)
            file_data = response.read()
            content_type = response.headers.get('Content-Type', 'application/octet-stream')
            file_size_mb = len(file_data) / 1024 / 1024
            
            logger.info(f"🚀 开始以 1MB/s 速度上传: {r2_object_name} ({file_size_mb:.2f} MB)")
            
            # 4. 包装为带限速的类文件对象
            throttled_data = ThrottledBytesIO(file_data, RATE_LIMIT_BPS)
            
            # 5. 上传至 R2
            storage.r2_client.upload_fileobj(
                Fileobj=throttled_data,
                Bucket=R2_BUCKET,
                Key=r2_object_name,
                ExtraArgs={'ContentType': content_type},
                Config=transfer_config
            )
            
            logger.info(f"✅ 迁移成功: {r2_object_name}")
            success_count += 1
            
        except Exception as e:
            logger.error(f"❌ 迁移失败 {object_name}: {e}")
            fail_count += 1
        finally:
            if response:
                response.close()
                response.release_conn()

    logger.info("===============================================")
    logger.info(f"🎉 迁移任务完成！")
    logger.info(f"   成功迁移: {success_count} 个文件")
    logger.info(f"   跳过(已存在): {skip_count} 个文件")
    logger.info(f"   失败报错: {fail_count} 个文件")
    logger.info("===============================================")

if __name__ == "__main__":
    asyncio.run(main())
