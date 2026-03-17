import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text, inspect, select, func
from sqlalchemy.orm import sessionmaker

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.models import Base, User, History, Referral, TemplateContribution, CheckinHistory, UserLog

# Configuration
SQLITE_URL = "sqlite+aiosqlite:///bot_data.db"
# Default to local docker setup if not provided
PG_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgrespassword@192.168.1.115:5432/mydatabase")

BATCH_SIZE = 1000

async def migrate():
    print(f"Source: {SQLITE_URL}")
    print(f"Target: {PG_URL}")

    # Create engines
    sqlite_engine = create_async_engine(SQLITE_URL, echo=False)
    pg_engine = create_async_engine(PG_URL, echo=False)

    # Create tables in Postgres
    print("Creating tables in PostgreSQL...")
    async with pg_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create sessions
    SqliteSession = sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)
    PgSession = sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    tables = [User, History, Referral, TemplateContribution, CheckinHistory, UserLog]

    async with SqliteSession() as sqlite_session, PgSession() as pg_session:
        for table_model in tables:
            table_name = table_model.__tablename__
            print(f"Migrating table: {table_name}...")

            # Get total count
            count_query = select(func.count()).select_from(table_model)
            total_count = await sqlite_session.scalar(count_query)
            print(f"  Total records: {total_count}")

            # Get max ID in target to support incremental/resume
            max_id_query = select(func.max(table_model.id))
            try:
                max_id = await pg_session.scalar(max_id_query)
            except Exception as e:
                # Table might be empty or error
                max_id = None
            
            start_id = (max_id or 0) + 1
            print(f"  Starting from ID: {start_id}")

            processed = 0
            while True:
                # Fetch batch from SQLite
                # Note: We assume 'id' is the primary key and is sortable
                if hasattr(table_model, 'id'):
                    stmt = select(table_model).where(table_model.id >= start_id).order_by(table_model.id).limit(BATCH_SIZE)
                else:
                    # Fallback for tables without 'id' (though all our models have it)
                    stmt = select(table_model).limit(BATCH_SIZE).offset(processed)

                result = await sqlite_session.execute(stmt)
                records = result.scalars().all()

                if not records:
                    break

                # Insert into Postgres
                for record in records:
                    # Detach from session to avoid tracking issues
                    sqlite_session.expunge(record)
                    
                    # Merge into Postgres session (using merge to handle potential conflicts if ID exists)
                    # For migration, we usually want to keep IDs.
                    # We clone the object to avoid session attachment issues
                    data = {c.name: getattr(record, c.name) for c in table_model.__table__.columns}
                    
                    # Special handling for boolean fields (SQLite might store as 0/1, Postgres needs bool)
                    # SQLAlchemy usually handles this, but let's be safe if raw SQL was used
                    
                    # Insert or update
                    # We use merge to be safe, though it might be slower than bulk insert
                    # For performance, we could use bulk_insert_mappings if we are sure of no conflicts
                    # But merge is safer for "idempotency"
                    await pg_session.merge(table_model(**data))
                    
                    if hasattr(table_model, 'id'):
                        start_id = getattr(record, 'id') + 1

                await pg_session.commit()
                processed += len(records)
                print(f"  Processed {processed}/{total_count} records...", end='\r')

            print(f"\n  Finished table: {table_name}")
            
            # Reset sequence in Postgres
            if hasattr(table_model, 'id'):
                print(f"  Resetting sequence for {table_name}...")
                try:
                    # Get max id again
                    max_id = await pg_session.scalar(select(func.max(table_model.id)))
                    if max_id:
                        seq_name = f"{table_name}_id_seq"
                        # Check if sequence exists (standard naming convention)
                        await pg_session.execute(text(f"SELECT setval('{seq_name}', {max_id})"))
                        await pg_session.commit()
                except Exception as e:
                    print(f"  Warning: Could not reset sequence for {table_name}: {e}")

    print("Migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
