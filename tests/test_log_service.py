import asyncio
import os
import unittest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete

# Add src to path if needed, but assuming run from root
import sys
sys.path.append(os.getcwd())

from src.database.models import Base, UserLog
from src.services.log_service import LogService

TEST_DB_URL = "sqlite+aiosqlite:///test_log_system.db"

class TestLogService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Setup test DB
        self.engine = create_async_engine(TEST_DB_URL, echo=False)
        self.AsyncSessionLocal = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Patch the session maker in LogService module
        self.patcher = patch('src.services.log_service.AsyncSessionLocal', new=self.AsyncSessionLocal)
        self.patcher.start()

    async def asyncTearDown(self):
        self.patcher.stop()
        await self.engine.dispose()
        if os.path.exists("test_log_system.db"):
            try:
                os.remove("test_log_system.db")
            except PermissionError:
                pass

    async def test_log_action(self):
        """Test basic logging action"""
        result = await LogService.log_action(
            user_id=12345,
            username="test_user",
            operation_type="test_op",
            credit_change=10,
            current_balance=100,
            extra_info={"foo": "bar"}
        )
        self.assertTrue(result)

        # Verify insertion
        async with self.AsyncSessionLocal() as session:
            stmt = select(UserLog).where(UserLog.user_id == 12345)
            result = await session.execute(stmt)
            log = result.scalar_one()
            
            self.assertEqual(log.user_id, 12345)
            self.assertEqual(log.credit_change, 10)
            self.assertEqual(log.current_balance, 100)
            self.assertEqual(log.operation_type, "test_op")
            
            # Check JSON
            extra = json.loads(log.extra_info)
            self.assertEqual(extra["foo"], "bar")

    async def test_get_logs_pagination(self):
        """Test query pagination and filtering"""
        # Insert multiple logs
        for i in range(10):
            await LogService.log_action(
                user_id=1, 
                username="u1", 
                operation_type="op1" if i % 2 == 0 else "op2", 
                credit_change=i, 
                current_balance=100+i
            )

        # Test filtering by user_id
        logs = await LogService.get_logs(user_id=1, page_size=5)
        self.assertEqual(logs['total'], 10)
        self.assertEqual(len(logs['items']), 5)
        self.assertEqual(logs['total_pages'], 2)

        # Test filtering by operation_type
        logs = await LogService.get_logs(operation_type="op1", page_size=10)
        self.assertEqual(logs['total'], 5)
        self.assertEqual(len(logs['items']), 5)

        # Test empty result
        logs = await LogService.get_logs(user_id=999)
        self.assertEqual(logs['total'], 0)

    async def test_cleanup_logs(self):
        """Test log cleanup"""
        # Insert an old log manually
        old_date = datetime.now() - timedelta(days=100)
        
        async with self.AsyncSessionLocal() as session:
            old_log = UserLog(
                user_id=999,
                username="old",
                operation_type="old_op",
                credit_change=0,
                current_balance=0,
                created_at=old_date,
                extra_info="{}"
            )
            session.add(old_log)
            await session.commit()
            
            # Verify it exists
            stmt = select(UserLog).where(UserLog.user_id == 999)
            res = await session.execute(stmt)
            self.assertIsNotNone(res.scalar_one_or_none())

        # Cleanup logs older than 90 days
        deleted = await LogService.cleanup_old_logs(days=90)
        self.assertEqual(deleted, 1)
        
        # Verify it's gone
        async with self.AsyncSessionLocal() as session:
            stmt = select(UserLog).where(UserLog.user_id == 999)
            res = await session.execute(stmt)
            self.assertIsNone(res.scalar_one_or_none())

    async def test_retry_mechanism(self):
        """Test retry logic by mocking failure"""
        from sqlalchemy.exc import SQLAlchemyError
        from unittest.mock import AsyncMock
        
        # Create a mock that works as an async context manager
        class MockSession:
            def __init__(self):
                self.add = MagicMock()
                self.rollback = AsyncMock()
                self.commit = AsyncMock(side_effect=SQLAlchemyError("DB Error"))
            
            async def __aenter__(self):
                return self
                
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
                
        mock_session_instance = MockSession()
        mock_session_maker = MagicMock(return_value=mock_session_instance)
        
        with patch('src.services.log_service.AsyncSessionLocal', mock_session_maker):
            result = await LogService.log_action(1, "u", "op", 0, 0, max_retries=2)
            self.assertFalse(result)
            
            # Verify it retried (number of attempts = max_retries)
            self.assertEqual(mock_session_maker.call_count, 2)

if __name__ == '__main__':
    unittest.main()
