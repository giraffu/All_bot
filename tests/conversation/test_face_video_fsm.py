import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram.ext import ConversationHandler
from src.handlers.conversation_states import FaceVideoState
from src.handlers.fsm.face_video_fsm import (
    start_face_video,
    receive_face_image,
    receive_video,
    process_resolution_selection,
    cancel_conversation,
    timeout_conversation,
    unexpected_input
)

@pytest.fixture
def mock_update():
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.username = "testuser"
    update.effective_user.full_name = "Test User"
    update.message = AsyncMock()
    update.callback_query = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {}
    context.bot = AsyncMock()
    return context

@pytest.mark.asyncio
async def test_start_face_video(mock_update, mock_context):
    """Test entry point of FSM."""
    # Start FSM
    state = await start_face_video(mock_update, mock_context)
    
    assert state == FaceVideoState.WAIT_FACE_IMAGE
    assert mock_context.user_data['in_conversation'] == "FACE_VIDEO"
    assert 'face_video_data' in mock_context.user_data
    
    # Test Concurrency Lock
    state2 = await start_face_video(mock_update, mock_context)
    assert state2 == ConversationHandler.END # Rejected because of lock

@pytest.mark.asyncio
@patch("src.handlers.fsm.face_video_fsm.os.makedirs")
async def test_receive_face_image_valid(mock_makedirs, mock_update, mock_context):
    """Test receiving valid photo."""
    mock_context.user_data['in_conversation'] = "FACE_VIDEO"
    mock_context.user_data['face_video_data'] = {}
    
    mock_update.message.document = None
    mock_photo = MagicMock()
    mock_photo.file_id = "test_file_123"
    mock_update.message.photo = [mock_photo]
    
    mock_file = AsyncMock()
    mock_context.bot.get_file.return_value = mock_file
    
    state = await receive_face_image(mock_update, mock_context)
    
    assert state == FaceVideoState.WAIT_VIDEO
    assert mock_context.user_data['face_video_data']['face_image_path'] == "/tmp/bot_fsm_tmp/test_file_123_face.png"
    mock_file.download_to_drive.assert_called_once()

@pytest.mark.asyncio
async def test_receive_face_image_invalid(mock_update, mock_context):
    """Test receiving invalid photo (text instead of photo)."""
    mock_update.message.document = None
    mock_update.message.photo = []
    
    state = await receive_face_image(mock_update, mock_context)
    
    assert state == FaceVideoState.WAIT_FACE_IMAGE
    mock_update.message.reply_text.assert_called_with("❌ 无法识别。请发送图片！")

@pytest.mark.asyncio
async def test_receive_video_valid(mock_update, mock_context):
    """Test receiving valid video."""
    mock_context.user_data['face_video_data'] = {'face_image_path': '/tmp/test.png'}
    
    mock_update.message.document = None
    mock_video = MagicMock()
    mock_video.file_id = "test_vid_123"
    mock_update.message.video = mock_video
    
    mock_file = AsyncMock()
    mock_context.bot.get_file.return_value = mock_file
    
    state = await receive_video(mock_update, mock_context)
    
    assert state == FaceVideoState.SELECT_RESOLUTION
    assert mock_context.user_data['face_video_data']['video_path'] == "/tmp/bot_fsm_tmp/test_vid_123_video.mp4"

@pytest.mark.asyncio
@patch("src.handlers.fsm.face_video_fsm.permission_service.calculate_user_priority", return_value=1)
@patch("src.handlers.fsm.face_video_fsm.TaskService.process_face_video_task")
async def test_process_resolution_selection(mock_process, mock_priority, mock_update, mock_context):
    """Test successful completion after selecting resolution."""
    mock_context.user_data['in_conversation'] = "FACE_VIDEO"
    mock_context.user_data['face_video_data'] = {
        'face_image_path': '/tmp/face.png',
        'video_path': '/tmp/video.mp4'
    }
    
    mock_update.callback_query.data = "fsm_fv_res_720"
    mock_update.callback_query.from_user.id = 12345
    
    state = await process_resolution_selection(mock_update, mock_context)
    
    assert state == ConversationHandler.END
    # Validate context cleanup
    assert 'in_conversation' not in mock_context.user_data
    # Assert TaskService was called
    mock_process.assert_called_once()

@pytest.mark.asyncio
async def test_cancel_conversation(mock_update, mock_context):
    """Test user manual cancellation."""
    mock_context.user_data['in_conversation'] = "FACE_VIDEO"
    mock_context.user_data['face_video_data'] = {
        'face_image_path': '/tmp/face.png',
        'video_path': '/tmp/video.mp4'
    }
    
    state = await cancel_conversation(mock_update, mock_context)
    
    assert state == ConversationHandler.END
    assert 'in_conversation' not in mock_context.user_data

@pytest.mark.asyncio
async def test_unexpected_input(mock_update, mock_context):
    """Test user sending text while waiting for media."""
    state = await unexpected_input(mock_update, mock_context)
    assert state is None # Keeps FSM in current state
