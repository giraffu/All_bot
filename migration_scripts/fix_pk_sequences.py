import psycopg2
import logging

# Configuration
PG_HOST = "192.168.1.115"
PG_PORT = "5432"
PG_DB = "bot_db"
PG_USER = "postgres"
PG_PASS = "postgrespassword"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_pg_connection():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASS
    )

def fix_autoincrement(table_name, id_column="id"):
    conn = get_pg_connection()
    cur = conn.cursor()
    try:
        # Check if sequence already exists (simple check by trying to create)
        seq_name = f"{table_name}_{id_column}_seq"
        
        logger.info(f"Fixing {table_name}...")
        
        # 1. Create Sequence if not exists
        cur.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name};")
        
        # 2. Set default value for ID column
        cur.execute(f"ALTER TABLE \"{table_name}\" ALTER COLUMN \"{id_column}\" SET DEFAULT nextval('{seq_name}');")
        
        # 3. Sync sequence value with max ID
        cur.execute(f"SELECT MAX(\"{id_column}\") FROM \"{table_name}\";")
        max_id = cur.fetchone()[0]
        if max_id is None:
            max_id = 0
        
        cur.execute(f"SELECT setval('{seq_name}', {max_id});")
        
        # 4. Bind sequence to column
        cur.execute(f"ALTER SEQUENCE {seq_name} OWNED BY \"{table_name}\".\"{id_column}\";")
        
        conn.commit()
        logger.info(f"Fixed {table_name}: Sequence {seq_name} set to {max_id}")
        
    except Exception as e:
        logger.error(f"Error fixing {table_name}: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def main():
    # List of tables that need autoincrement PK
    # Users table uses Telegram ID, so it is NOT autoincrement.
    tables_to_fix = [
        "permissions",
        "referrals",
        "history",
        "conversations",
        "template_contributions",
        "checkin_history",
        "user_logs"
    ]
    
    for table in tables_to_fix:
        fix_autoincrement(table)

if __name__ == "__main__":
    main()
