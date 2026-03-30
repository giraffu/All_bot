import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app as fastapi_app, get_queue_manager
from app.queue_manager import QueueManager
from app.config import settings
import app.main

@pytest.fixture
def mock_queue_manager():
    qm = AsyncMock(spec=QueueManager)
    qm.enqueue_task.return_value = "mock-task-id"
    qm.get_task_status.return_value = {
        "status": "pending",
        "progress": 0.0,
        "queue_pos": 0,
        "result_path": "test_output.png"
    }
    qm.get_queue_size.return_value = 5
    qm.get_active_workers_count.return_value = 1
    qm.get_queue_position.return_value = 0
    return qm

@pytest.fixture
def client(mock_queue_manager):
    # Override dependency
    fastapi_app.dependency_overrides[get_queue_manager] = lambda: mock_queue_manager
    
    # Patch global comfy_client
    # We need to access the module where comfy_client is defined to patch it if it's used as a global
    original_check = app.main.comfy_client.check_connection
    app.main.comfy_client.check_connection = AsyncMock(return_value=True)
    
    with TestClient(fastapi_app) as c:
        yield c
    
    # Cleanup
    fastapi_app.dependency_overrides = {}
    app.main.comfy_client.check_connection = original_check

@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {settings.auth_token}"}
