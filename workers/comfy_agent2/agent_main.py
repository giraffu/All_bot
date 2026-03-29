import asyncio
import json
import logging
import os
import sys
import httpx
import websockets
from minio import Minio
from dotenv import load_dotenv
from typing import Dict, Any, Optional

from comfy_client import ComfyClient
from workflow_patcher import WorkflowPatcher

# Load environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("agent_main")

# Configuration
AGENT_ID = os.getenv("AGENT_ID", "worker_local_01")
SUPPORTED_TASK_TYPES = os.getenv("SUPPORTED_TASK_TYPES", "") # e.g. "img2img,face_swap"
MASTER_API_URL = os.getenv("MASTER_API_URL", "http://127.0.0.1:8000")
AGENT_SECRET_TOKEN = os.getenv("AGENT_SECRET_TOKEN", "")

COMFY_API_URL = os.getenv("COMFY_API_URL", "http://127.0.0.1:8188")
COMFY_WS_URL = os.getenv("COMFY_WS_URL", "ws://127.0.0.1:8188/ws")
COMFY_INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/home/ubantu/comfyui/input")
COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/home/ubantu/comfyui/output")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "play.min.io:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "your_key")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_secret")
MINIO_INPUT_BUCKET = os.getenv("MINIO_INPUT_BUCKET", "comfyui-input")
MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET", "comfyui-output")

