import json
import logging
import time
from datetime import datetime

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from src.context import user_id_ctx

db_logger = logging.getLogger("bot.database")

def setup_db_logging(engine):
    """
    Register SQLAlchemy events for database logging.
    Use engine.sync_engine for AsyncEngine compatibility.
    """
    
    # Check if it's an AsyncEngine, if so, get the sync_engine
    target_engine = engine
    if hasattr(engine, 'sync_engine'):
        target_engine = engine.sync_engine

    @event.listens_for(target_engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, _executemany):
        context._query_start_time = time.time()

    @event.listens_for(target_engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, _executemany):
        total = time.time() - context._query_start_time
        
        # Operation type estimation
        op_type = statement.split()[0].upper() if statement else "UNKNOWN"
        
        # Skip logging for SELECT statements to reduce I/O overhead
        # Keep logging for INSERT, UPDATE, DELETE, etc.
        if op_type == "SELECT":
            return

        user_id = user_id_ctx.get()
        
        log_entry = {
            "event": "db_operation",
            "operation_type": op_type,
            "execution_time": datetime.now().isoformat(),
            "duration_ms": round(total * 1000, 2),
            "sql": statement,
            # Be careful with sensitive data in parameters
            "parameters": str(parameters) if parameters else None, 
            "user_id": user_id,
            "status": "success"
        }
        
        # Try to get affected rows if available
        # Note: rowcount is not always reliable or available depending on DB/Driver
        if hasattr(cursor, 'rowcount'):
            log_entry['affected_rows'] = cursor.rowcount

        db_logger.info(json.dumps(log_entry))

    @event.listens_for(target_engine, "handle_error")
    def handle_error(exception_context):
        total = time.time() - exception_context.execution_context._query_start_time
        statement = exception_context.statement
        parameters = exception_context.parameters
        
        op_type = statement.split()[0].upper() if statement else "UNKNOWN"
        user_id = user_id_ctx.get()
        
        error_msg = str(exception_context.original_exception)
        
        is_expected_constraint = False
        if isinstance(exception_context.original_exception, IntegrityError) or \
           "UniqueViolationError" in error_msg or \
           "duplicate key value violates unique constraint" in error_msg:
            is_expected_constraint = True

        log_entry = {
            "event": "db_operation",
            "operation_type": op_type,
            "execution_time": datetime.now().isoformat(),
            "duration_ms": round(total * 1000, 2),
            "sql": statement,
            "parameters": str(parameters) if parameters else None,
            "user_id": user_id,
            "status": "warning_db_conflict" if is_expected_constraint else "failure",
            "error": error_msg
        }
        
        if is_expected_constraint:
            db_logger.warning(json.dumps(log_entry))
        else:
            db_logger.error(json.dumps(log_entry))
