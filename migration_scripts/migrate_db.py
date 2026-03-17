import sqlite3
import psycopg2
import psycopg2.extras
import logging
import csv
import os
import re
import time
from datetime import datetime

# Configuration
SQLITE_DB_PATH = "/home/hfy/APP/All_bot/bot_data.db"
PG_HOST = "192.168.1.115"
PG_PORT = "5432"
PG_DB = "bot_db"
PG_USER = "postgres"
PG_PASS = "postgrespassword"

REPORT_FILE = "db_migration_report.csv"
DDL_FILE = "postgres_schema.sql"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("db_migration.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_pg_connection():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASS
    )

def get_sqlite_connection():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def setup_log_table(pg_conn):
    cur = pg_conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS migrate_error_log (
                id SERIAL PRIMARY KEY,
                table_name TEXT,
                batch_range TEXT,
                error_message TEXT,
                failed_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        
        # Create migration summary view
        cur.execute("""
            CREATE TABLE IF NOT EXISTS migration_summary_table (
                table_name TEXT PRIMARY KEY,
                source_rows BIGINT,
                target_rows BIGINT,
                duration_seconds NUMERIC,
                status TEXT,
                validation_result TEXT
            );
        """)
        
        cur.execute("""
            CREATE OR REPLACE VIEW v_migration_summary AS
            SELECT * FROM migration_summary_table;
        """)
        
        pg_conn.commit()
    except Exception as e:
        pg_conn.rollback()
        logger.error(f"Failed to setup log tables: {e}")
        raise
    finally:
        cur.close()

def map_sqlite_type_to_pg(sqlite_type):
    sqlite_type = sqlite_type.upper()
    if "INT" in sqlite_type:
        if "BIG" in sqlite_type:
            return "BIGINT"
        return "INTEGER" # Can be BIGINT to be safe
    if "CHAR" in sqlite_type or "TEXT" in sqlite_type:
        return "TEXT"
    if "BLOB" in sqlite_type:
        return "BYTEA"
    if "REAL" in sqlite_type or "FLOAT" in sqlite_type or "DOUBLE" in sqlite_type:
        return "DOUBLE PRECISION"
    if "BOOLEAN" in sqlite_type:
        return "BOOLEAN"
    if "DATE" in sqlite_type:
        if "TIME" in sqlite_type:
            return "TIMESTAMPTZ"
        return "DATE"
    return "TEXT" # Default

def extract_schema_and_generate_ddl():
    sqlite_conn = get_sqlite_connection()
    cursor = sqlite_conn.cursor()
    
    # Get list of tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]
    
    ddl_statements = []
    ordered_tables = [] # To handle dependencies roughly
    
    # Simple dependency handling: Users first
    if "users" in tables:
        tables.remove("users")
        ordered_tables.append("users")
    ordered_tables.extend(tables)
    
    for table in ordered_tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        
        cursor.execute(f"PRAGMA foreign_key_list({table})")
        fks = cursor.fetchall()
        
        # Build CREATE TABLE
        col_defs = []
        pk_cols = []
        
        for col in columns:
            cid, name, type_, notnull, dflt_value, pk = col
            pg_type = map_sqlite_type_to_pg(type_)
            
            # Handle Auto Increment and PK
            # SQLite: INTEGER PRIMARY KEY is rowid alias (autoincrement)
            if pk > 0:
                pk_cols.append(name)
                if type_.upper() == "INTEGER": # Likely autoincrement
                     # Check if it's actually AUTOINCREMENT in sqlite_master
                    cursor.execute(f"SELECT sql FROM sqlite_master WHERE name='{table}'")
                    create_sql = cursor.fetchone()[0]
                    if "AUTOINCREMENT" in create_sql.upper():
                        pg_type = "SERIAL"
            
            col_def = f'"{name}" {pg_type}'
            
            if notnull:
                col_def += " NOT NULL"
            
            if dflt_value is not None:
                # Clean up default value (sqlite sometimes quotes '0' or CURRENT_TIMESTAMP)
                dflt_upper = str(dflt_value).upper()
                if dflt_upper == "CURRENT_TIMESTAMP":
                    col_def += " DEFAULT NOW()"
                elif dflt_upper == "CURRENT_DATE":
                    col_def += " DEFAULT CURRENT_DATE"
                elif pg_type == "BOOLEAN":
                    if dflt_upper in ("0", "FALSE", "'0'"):
                        col_def += " DEFAULT FALSE"
                    elif dflt_upper in ("1", "TRUE", "'1'"):
                        col_def += " DEFAULT TRUE"
                    else:
                         col_def += f" DEFAULT {dflt_value}"
                else:
                    col_def += f" DEFAULT {dflt_value}"
            
            col_defs.append(col_def)

        # Primary Key constraint
        if pk_cols:
            # If single serial PK, it's already handled by SERIAL type usually implies PK? 
            # No, SERIAL is just type. Need PRIMARY KEY.
            # If we used SERIAL for a column, we still add PRIMARY KEY constraint or inline it.
            # Let's add constraint at the end.
            pk_str = ", ".join([f'"{c}"' for c in pk_cols])
            col_defs.append(f"PRIMARY KEY ({pk_str})")

        # Foreign Keys
        for fk in fks:
            id_, seq, table_to, from_, to_, on_update, on_delete, match = fk
            fk_def = f'FOREIGN KEY ("{from_}") REFERENCES "{table_to}" ("{to_}")'
            # Add ON DELETE/UPDATE if needed, skipping for now to keep simple/safe
            col_defs.append(fk_def)
            
        drop_stmt = f"DROP TABLE IF EXISTS \"{table}\" CASCADE;"
        create_stmt = f"CREATE TABLE \"{table}\" (\n    " + ",\n    ".join(col_defs) + "\n);"
        ddl_statements.append(drop_stmt)
        ddl_statements.append(create_stmt)
        
        # Indexes
        cursor.execute(f"PRAGMA index_list({table})")
        indexes = cursor.fetchall()
        for idx in indexes:
            seq, name, unique, origin, partial = idx
            if origin == 'pk': continue # Skip PK indexes
            
            cursor.execute(f"PRAGMA index_info({name})")
            idx_cols = cursor.fetchall()
            col_names = [f'"{r[2]}"' for r in idx_cols]
            
            unique_str = "UNIQUE" if unique else ""
            idx_stmt = f"CREATE {unique_str} INDEX IF NOT EXISTS \"{name}\" ON \"{table}\" ({', '.join(col_names)});"
            ddl_statements.append(idx_stmt)

    sqlite_conn.close()
    return ddl_statements, ordered_tables

def execute_ddl(pg_conn, ddl_statements):
    cur = pg_conn.cursor()
    try:
        for stmt in ddl_statements:
            cur.execute(stmt)
        pg_conn.commit()
        logger.info("DDL executed successfully.")
    except Exception as e:
        pg_conn.rollback()
        logger.error(f"DDL execution failed: {e}")
        raise
    finally:
        cur.close()

def migrate_data(pg_conn, sqlite_conn, tables):
    BATCH_SIZE = 10000
    
    # Disable FK constraints temporarily?
    # Better to insert in order. We sorted tables roughly.
    # Users first.
    
    summary_data = []
    
    # Disable FK checks
    cur = pg_conn.cursor()
    cur.execute("SET session_replication_role = 'replica';")
    pg_conn.commit()
    cur.close()

    for table in tables:
        start_time = time.time()
        logger.info(f"Migrating table {table}...")
        
        # Get columns
        pg_cur = pg_conn.cursor()
        # Verify columns exist in PG to avoid errors
        pg_cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'")
        pg_cols = [row[0] for row in pg_cur.fetchall()]
        pg_cur.close()
        
        # Prepare SQLite Select
        sl_cur = sqlite_conn.cursor()
        sl_cur.execute(f"SELECT * FROM \"{table}\"")
        
        # Get SQLite column names
        sl_cols = [description[0] for description in sl_cur.description]
        
        # Map columns (assuming same names)
        common_cols = [c for c in sl_cols if c in pg_cols]
        cols_str = ", ".join([f'"{c}"' for c in common_cols])
        
        total_rows = 0
        failed_batches = 0
        
        while True:
            rows = sl_cur.fetchmany(BATCH_SIZE)
            if not rows:
                break
            
            # Convert rows to suitable format (e.g. handle booleans)
            # Psycopg2 execute_values handles most.
            
            pg_cur = pg_conn.cursor()
            try:
                # Use COPY if possible, but execute_values is safer for types
                # prompt asks for COPY.
                # To use COPY, we need a CSV-like buffer.
                # Let's use execute_values for reliability with types, 
                # OR implement COPY with proper CSV escaping.
                # Given "COPY mode" requirement:
                
                from io import StringIO
                buffer = StringIO()
                writer = csv.writer(buffer)
                # Filter rows to common columns
                # Need to map row data to common_cols
                col_indices = [sl_cols.index(c) for c in common_cols]
                
                filtered_rows = []
                for row in rows:
                    filtered_row = [row[i] for i in col_indices]
                    # Handle boolean conversion for Postgres COPY (t/f or 1/0)
                    # Psycopg2 copy_expert expects text.
                    # Let's try execute_values first as it's cleaner, but prompt demanded COPY.
                    # Okay, I will use copy_from with a generator or StringIO
                    writer.writerow(filtered_row)
                    
                buffer.seek(0)
                
                pg_cur.copy_expert(f"COPY \"{table}\" ({cols_str}) FROM STDIN WITH CSV", buffer)
                pg_conn.commit()
                total_rows += len(rows)
                
            except Exception as e:
                pg_conn.rollback()
                logger.error(f"Batch failed for {table}: {e}")
                # Log to DB
                log_cur = pg_conn.cursor()
                log_cur.execute("INSERT INTO migrate_error_log (table_name, error_message) VALUES (%s, %s)", (table, str(e)))
                log_cur.close()
                pg_conn.commit() # Commit the log
                failed_batches += 1
            finally:
                pg_cur.close()
                buffer.close()
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Validation
        sl_count_cur = sqlite_conn.cursor()
        sl_count_cur.execute(f"SELECT COUNT(*) FROM \"{table}\"")
        src_count = sl_count_cur.fetchone()[0]
        
        pg_count_cur = pg_conn.cursor()
        pg_count_cur.execute(f"SELECT COUNT(*) FROM \"{table}\"")
        tgt_count = pg_count_cur.fetchone()[0]
        
        status = "SUCCESS"
        if src_count != tgt_count or failed_batches > 0:
            status = "FAILED"
            logger.error(f"Table {table} migration failed. Src: {src_count}, Tgt: {tgt_count}, Failed Batches: {failed_batches}")
        
        # Record summary
        summary_cur = pg_conn.cursor()
        summary_cur.execute("""
            INSERT INTO migration_summary_table (table_name, source_rows, target_rows, duration_seconds, status, validation_result)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (table_name) DO UPDATE SET 
            source_rows=EXCLUDED.source_rows, target_rows=EXCLUDED.target_rows, 
            duration_seconds=EXCLUDED.duration_seconds, status=EXCLUDED.status;
        """, (table, src_count, tgt_count, duration, status, f"Diff: {src_count - tgt_count}"))
        pg_conn.commit()
        summary_cur.close()

def main():
    pg_conn = get_pg_connection()
    sl_conn = get_sqlite_connection()
    
    try:
        # 1. Setup Logs
        setup_log_table(pg_conn)
        
        # 2. Extract & DDL
        ddl_stmts, tables = extract_schema_and_generate_ddl()
        
        # Save DDL
        with open(DDL_FILE, 'w') as f:
            f.write("\n".join(ddl_stmts))
        
        # 3. Execute DDL
        execute_ddl(pg_conn, ddl_stmts)
        
        # 4. Migrate Data
        migrate_data(pg_conn, sl_conn, tables)
        
        logger.info("Migration finished.")
        print("Migration finished. Check logs and report.")
        
    except Exception as e:
        logger.error(f"Critical error: {e}")
    finally:
        pg_conn.close()
        sl_conn.close()

if __name__ == "__main__":
    main()
