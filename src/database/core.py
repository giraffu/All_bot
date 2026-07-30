import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW
from src.domain_config.membership_plans import CANONICAL_MEMBERSHIP_PLAN_ROWS

from .logger import setup_db_logging

logger = logging.getLogger(__name__)

# Engine configuration
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # Useful for Postgres to detect disconnects
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=30,
    pool_recycle=1800,
)

# Setup DB Logging
setup_db_logging(engine)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _build_membership_plan_sync_sql() -> str:
    values_sql = ",\n                    ".join(
        (
            f"({plan['id']}, '{plan['name']}', '{plan['identity_name']}', "
            f"{plan['price_ton']}, {plan['price_usdt']}, "
            f"{plan['price_stars']}, {plan['price_rmb']}, "
            f"{plan['reward_credits']}, {plan['duration_days']}, "
            f"{'TRUE' if plan['is_active'] else 'FALSE'})"
        )
        for plan in CANONICAL_MEMBERSHIP_PLAN_ROWS
    )
    return f"""
                    INSERT INTO membership_plans
                        (id, name, identity_name, price_ton, price_usdt, price_stars, price_rmb, reward_credits, duration_days, is_active)
                    VALUES
                    {values_sql}
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        identity_name = EXCLUDED.identity_name,
                        price_ton = EXCLUDED.price_ton,
                        price_usdt = EXCLUDED.price_usdt,
                        price_stars = EXCLUDED.price_stars,
                        price_rmb = EXCLUDED.price_rmb,
                        reward_credits = EXCLUDED.reward_credits,
                        duration_days = EXCLUDED.duration_days,
                        is_active = EXCLUDED.is_active
                """


async def stamp_alembic_head():
    import asyncio
    import os

    from alembic import command
    from alembic.config import Config

    def _run_sync():
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        alembic_ini_path = os.path.join(root_dir, "alembic.ini")
        alembic_cfg = Config(alembic_ini_path)
        alembic_cfg.set_main_option(
            "script_location", os.path.join(root_dir, "migrations")
        )

        command.stamp(alembic_cfg, "head")

    await asyncio.to_thread(_run_sync)


async def init_db():
    async with engine.begin() as conn:
        # We still run create_all to ensure tables exist if it's a completely fresh setup
        # However, alembic upgrade head will also create tables.
        # It's safer to just check if we need to stamp.

        try:
            res = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'users'"
                )
            )
            users_exists = res.scalar() == 1
        except Exception:
            users_exists = False

        try:
            res = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version'"
                )
            )
            alembic_exists = res.scalar() == 1
        except Exception:
            alembic_exists = False

    if users_exists and not alembic_exists:
        logger.info(
            "检测到现存数据库未包含 Alembic 版本信息，执行 stamp head 操作平滑过渡..."
        )
        await stamp_alembic_head()

    logger.info("数据库结构迁移跳过（交由手动Alembic执行）")

    async with engine.begin() as conn:
        # Ensure canonical membership plans exist in every environment.
        try:
            logger.info("Synchronizing canonical membership plans")
            await conn.execute(text(_build_membership_plan_sync_sql()))
            await conn.execute(
                text(
                    """
                    SELECT setval(
                        pg_get_serial_sequence('membership_plans', 'id'),
                        GREATEST((SELECT COALESCE(MAX(id), 1) FROM membership_plans), 1),
                        true
                    )
                    """
                )
            )
        except Exception as e:
            logger.warning(f"Failed to synchronize canonical membership plans: {e}")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
