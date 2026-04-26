import asyncio
import json
import logging
import os
import sys
from asgi_correlation_id import correlation_id
import httpx
import websockets # type: ignore
from minio import Minio # type: ignore
from dotenv import load_dotenv
from typing import Dict, Any, Optional

from comfy_client import ComfyClient
from workflow_patcher import WorkflowPatcher

# Load environment variables
load_dotenv()

# Unset proxies to prevent internal requests from being routed through system VPN/proxies
for proxy_var in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
    os.environ.pop(proxy_var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        trace_id = correlation_id.get()
        record.correlation_id = f"TraceID: {trace_id}" if trace_id else "TraceID: None"
        return True

# Configuration
AGENT_ID = os.getenv("AGENT_ID", "worker_local_01")
SUPPORTED_TASK_TYPES = os.getenv("SUPPORTED_TASK_TYPES", "img2img,face_swap")
MASTER_API_URL = os.getenv("MASTER_API_URL", "http://127.0.0.1:8000")
AGENT_SECRET_TOKEN = os.getenv("AGENT_SECRET_TOKEN", "")

COMFY_API_URL = os.getenv("COMFY_API_URL", "http://127.0.0.1:8188")
COMFY_WS_URL = os.getenv("COMFY_WS_URL", "ws://127.0.0.1:8188/ws")
COMFY_INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/tmp/input")
COMFY_OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/tmp/output")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "play.min.io:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "your_key")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "your_secret")
MINIO_INPUT_BUCKET = os.getenv("MINIO_INPUT_BUCKET", "comfyui-input")
MINIO_RESULT_BUCKET = os.getenv("MINIO_RESULT_BUCKET", "comfyui-output")

log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s'
formatter = logging.Formatter(log_format)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
handler.addFilter(CorrelationIdFilter())

# Also log to file if the directory exists
handlers = [handler]
os.makedirs("/app/logs", exist_ok=True)
file_handler = logging.FileHandler(f"/app/logs/agent_{AGENT_ID}.log")
file_handler.setFormatter(formatter)
file_handler.addFilter(CorrelationIdFilter())
handlers.append(file_handler)

