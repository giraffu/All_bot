import unittest
import logging
import json
import io
from sqlalchemy import create_engine, text
from src.database.logger import setup_db_logging
from src.context import user_id_ctx

class TestDBLogging(unittest.TestCase):
    def setUp(self):
        self.log_capture = io.StringIO()
        self.handler = logging.StreamHandler(self.log_capture)
        self.logger = logging.getLogger("bot.database")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(self.handler)
        
        self.engine = create_engine("sqlite:///:memory:")
        setup_db_logging(self.engine)

    def tearDown(self):
        self.logger.removeHandler(self.handler)

    def test_logging(self):
        token = user_id_ctx.set(999)
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            user_id_ctx.reset(token)
            
        log_content = self.log_capture.getvalue()
        self.assertTrue(len(log_content) > 0, "No logs captured")
        
        # Parse last line (in case of multiple logs)
        lines = log_content.strip().split('\n')
        last_line = lines[-1]
        
        try:
            data = json.loads(last_line)
        except json.JSONDecodeError:
            self.fail(f"Log is not valid JSON: {last_line}")
            
        self.assertEqual(data['event'], 'db_operation')
        self.assertEqual(data['operation_type'], 'SELECT')
        self.assertEqual(data['user_id'], 999)
        self.assertIn('duration_ms', data)
        self.assertEqual(data['status'], 'success')

if __name__ == '__main__':
    unittest.main()
