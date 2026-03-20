import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from src.database.core import engine
from sqlalchemy import text

async def fix_orders_table():
    async with engine.begin() as conn:
        print("Checking tables...")
        
        # It seems the orders table exists but might be missing the 'id' column
        # Or maybe it was created without a primary key?
        # Let's try to add the id column or drop and recreate if it's empty
        
        try:
            # Let's check if the table has any rows first
            result = await conn.execute(text("SELECT COUNT(*) FROM orders"))
            count = result.scalar()
            print(f"Orders table has {count} rows.")
            
            if count == 0:
                print("Table is empty, dropping and recreating it.")
                await conn.execute(text("DROP TABLE IF EXISTS orders"))
                
                # Now the application will recreate it on next startup (init_db)
                # But let's just create it directly
                create_sql = """
                CREATE TABLE orders (
                    id SERIAL PRIMARY KEY,
                    order_id VARCHAR(64),
                    telegram_id BIGINT NOT NULL,
                    plan_id INTEGER NOT NULL,
                    original_price NUMERIC(10, 2) NOT NULL,
                    final_price NUMERIC(10, 2) NOT NULL,
                    status VARCHAR(20) DEFAULT 'PENDING',
                    tx_hash VARCHAR(100) UNIQUE,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
                """
                await conn.execute(text(create_sql))
                
                # Add indexes
                await conn.execute(text("CREATE INDEX ix_orders_order_id ON orders (order_id)"))
                await conn.execute(text("CREATE INDEX ix_orders_telegram_id ON orders (telegram_id)"))
                
                print("Successfully recreated orders table.")
            else:
                # If it has data, we need to alter it
                print("Table has data. Trying to add id column...")
                try:
                    await conn.execute(text("ALTER TABLE orders ADD COLUMN id SERIAL PRIMARY KEY"))
                    print("Added id column.")
                except Exception as e:
                    print(f"Could not add id column: {e}")
                    
        except Exception as e:
            print(f"Error checking orders table: {e}")

if __name__ == "__main__":
    asyncio.run(fix_orders_table())