logging.basicConfig(
    level=logging.INFO,
    handlers=handlers
)
logger = logging.getLogger("agent_main")

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
        self.running = False

    async def report_heartbeat(self):
        try:
            status = "running" if self.current_task_id else "idle"
            await self.master_client.post("/api/agent/task/heartbeat", json={
                "agent_id": AGENT_ID,
                "types": SUPPORTED_TASK_TYPES,
                "status": status
            })
            if self.current_task_id:
                # Add task heartbeat specifically
                await self.master_client.post("/api/agent/task/task_heartbeat", json={
                    "task_id": self.current_task_id
                })
        except Exception as e:
            logger.debug(f"Failed to report heartbeat: {e}")

    async def heartbeat_loop(self):
        logger.info(f"Agent {AGENT_ID} started heartbeat loop...")
        while getattr(self, 'running', True):
            await self.report_heartbeat()
            await asyncio.sleep(15)  # Send heartbeat every 15 seconds

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
        
        while getattr(self, 'running', True):
            try:
                async with websockets.connect(uri, max_size=None, ping_interval=20, ping_timeout=20) as websocket:
                    logger.info(f"Connected to ComfyUI WebSocket at {uri}")
                    while True:
                        try:
                            # Use timeout to periodically check connection state
                            message = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                        except asyncio.TimeoutError:
                            if websocket.closed:
                                logger.error("WebSocket closed unexpectedly")
                                break
                            try:
                                await websocket.ping()
                            except Exception as e:
                                logger.error(f"WebSocket ping failed: {e}")
                                break
                            continue
                            
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
                                
                        elif msg_type == "executing":
                            node = data_content.get("node")
                            if node is None:
                                logger.info(f"Execution fully completed for prompt {prompt_id}")
                                self.task_completed_event.set()
                                
                        elif msg_type == "execution_success":
                            logger.info(f"Execution success received for prompt {prompt_id}")
                            self.task_completed_event.set()
                                
                        elif msg_type == "executed":
                            logger.info(f"Node executed for prompt {prompt_id}")
                            output = data_content.get("output", {})
                            images = output.get("images", [])
                            gifs = output.get("gifs", [])
                            videos = output.get("videos", [])
                            
                            result_path = ""
                            if images:
                                img = images[0]
                                result_path = f"{self.current_task_id}_{img.get('subfolder', '')}_{img.get('filename')}".replace('/', '_').lstrip('_')
                            elif gifs:
                                gif = gifs[0]
                                result_path = f"{self.current_task_id}_{gif.get('subfolder', '')}_{gif.get('filename')}".replace('/', '_').lstrip('_')
                            elif videos:
                                video = videos[0]
                                result_path = f"{self.current_task_id}_{video.get('subfolder', '')}_{video.get('filename')}".replace('/', '_').lstrip('_')
                                
                            if result_path:
                                self.task_result = result_path
                                # We now wait for executing node=None to set the completion event
                            
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
            
        bucket_name = MINIO_INPUT_BUCKET
        real_object_name = object_name
        
        if object_name.startswith("template:"):
            bucket_name = "bot-template"
            real_object_name = object_name.replace("template:", "")
            
        logger.info(f"Downloading {real_object_name} from MinIO bucket {bucket_name} to {local_path}")
        self.minio_client.fget_object(bucket_name, real_object_name, local_path)

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

    async def check_task_cancelled(self, task_id: str) -> bool:
        try:
            response = await self.master_client.get(f"/api/agent/task/check/{task_id}")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "cancelled":
                    return True
        except Exception as e:
            logger.debug(f"Failed to check task status: {e}")
        return False

    async def process_task(self, task: Dict[str, Any]):
        trace_id = task.get("trace_id", "")
        if trace_id:
            correlation_id.set(trace_id)
            
        task_id = str(task.get("task_id", ""))
        if not task_id:
            logger.error("Received task without task_id")
            return
            
        task_type = str(task.get("type", ""))
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
        
        downloaded_input_paths = []

        try:
            if await self.check_task_cancelled(task_id):
                logger.info(f"Task {task_id} was cancelled before processing.")
                return

            # Helper for downloading and uploading single image
            async def process_single_image(img_filename: str, param_key: str):
                local_safe_filename = img_filename.replace("/", "_").replace("template:", "")
                local_img_path = os.path.join(COMFY_INPUT_DIR, local_safe_filename)
                try:
                    await asyncio.to_thread(self.download_input_from_minio, img_filename, local_img_path)
                    logger.info(f"Downloaded {param_key} to {local_img_path}")
                    try:
                        with open(local_img_path, "rb") as f:
                            img_data = f.read()
                        await self.comfy_client.upload_image(img_data, local_safe_filename)
                        logger.info(f"Uploaded {local_safe_filename} to ComfyUI via API")
                    except Exception as upload_err:
                        logger.warning(f"Failed to upload {local_safe_filename} to ComfyUI via API: {upload_err}")
                    params[param_key] = local_safe_filename
                    if local_img_path not in downloaded_input_paths:
                        downloaded_input_paths.append(local_img_path)
                except Exception as e:
                    logger.error(f"Failed to process {param_key} {img_filename}: {e}")

            # 1. Handle multi-image concurrent download if `images` list is provided
            if "images" in params and isinstance(params["images"], list) and len(params["images"]) > 0:
                images_list = params["images"]
                tasks = []
                keys = ["image", "image2", "image3"]
                for i, img_filename in enumerate(images_list[:3]):
                    tasks.append(process_single_image(img_filename, keys[i]))
                if tasks:
                    await asyncio.gather(*tasks)
            else:
                # Fallback to legacy single image keys
                legacy_tasks = []
                if "image" in params and params["image"]:
                    legacy_tasks.append(process_single_image(params["image"], "image"))
                if "image2" in params and params["image2"]:
                    legacy_tasks.append(process_single_image(params["image2"], "image2"))
                if legacy_tasks:
                    await asyncio.gather(*legacy_tasks)

            # Also check for other potential image inputs (like face_image, body_image, video)
            other_tasks = []
            for key in ["face_image", "body_image", "video"]:
                if key in params and params[key]:
                    other_tasks.append(process_single_image(params[key], key))
            if other_tasks:
                await asyncio.gather(*other_tasks)

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
                logger.warning(f"Task execution timed out for {task_id}, will attempt to fetch result from history.")

            if self.task_error:
                raise Exception(self.task_error)

            if not self.task_result:
                logger.info(f"Task result not set via WS, checking history for prompt {self.current_prompt_id}")
                try:
                    history = await self.comfy_client.get_history(self.current_prompt_id)
                    if history and self.current_prompt_id in history:
                        outputs = history[self.current_prompt_id].get("outputs", {})
                        for node_id, node_output in outputs.items():
                            images = node_output.get("images", [])
                            gifs = node_output.get("gifs", [])
                            videos = node_output.get("videos", [])
                            
                            if images:
                                img = images[0]
                                self.task_result = f"{self.current_task_id}_{img.get('subfolder', '')}_{img.get('filename')}".replace('/', '_').lstrip('_')
                                break
                            elif gifs:
                                gif = gifs[0]
                                self.task_result = f"{self.current_task_id}_{gif.get('subfolder', '')}_{gif.get('filename')}".replace('/', '_').lstrip('_')
                                break
                            elif videos:
                                video = videos[0]
                                self.task_result = f"{self.current_task_id}_{video.get('subfolder', '')}_{video.get('filename')}".replace('/', '_').lstrip('_')
                                break
                except Exception as e:
                    logger.warning(f"Failed to fetch history: {e}")

            if not self.task_result:
                raise Exception("Task completed but no result path found")

            if await self.check_task_cancelled(task_id):
                logger.info(f"Task {task_id} was cancelled during execution, skipping upload.")
                return

            # 5. Fetch result from ComfyUI API and Upload to MinIO
            # We must fetch the file via the ComfyUI /view API since Agent might not have direct local disk access
            # or the file might be in temp/output directories on the ComfyUI server.
            try:
                # 现在的 task_result 格式如: task_id_subfolder_filename.png
                # 我们需要提取出原始的 filename 来从 ComfyUI API 获取文件
                # 由于 task_result 已经被替换过下划线，这里不能简单地 split('/')
                # 我们假设原始文件名在最后一个 '_' 之后（这是一种简化的假设，更严谨的做法是在上报前保留原始文件名）
                # 这里我们修改逻辑：在上报前，先提取 ComfyUI 原始返回的 filename 和 subfolder
                # 由于前面我们将 result 加上了 task_id 前缀，我们需要回溯原始数据
                
                # 为了不改变 ComfyUI 的请求逻辑，我们需要从 ComfyUI 的历史记录中重新提取原始 filename 和 subfolder
                history = await self.comfy_client.get_history(self.current_prompt_id)
                original_filename = ""
                original_subfolder = ""
                if history and self.current_prompt_id in history:
                    outputs = history[self.current_prompt_id].get("outputs", {})
                    for node_id, node_output in outputs.items():
                        images = node_output.get("images", [])
                        gifs = node_output.get("gifs", [])
                        videos = node_output.get("videos", [])
                        
                        if images:
                            original_filename = images[0].get('filename', '')
                            original_subfolder = images[0].get('subfolder', '')
                            break
                        elif gifs:
                            original_filename = gifs[0].get('filename', '')
                            original_subfolder = gifs[0].get('subfolder', '')
                            break
                        elif videos:
                            original_filename = videos[0].get('filename', '')
                            original_subfolder = videos[0].get('subfolder', '')
                            break
                            
                if not original_filename:
                    raise Exception("Could not retrieve original filename from ComfyUI history")

                view_type = "temp" if "temp" in original_filename.lower() else "output"
                
                logger.info(f"Fetching result {original_filename} from ComfyUI API (subfolder: '{original_subfolder}', type: '{view_type}')")
                
                file_data = await self.comfy_client.get_view(original_filename, original_subfolder, type=view_type)
                
                # Upload the fetched bytes directly to MinIO using the safe prefixed task_result name
                import io
                content_type = "image/png"
                if original_filename.endswith(".mp4"):
                    content_type = "video/mp4"
                elif original_filename.endswith(".gif"):
                    content_type = "image/gif"
                elif original_filename.endswith(".jpg") or original_filename.endswith(".jpeg"):
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
            for path in downloaded_input_paths:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        logger.info(f"Cleaned up input file: {path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up input file {path}: {e}")

    async def poll_loop(self):
        logger.info(f"Agent {AGENT_ID} started polling {MASTER_API_URL} for tasks (types: {SUPPORTED_TASK_TYPES or 'all'})...")
        while getattr(self, 'running', True):
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
        
        # Start WS listener, polling loops, and heartbeat
        self.running = True
        self.tasks = [
            asyncio.create_task(self.ws_listener_loop()),
            asyncio.create_task(self.poll_loop()),
            asyncio.create_task(self.heartbeat_loop())
        ]
        await asyncio.gather(*self.tasks)

    async def shutdown(self):
        logger.info("Initiating graceful shutdown...")
        self.running = False
        
        # If there is a task currently running, report it as failed/interrupted back to master
        if self.current_task_id:
            logger.info(f"Returning task {self.current_task_id} to master due to shutdown")
            try:
                await self.report_status(
                    self.current_task_id, 
                    "failed", 
                    error="Agent was shut down while processing the task. Task should be retried."
                )
            except Exception as e:
                logger.error(f"Failed to report task failure during shutdown: {e}")
                
        # Cancel all running background loops
        for task in self.tasks:
            task.cancel()
            
        # Close HTTP clients
        await self.master_client.aclose()
        await self.comfy_client.close()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    agent = ComfyAgent()
    
    # Setup graceful shutdown signals
    import signal
    import sys
    loop = asyncio.get_event_loop()
    
    if sys.platform != 'win32':
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(agent.shutdown())
            )
        
    try:
        loop.run_until_complete(agent.start())
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        # 捕获 Ctrl+C，触发优雅退出逻辑，防止 Master 端任务卡死
        loop.run_until_complete(agent.shutdown())
    finally:
        loop.close()
