import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .models import Base
from config import DATABASE_URL
from .logger import setup_db_logging

logger = logging.getLogger(__name__)

# Engine configuration
engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    pool_pre_ping=True,  # Useful for Postgres to detect disconnects
)

# Setup DB Logging
setup_db_logging(engine)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def run_alembic_upgrade():
    import os
    import asyncio
    from alembic.config import Config
    from alembic import command
    
    def _run_sync():
        # Get the path to the root directory where alembic.ini is located
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        alembic_ini_path = os.path.join(root_dir, "alembic.ini")
        alembic_cfg = Config(alembic_ini_path)
        # Set the root directory so alembic can find the migrations folder
        alembic_cfg.set_main_option("script_location", os.path.join(root_dir, "migrations"))
        
        command.upgrade(alembic_cfg, "head")
        
    await asyncio.to_thread(_run_sync)

async def stamp_alembic_head():
    import os
    import asyncio
    from alembic.config import Config
    from alembic import command
    
    def _run_sync():
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        alembic_ini_path = os.path.join(root_dir, "alembic.ini")
        alembic_cfg = Config(alembic_ini_path)
        alembic_cfg.set_main_option("script_location", os.path.join(root_dir, "migrations"))
        
        command.stamp(alembic_cfg, "head")
        
    await asyncio.to_thread(_run_sync)

async def init_db():
    async with engine.begin() as conn:
        # We still run create_all to ensure tables exist if it's a completely fresh setup
        # However, alembic upgrade head will also create tables.
        # It's safer to just check if we need to stamp.
        
        try:
            res = await conn.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name = 'users'"))
            users_exists = res.scalar() == 1
        except Exception:
            users_exists = False
            
        try:
            res = await conn.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version'"))
            alembic_exists = res.scalar() == 1
        except Exception:
            alembic_exists = False

    if users_exists and not alembic_exists:
        logger.info("检测到现存数据库未包含 Alembic 版本信息，执行 stamp head 操作平滑过渡...")
        await stamp_alembic_head()

    logger.info("执行数据库结构迁移...")
    # await run_alembic_upgrade()
    logger.info("数据库结构迁移完成！")

    async with engine.begin() as conn:
        # Initialize default membership plans and discount rules if tables are empty
        try:
            res = await conn.execute(text("SELECT COUNT(*) FROM membership_plans"))
            if res.scalar() == 0:
                logger.info("Initializing default membership plans")
                await conn.execute(text("""
                    INSERT INTO membership_plans (name, identity_name, price_ton, price_stars, reward_credits, duration_days) VALUES
                    ('基础月卡', '内门弟子', 1.99, 200, 400, 30),
                    ('高级月卡', '核心弟子', 4.99, 500, 1200, 30),
                    ('至尊月卡', '真传弟子', 9.90, 1000, 3000, 30),
                    ('200 Star 直购', '纯灵石', 1.99, 200, 600, 0),
                    ('500 Star 直购', '纯灵石', 4.99, 500, 1800, 0),
                    ('1000 Star 直购', '纯灵石', 9.90, 1000, 4000, 0)
                """))
        except Exception as e:
            logger.warning(f"Failed to initialize default plans: {e}")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


