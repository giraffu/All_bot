
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure src is in path
sys.path.insert(0, os.path.abspath('.'))

from src.api_client import listen_for_progress
from src.services.task_service import TaskService


def test_api_client_no_normalization():
    """
    Test that listen_for_progress DOES NOT normalize queue_remaining to queue_pos anymore.
    """
    async def run_test():
        task_id = "test_task_1"
        
        # Mock response with queue_remaining only
        mock_resp_pending = MagicMock()
        mock_resp_pending.json.return_value = {
            "status": "pending",
            "queue_remaining": 5
        }
        mock_resp_pending.raise_for_status = MagicMock()

        mock_resp_done = MagicMock()
        mock_resp_done.json.return_value = {
            "status": "done",
            "progress": 100
        }
        mock_resp_done.raise_for_status = MagicMock()

        with patch("src.api_client.api_client._request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = [mock_resp_pending, mock_resp_done]

            results = []
            async for info in listen_for_progress(task_id):
                results.append(info)
                
            # Verify first yield
            assert results[0]["status"] == "pending"
            assert results[0]["queue_remaining"] == 5
            # queue_pos should NOT be in info unless backend sent it
            assert "queue_pos" not in results[0] 
            
            assert results[1]["status"] == "done"
            
    asyncio.run(run_test())

def test_task_service_queue_logic_new():
    """
    Test TaskService._monitor_task_progress uses queue_pos (0-based) and queue_remaining correctly.
    """
    async def run_test():
        task_id = "test_task_2"
        mock_status_msg = AsyncMock()
        
        # Mock generator
        async def mock_monitor_func(_tid, is_video=False):
            # 1. New API: queue_pos=0 (front), queue_remaining=1 (maybe)
            yield {"status": "pending", "queue_pos": 0, "queue_remaining": 1}
            
            # 2. Legacy/Fallback: queue_pos missing, queue_remaining=5
            yield {"status": "pending", "queue_remaining": 5}
            
            # 3. Done
            yield {"status": "done", "progress": 100}

        # Mock image_service (though not strictly needed if we provide data in generator)
        with patch("src.services.task_service.image_service"):

            
            with patch("src.services.task_service.robust_edit_text", new_callable=AsyncMock) as mock_edit:
                
                await TaskService._monitor_task_progress(
                    task_id, 
                    mock_status_msg, 
                    is_video=False, 
                    monitor_func=mock_monitor_func
                )
                
                calls = mock_edit.call_args_list
                call_args = [str(c) for c in calls]
                
                # Check 1: queue_pos=0 -> display "第 1 位"
                assert any("第 1 位" in c for c in call_args), f"Should display '第 1 位' for queue_pos=0. Got: {call_args}"
                
                # Check 2: queue_remaining=5 -> display "第 5 位"
                assert any("第 5 位" in c for c in call_args), f"Should display '第 5 位' for queue_remaining=5. Got: {call_args}"

    asyncio.run(run_test())

if __name__ == "__main__":
    test_api_client_no_normalization()
    test_task_service_queue_logic_new()
    print("All tests passed!")
