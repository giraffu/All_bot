
import pytest
import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure src is in path
sys.path.insert(0, os.path.abspath('.'))

from src.api_client import listen_for_progress
from src.services.task_service import TaskService

def test_api_client_normalization():
    """
    Test that listen_for_progress normalizes queue_remaining to queue_pos
    """
    async def run_test():
        task_id = "test_task_1"
        
        # Mock response with queue_remaining
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

        with patch("src.api_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            
            # side_effect for get(): first pending, then done
            mock_client.get.side_effect = [mock_resp_pending, mock_resp_done]

            results = []
            async for info in listen_for_progress(task_id):
                results.append(info)
                
            # Verify first yield has queue_pos
            assert results[0]["status"] == "pending"
            assert results[0]["queue_remaining"] == 5
            assert results[0]["queue_pos"] == 5  # This confirms normalization works
            
            assert results[1]["status"] == "done"
            
    asyncio.run(run_test())

def test_task_service_queue_logic():
    """
    Test TaskService._monitor_task_progress uses queue_pos correctly
    """
    async def run_test():
        task_id = "test_task_2"
        mock_status_msg = AsyncMock()
        
        # Mock generator
        async def mock_monitor_func(tid, is_video=False):
            # 1. Pending with queue_remaining (normalized to queue_pos by api_client, but here we simulate what TaskService receives)
            yield {"status": "pending", "queue_remaining": 3, "queue_pos": 3}
            # 2. Pending without queue info -> should trigger explicit fetch
            yield {"status": "pending"}
            # 3. Done
            yield {"status": "done", "progress": 100}

        # Mock image_service.get_queue_position
        # We need to patch the image_service imported in task_service
        with patch("src.services.task_service.image_service") as mock_img_svc:
            mock_img_svc.get_queue_position = AsyncMock(return_value={"position": 1})
            
            # We also need to patch robust_edit_text since it's imported in task_service
            with patch("src.services.task_service.robust_edit_text", new_callable=AsyncMock) as mock_edit:
                
                await TaskService._monitor_task_progress(
                    task_id, 
                    mock_status_msg, 
                    is_video=False, 
                    monitor_func=mock_monitor_func
                )
                
                # Verify calls
                # 1. First pending: queue_pos=3. 
                # Logic: if queue_pos != last_queue_pos (None) -> edit text
                # Expect: "⏳ 排队中... (第 3 位)"
                
                # 2. Second pending: queue_pos missing in info -> call get_queue_position -> returns 1
                # Logic: queue_pos=1. 1 != 3 -> edit text
                # Expect: "⏳ 排队中... (第 1 位)"
                
                # 3. Done -> "100%"
                
                calls = mock_edit.call_args_list
                print("\nrobust_edit_text calls:")
                for c in calls:
                    print(c)
                    
                # assertions
                # Find call with "第 3 位"
                assert any("第 3 位" in str(c) for c in calls), "Should report position 3"
                # Find call with "第 1 位"
                assert any("第 1 位" in str(c) for c in calls), "Should report position 1 (fetched explicitly)"
                
                # Verify explicit fetch was called
                mock_img_svc.get_queue_position.assert_called_with(task_id)

    asyncio.run(run_test())
