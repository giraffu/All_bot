import pytest
import os
from unittest.mock import patch, MagicMock
from app.config import settings

def test_system_status(client, mock_queue_manager):
    # This endpoint does not require auth
    mock_queue_manager.get_queue_metrics_by_type.return_value = {
        "img2img": 2,
        "face_swap": 1,
        "video_insert": 1,
        "video_edit": 1
    }
    
    response = client.get("/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["queue_size"] == 5
    assert data["active_workers"] == 1
    assert data["comfy_online"] is True
    assert data["queue_by_type"]["img2img"] == 2

def test_img2img_auth_success(client, auth_headers, mock_queue_manager):
    mock_queue_manager.enqueue_task.return_value = "img2img-task-123"
    
    with patch("app.main.save_upload_file", return_value="test.png"):
        response = client.post(
            "/comfy_img2img",
            headers=auth_headers,
            files={"image": ("test.png", b"fake-image-data", "image/png")},
            data={"prompt": "test prompt", "priority": 0}
        )
    
    assert response.status_code == 200
    assert response.json()["task_id"] == "img2img-task-123"

def test_face_swap_auth_success(client, auth_headers, mock_queue_manager):
    mock_queue_manager.enqueue_task.return_value = "faceswap-task-123"
    
    with patch("app.main.save_upload_file", return_value="test.png"):
        response = client.post(
            "/face_swap",
            headers=auth_headers,
            files={
                "face_image": ("face.png", b"fake-data", "image/png"),
                "body_image": ("body.png", b"fake-data", "image/png")
            },
            data={"priority": 0}
        )
    
    assert response.status_code == 200
    assert response.json()["task_id"] == "faceswap-task-123"

def test_video_insert_auth_success(client, auth_headers, mock_queue_manager):
    mock_queue_manager.enqueue_task.return_value = "video-insert-task-123"
    
    with patch("app.main.save_upload_file", return_value="test.png"):
        response = client.post(
            "/perfect_video_insert",
            headers=auth_headers,
            files={"image": ("test.png", b"fake-data", "image/png")},
            data={"prompt": "test prompt", "priority": 0, "width": 512, "height": 512, "length": 81}
        )
    
    assert response.status_code == 200
    assert response.json()["task_id"] == "video-insert-task-123"

def test_video_edit_auth_success(client, auth_headers, mock_queue_manager):
    mock_queue_manager.enqueue_task.return_value = "video-edit-task-123"
    
    with patch("app.main.save_upload_file", return_value="test.png"):
        response = client.post(
            "/perfect_video_edit",
            headers=auth_headers,
            files={"image": ("test.png", b"fake-data", "image/png")},
            data={"prompt": "test prompt", "priority": 0, "width": 512, "height": 512, "length": 81}
        )
    
    assert response.status_code == 200
    assert response.json()["task_id"] == "video-edit-task-123"

def test_get_task_status(client, mock_queue_manager):
    # Mock return value for status
    mock_queue_manager.get_task_status.return_value = {
        "status": "pending",
        "progress": 0.5,
        "queue_pos": 2,
        "result_path": None,
        "error_msg": None
    }
    mock_queue_manager.get_queue_position.return_value = 2
    
    response = client.get("/status/task-123")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["queue_pos"] == 2
    assert data["progress"] == 0.5

def test_get_task_status_not_found(client, mock_queue_manager):
    mock_queue_manager.get_task_status.return_value = None
    response = client.get("/status/non-existent")
    assert response.status_code == 404

def test_get_task_image_success(client, mock_queue_manager):
    mock_queue_manager.get_task_status.return_value = {
        "status": "done",
        "result_path": "output.png"
    }
    
    # Mock os.path.exists and FileResponse
    with patch("os.path.exists", return_value=True), \
         patch("app.main.FileResponse") as mock_file_response:
        
        mock_file_response.return_value = "mock_file_response"
        response = client.get("/image/task-123")
        
        # In TestClient, FileResponse isn't fully processed like in a real server unless we read content
        # But here we just check if it didn't error 404
        assert response.status_code == 200 or response == "mock_file_response"

def test_get_task_image_not_ready(client, mock_queue_manager):
    mock_queue_manager.get_task_status.return_value = {
        "status": "pending",
        "result_path": None
    }
    response = client.get("/image/task-123")
    assert response.status_code == 404
    assert response.json()["detail"] == "Image not ready"

def test_get_task_video_success(client, mock_queue_manager):
    mock_queue_manager.get_task_status.return_value = {
        "status": "done",
        "result_path": "output.mp4"
    }
    
    with patch("os.path.exists", return_value=True), \
         patch("app.main.FileResponse") as mock_file_response:
        
        mock_file_response.return_value = "mock_file_response"
        response = client.get("/video/task-123")
        assert response.status_code == 200 or response == "mock_file_response"

