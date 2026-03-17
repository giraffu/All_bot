import os
import logging
from src.logger import UserLogger
from src.services.storage import storage
import uuid

# Mock logging to avoid file output issues
logging.basicConfig(level=logging.INFO)

def test_logger_write():
    user_id = 999999999
    username = "test_user"
    logger = UserLogger(user_id, username)
    
    # Create dummy image data
    dummy_data = b"fake_image_data"
    task_id = str(uuid.uuid4())
    
    print(f"Testing save_output_image with task_id: {task_id}")
    try:
        # This should upload to MinIO based on current code
        key = logger.save_output_image(dummy_data, task_id, extension="png")
        print(f"Result key: {key}")
        
        # Check if local file exists
        local_path = f"user_data/{user_id}/output_images/{task_id}.png"
        if os.path.exists(local_path):
            print(f"❌ ERROR: Local file FOUND at {local_path}!")
        else:
            print(f"✅ SUCCESS: Local file NOT found at {local_path}.")
            
        # Check if MinIO has it (if possible)
        # We can't easily check MinIO without client access, but return key implies success
        
    except Exception as e:
        print(f"Exception during test: {e}")

if __name__ == "__main__":
    # Ensure directory exists just in case code tries to write to it and fails if missing
    os.makedirs(f"user_data/999999999/output_images", exist_ok=True)
    test_logger_write()
    # Cleanup
    import shutil
    if os.path.exists(f"user_data/999999999"):
        shutil.rmtree(f"user_data/999999999")
