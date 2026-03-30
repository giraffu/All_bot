import pytest
import asyncio
import os
import json
from unittest.mock import patch, MagicMock, AsyncMock
from app.models import TaskType, TaskStatus, T2ITaskResponse
from app.config import settings

def test_create_t2i_task_async_success(client, auth_headers, mock_queue_manager):
    # Mock return value
    mock_queue_manager.enqueue_task.return_value = "t2i-task-123"
    
    response = client.post(
        "/api/v1/workflows/t2i-pornmaster-turbo",
        headers=auth_headers,
        json={"prompt": "a beautiful landscape"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "t2i-task-123"
    assert data.get("image_url") is None

def test_create_t2i_task_sync_success(client, auth_headers, mock_queue_manager):
    # Mock return value
    mock_queue_manager.enqueue_task.return_value = "t2i-task-123"
    
    # Mock status sequence: pending -> running -> done
    mock_queue_manager.get_task_status.side_effect = [
        {"status": "pending"},
        {"status": "running"},
        {"status": "done", "result_path": "output.png"}
    ]
    
    # Speed up asyncio.sleep and mock loop time
    with patch("asyncio.sleep", return_value=None), \
         patch("asyncio.get_event_loop") as mock_loop:
        
        mock_loop.return_value.time.side_effect = [0, 1, 2, 3]
        
        response = client.post(
            "/api/v1/workflows/t2i-pornmaster-turbo?async=false",
            headers=auth_headers,
            json={"prompt": "a beautiful landscape"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "t2i-task-123"
    assert "output.png" in data["image_url"]
    assert data["image_url"].startswith("http")

def test_create_t2i_task_invalid_prompt(client, auth_headers):
    # Empty prompt
    response = client.post(
        "/api/v1/workflows/t2i-pornmaster-turbo",
        headers=auth_headers,
        json={"prompt": ""}
    )
    assert response.status_code == 400
    
    # Long prompt (>512)
    response = client.post(
        "/api/v1/workflows/t2i-pornmaster-turbo",
        headers=auth_headers,
        json={"prompt": "a" * 513}
    )
    assert response.status_code == 400
    
    # Missing prompt
    response = client.post(
        "/api/v1/workflows/t2i-pornmaster-turbo",
        headers=auth_headers,
        json={}
    )
    assert response.status_code == 400

def test_create_t2i_task_comfy_failure(client, auth_headers, mock_queue_manager):
    # Mock return value
    mock_queue_manager.enqueue_task.return_value = "t2i-task-123"
    
    # Mock failure
    mock_queue_manager.get_task_status.return_value = {
        "status": "error",
        "error_msg": "ComfyUI disconnected"
    }
    
    with patch("asyncio.sleep", return_value=None), \
         patch("asyncio.get_event_loop") as mock_loop:
        
        mock_loop.return_value.time.side_effect = [0, 1]
        
        response = client.post(
            "/api/v1/workflows/t2i-pornmaster-turbo?async=false",
            headers=auth_headers,
            json={"prompt": "a beautiful landscape"}
        )
    
    assert response.status_code == 500
    assert "ComfyUI disconnected" in response.json()["detail"]

def test_create_t2i_task_sync_timeout(client, auth_headers, mock_queue_manager):
    # Mock return value
    mock_queue_manager.enqueue_task.return_value = "t2i-task-123"
    
    # Always running
    mock_queue_manager.get_task_status.return_value = {"status": "running"}
    
    # Mock time to simulate timeout
    with patch("asyncio.sleep", return_value=None), \
         patch("asyncio.get_event_loop") as mock_loop:
        
        # Initial call, then after 60s
        mock_loop.return_value.time.side_effect = [0, 61]
        
        response = client.post(
            "/api/v1/workflows/t2i-pornmaster-turbo?async=false",
            headers=auth_headers,
            json={"prompt": "a beautiful landscape"}
        )
    
    assert response.status_code == 504

def test_get_task_status_v1(client, mock_queue_manager):
    # Mock done status
    mock_queue_manager.get_task_status.return_value = {
        "status": "done",
        "result_path": "output.png",
        "progress": 1.0
    }
    
    response = client.get("/api/v1/tasks/task-123")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["result_path"] == "output.png"

@pytest.mark.asyncio
async def test_worker_retry_logic():
    from app.worker import Worker
    from app.comfy_client import ComfyClient
    from app.queue_manager import QueueManager
    
    mock_qm = AsyncMock(spec=QueueManager)
    mock_cc = AsyncMock(spec=ComfyClient)
    
    worker = Worker(mock_qm, mock_cc)
    
    # Mock task data
    task_id = "task-123"
    task_data = {
        "type": TaskType.T2I_PORNMASTER_TURBO,
        "params": '{"prompt": "test"}'
    }
    
    # Mock comfy_client to fail twice then succeed
    mock_cc.queue_prompt.side_effect = [
        Exception("Conn error 1"),
        Exception("Conn error 2"),
        "prompt-id-success"
    ]
    
    # Mock internal methods
    with patch.object(worker, "load_workflow", return_value={"node": "data"}), \
         patch.object(worker, "patch_workflow", return_value={"node": "patched"}), \
         patch("asyncio.sleep", return_value=None), \
         patch("builtins.open", MagicMock()), \
         patch("os.path.exists", return_value=True):
        
        await worker.process_task(task_id, task_data)
        
    assert mock_cc.queue_prompt.call_count == 3
    mock_qm.set_prompt_id.assert_called_with(task_id, "prompt-id-success")

@pytest.mark.asyncio
async def test_worker_retry_max_reached():
    from app.worker import Worker
    from app.comfy_client import ComfyClient
    from app.queue_manager import QueueManager
    
    mock_qm = AsyncMock(spec=QueueManager)
    mock_cc = AsyncMock(spec=ComfyClient)
    
    worker = Worker(mock_qm, mock_cc)
    
    # Mock task data
    task_id = "task-123"
    task_data = {
        "type": TaskType.T2I_PORNMASTER_TURBO,
        "params": '{"prompt": "test"}'
    }
    
    # Mock comfy_client to always fail
    mock_cc.queue_prompt.side_effect = Exception("Permanent failure")
    
    # Mock internal methods
    with patch.object(worker, "load_workflow", return_value={"node": "data"}), \
         patch.object(worker, "patch_workflow", return_value={"node": "patched"}), \
         patch("asyncio.sleep", return_value=None), \
         patch("builtins.open", MagicMock()), \
         patch("os.path.exists", return_value=True):
        
        await worker.process_task(task_id, task_data)
        
    assert mock_cc.queue_prompt.call_count == 3
    mock_qm.fail_task.assert_called_with(task_id, "Permanent failure")