class ComfyAgent:
    def __init__(self):
        self.comfy_client = ComfyClient(base_url=COMFY_API_URL)
        self.patcher = WorkflowPatcher(workflows_dir=os.path.join(os.path.dirname(__file__), "workflows"))
        self.master_client = httpx.AsyncClient(
            base_url=MASTER_API_URL, 
            headers={"Authorization": f"Bearer {AGENT_SECRET_TOKEN}"},
            timeout=30.0
        )
        
        # Init MinIO
        try:
            self.minio_client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=False  # Set to True if using HTTPS
            )
            logger.info("MinIO client initialized")
        except Exception as e:
            logger.error(f"Failed to init MinIO: {e}")
            self.minio_client = None

        self.current_task_id: Optional[str] = None
        self.current_prompt_id: Optional[str] = None
        self.task_completed_event = asyncio.Event()
        self.task_result: Optional[str] = None
        self.task_error: Optional[str] = None

    async def report_status(self, task_id: str, status: str, progress: float = 0.0, error: str = ""):
        try:
            await self.master_client.post("/api/agent/task/status", json={
                "task_id": task_id,
                "agent_id": AGENT_ID,
                "status": status,
                "progress": progress,
                "error": error
            })
        except Exception as e:
            logger.error(f"Failed to report status for task {task_id}: {e}")

    async def report_complete(self, task_id: str, result_path: str):
        try:
            await self.master_client.post("/api/agent/task/complete", json={
                "task_id": task_id,
                "agent_id": AGENT_ID,
                "result": result_path
            })
        except Exception as e:
            logger.error(f"Failed to report completion for task {task_id}: {e}")

    async def ws_listener_loop(self):
        client_id = f"agent_{AGENT_ID}"
        uri = f"{COMFY_WS_URL}?clientId={client_id}"
        
        while True:
            try:
                async with websockets.connect(uri, max_size=None) as websocket:
                    logger.info(f"Connected to ComfyUI WebSocket at {uri}")
                    while True:
                        message = await websocket.recv()
                        if isinstance(message, bytes):
                            continue
                            
                        data = json.loads(message)
                        msg_type = data.get("type")
                        data_content = data.get("data", {})
                        
                        prompt_id = data_content.get("prompt_id")
                        
                        if not prompt_id or prompt_id != self.current_prompt_id:
                            continue

                        if msg_type == "execution_start":
                            logger.info(f"Execution started for prompt {prompt_id}")
                            if self.current_task_id:
                                await self.report_status(self.current_task_id, "running")
                                
                        elif msg_type == "progress":
                            value = data_content.get("value", 0)
                            max_val = data_content.get("max", 1)
                            if max_val > 0 and self.current_task_id:
                                progress = value / max_val
                                await self.report_status(self.current_task_id, "running", progress=progress)
                                
                        elif msg_type == "executed":
                            logger.info(f"Execution completed for prompt {prompt_id}")
                            output = data_content.get("output", {})
                            images = output.get("images", [])
                            gifs = output.get("gifs", [])
                            videos = output.get("videos", [])
                            
                            result_path = ""
                            if images:
                                img = images[0]
                                result_path = f"{img.get('subfolder', '')}/{img.get('filename')}".lstrip('/')
                            elif gifs:
                                gif = gifs[0]
                                result_path = f"{gif.get('subfolder', '')}/{gif.get('filename')}".lstrip('/')
                            elif videos:
                                video = videos[0]
                                result_path = f"{video.get('subfolder', '')}/{video.get('filename')}".lstrip('/')
                                
                            self.task_result = result_path
                            self.task_completed_event.set()
                            
                        elif msg_type == "execution_error":
                            error_msg = str(data_content.get("exception_message", "Unknown error"))
                            logger.error(f"Execution error for prompt {prompt_id}: {error_msg}")
                            self.task_error = error_msg
                            self.task_completed_event.set()
                            
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                await asyncio.sleep(5)

    def download_input_from_minio(self, object_name: str, local_path: str):
        if not self.minio_client:
            raise Exception("MinIO client not initialized")
        logger.info(f"Downloading {object_name} from MinIO to {local_path}")
        self.minio_client.fget_object(MINIO_INPUT_BUCKET, object_name, local_path)

    def upload_result_to_minio(self, local_path: str, object_name: str):
        if not self.minio_client:
            raise Exception("MinIO client not initialized")
        
        content_type = "image/png"
        if object_name.endswith(".mp4"):
            content_type = "video/mp4"
        elif object_name.endswith(".gif"):
            content_type = "image/gif"
        elif object_name.endswith(".jpg") or object_name.endswith(".jpeg"):
            content_type = "image/jpeg"
            
        logger.info(f"Uploading {local_path} to MinIO bucket {MINIO_RESULT_BUCKET} as {object_name}")
        self.minio_client.fput_object(MINIO_RESULT_BUCKET, object_name, local_path, content_type=content_type)

    async def process_task(self, task: Dict[str, Any]):
        task_id = task.get("task_id")
        task_type = task.get("type")
        params_str = task.get("params", "{}")
        
        if isinstance(params_str, str):
            params = json.loads(params_str)
        else:
            params = params_str
            
        logger.info(f"Processing task {task_id} of type {task_type}")
        self.current_task_id = task_id
        self.task_completed_event.clear()
        self.task_result = None
        self.task_error = None

        try:
            # 1. Download input image if provided and needed
            if "image" in params and params["image"]:
                image_filename = params["image"]
                local_image_path = os.path.join(COMFY_INPUT_DIR, image_filename)
                
                # Assuming the Master node saves the image in MinIO with the same filename
                try:
                    await asyncio.to_thread(self.download_input_from_minio, image_filename, local_image_path)
                    logger.info(f"Downloaded input image to {local_image_path}")
                    
                    # Ensure the image is uploaded to ComfyUI if we are using the remote API
                    # Note: Since the agent container mounts the ComfyUI input directory directly, 
                    # downloading the file to COMFY_INPUT_DIR *is* making it available to ComfyUI.
                    # Upload API might be failing due to file permission/locking issues since the file is already there.
                    # We will only try API upload if we think it's strictly necessary (it shouldn't be if paths match).
                    params["image"] = image_filename
                except Exception as e:
                    logger.error(f"Failed to process input image {image_filename}: {e}")
                    params["image"] = image_filename

            # Also check for other potential image inputs (like face_image, body_image)
            for key in ["face_image", "body_image"]:
                if key in params and params[key]:
                    img_filename = params[key]
                    local_img_path = os.path.join(COMFY_INPUT_DIR, img_filename)
                    try:
                        await asyncio.to_thread(self.download_input_from_minio, img_filename, local_img_path)
                        logger.info(f"Downloaded {key} to {local_img_path}")
                        params[key] = img_filename
                    except Exception as e:
                        logger.error(f"Failed to process {key} {img_filename}: {e}")

            # 2. Load and patch workflow
            workflow = self.patcher.load_workflow(task_type)
            if not workflow:
                raise ValueError(f"Workflow for {task_type} not found")

            patched_workflow = self.patcher.patch_workflow(task_type, workflow, params)

            # 3. Submit to ComfyUI
            client_id = f"agent_{AGENT_ID}"
            self.current_prompt_id = await self.comfy_client.queue_prompt(patched_workflow, client_id)
            logger.info(f"Submitted task {task_id} to ComfyUI, prompt_id: {self.current_prompt_id}")
            
            await self.report_status(task_id, "running")

            # 4. Wait for completion (via WS listener)
            # Timeout after 10 minutes to avoid hanging forever
            try:
                await asyncio.wait_for(self.task_completed_event.wait(), timeout=600.0)
            except asyncio.TimeoutError:
                raise Exception("Task execution timed out")

            if self.task_error:
                raise Exception(self.task_error)

            if not self.task_result:
                raise Exception("Task completed but no result path found")

            # 5. Fetch result from ComfyUI API and Upload to MinIO
            # We must fetch the file via the ComfyUI /view API since Agent might not have direct local disk access
            # or the file might be in temp/output directories on the ComfyUI server.
            try:
                # Assuming task_result format is like "subfolder/filename.png" or "filename.png"
                parts = self.task_result.split('/')
                if len(parts) > 1:
                    subfolder = '/'.join(parts[:-1])
                    filename = parts[-1]
                else:
                    subfolder = ""
                    filename = self.task_result
                    
                # We need to determine the type based on the path. Often it's 'output', but if it contains 'temp' 
                # (like ComfyUI_temp_xxx), it might be in the 'temp' type.
                # However, get_view defaults to 'output' or 'temp' based on how ComfyUI saves it.
                view_type = "temp" if "temp" in filename.lower() else "output"
                
                logger.info(f"Fetching result {filename} from ComfyUI API (subfolder: '{subfolder}', type: '{view_type}')")
                
                # We use the existing comfy_client.get_view method
                file_data = await self.comfy_client.get_view(filename, subfolder, type=view_type)
                
                # Upload the fetched bytes directly to MinIO
                import io
                content_type = "image/png"
                if filename.endswith(".mp4"):
                    content_type = "video/mp4"
                elif filename.endswith(".gif"):
                    content_type = "image/gif"
                elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
                    content_type = "image/jpeg"
                    
                logger.info(f"Uploading result {self.task_result} to MinIO bucket {MINIO_RESULT_BUCKET}")
                await asyncio.to_thread(
                    self.minio_client.put_object,
                    MINIO_RESULT_BUCKET,
                    self.task_result,
                    io.BytesIO(file_data),
                    len(file_data),
                    content_type=content_type
                )
                
            except Exception as e:
                logger.error(f"Failed to fetch from ComfyUI or upload to MinIO: {e}")
                raise Exception(f"Result processing failed: {e}")

            # 6. Report completion
            await self.report_complete(task_id, self.task_result)
            logger.info(f"Task {task_id} completed successfully")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            await self.report_status(task_id, "failed", error=str(e))
        finally:
            self.current_task_id = None
            self.current_prompt_id = None

    async def poll_loop(self):
        logger.info(f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks (types: {SUPPORTED_TASK_TYPES or 'all'})...")
        while True:
            try:
                # Poll for tasks with optional type filtering
                params = {}
                if SUPPORTED_TASK_TYPES:
                    params["types"] = SUPPORTED_TASK_TYPES
                
                response = await self.master_client.get("/api/agent/task/pop", params=params)
                if response.status_code == 200:
                    data = response.json()
                    task = data.get("task")
                    if task:
                        await self.process_task(task)
                        continue  # Immediately poll again after finishing
                elif response.status_code != 404: # 404 means no tasks, which is fine
                    logger.warning(f"Unexpected response from master: {response.status_code}")
                    
            except httpx.RequestError as e:
                logger.error(f"Connection to master failed: {e}")
            except Exception as e:
                logger.error(f"Polling error: {e}")
                
            # Wait before next poll
            await asyncio.sleep(2)

    async def start(self):
        # Ensure directories exist
        os.makedirs(COMFY_INPUT_DIR, exist_ok=True)
        os.makedirs(COMFY_OUTPUT_DIR, exist_ok=True)
        
        # Start WS listener and polling loops
        await asyncio.gather(
            self.ws_listener_loop(),
            self.poll_loop()
        )

if __name__ == "__main__":
    agent = ComfyAgent()
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        logger.info("Agent shutting down...")
