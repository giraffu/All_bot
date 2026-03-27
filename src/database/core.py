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

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Migrations (idempotent checks)
        # Note: In a real production env, use Alembic. 
        # Here we do simple column checks for backward compatibility during dev.
        try:
            # Check if user_group column exists
            await conn.execute(text("SELECT user_group FROM users LIMIT 1"))
        except Exception:
            pass
            
    async with engine.begin() as conn:
        try:
            # Check if user_group column exists
            await conn.execute(text("SELECT user_group FROM users LIMIT 1"))
        except Exception:
            try:
                logger.info("Adding user_group column to users table")
                await conn.execute(text("ALTER TABLE users ADD COLUMN user_group VARCHAR(20) DEFAULT '游客'"))
            except Exception as e:
                logger.warning(f"Failed to add user_group column: {e}")
        
        try:
            # Check if total_contributions column exists
            await conn.execute(text("SELECT total_contributions FROM users LIMIT 1"))
        except Exception:
            pass

    async with engine.begin() as conn:
        try:
            # Check if total_contributions column exists
            await conn.execute(text("SELECT total_contributions FROM users LIMIT 1"))
        except Exception:
            try:
                logger.info("Adding contribution columns to users table")
                await conn.execute(text("ALTER TABLE users ADD COLUMN total_contributions INTEGER DEFAULT 0"))
                await conn.execute(text("ALTER TABLE users ADD COLUMN approved_contributions INTEGER DEFAULT 0"))
            except Exception as e:
                logger.warning(f"Failed to add contribution columns: {e}")

        try:
            # Check if temp_credits column exists
            await conn.execute(text("SELECT temp_credits FROM users LIMIT 1"))
        except Exception:
            pass

    async with engine.begin() as conn:
        try:
            await conn.execute(text("SELECT temp_credits FROM users LIMIT 1"))
        except Exception:
            try:
                logger.info("Adding temp_credits column to users table")
                await conn.execute(text("ALTER TABLE users ADD COLUMN temp_credits INTEGER DEFAULT 0"))
            except Exception as e:
                logger.warning(f"Failed to add temp_credits column: {e}")

        try:
            # Check if temporary_ingot column exists
            await conn.execute(text("SELECT temporary_ingot FROM users LIMIT 1"))
        except Exception:
            try:
                # We need to create a new subtransaction or execute in a new connection
                pass # This is handled below
            except Exception:
                pass
                
    # Need to run these outside the first transaction block if it failed
    async with engine.begin() as conn:
        try:
            await conn.execute(text("SELECT temporary_ingot FROM users LIMIT 1"))
        except Exception:
            try:
                logger.info("Adding temporary_ingot column to users table")
                await conn.execute(text("ALTER TABLE users ADD COLUMN temporary_ingot INTEGER DEFAULT 0"))
            except Exception as e:
                logger.warning(f"Failed to add temporary_ingot column: {e}")
                
    async with engine.begin() as conn:
        try:
            logger.info("Adding new payment and identity columns to users table")
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS current_identity VARCHAR(20) DEFAULT '外门弟子'"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS identity_expire_at TIMESTAMP"))
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_first_charge BOOLEAN DEFAULT TRUE"))
        except Exception as e:
            logger.warning(f"Failed to add payment columns: {e}")

        try:
            logger.info("Adding price_stars column to membership_plans table")
            await conn.execute(text("ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS price_stars INTEGER DEFAULT 0 NOT NULL"))
            
            # Update existing plans with default stars prices if they are 0
            await conn.execute(text("UPDATE membership_plans SET price_stars = 200 WHERE name = '基础月卡' AND price_stars = 0"))
            await conn.execute(text("UPDATE membership_plans SET price_stars = 500 WHERE name = '高级月卡' AND price_stars = 0"))
            await conn.execute(text("UPDATE membership_plans SET price_stars = 1000 WHERE name = '至尊月卡' AND price_stars = 0"))
        except Exception as e:
            logger.warning(f"Failed to add price_stars column: {e}")

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
                    ('至尊月卡', '真传弟子', 9.90, 1000, 3000, 30)
                """))
            res = await conn.execute(text("SELECT COUNT(*) FROM discount_rules"))
            if res.scalar() == 0:
                logger.info("Initializing default discount rules")
                await conn.execute(text("""
                    INSERT INTO discount_rules (rule_type, target_level, discount_rate) VALUES
                    ('FIRST_CHARGE', NULL, 0.50),
                    ('LEVEL_DISCOUNT', '筑基期', 0.98),
                    ('LEVEL_DISCOUNT', '金丹期', 0.95),
                    ('LEVEL_DISCOUNT', '元婴期', 0.90),
                    ('LEVEL_DISCOUNT', '化神期', 0.85),
                    ('LEVEL_DISCOUNT', '大乘期', 0.80)
                """))
        except Exception as e:
            logger.warning(f"Failed to initialize default plans and rules: {e}")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


