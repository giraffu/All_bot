import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ComfyClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def check_connection(self) -> bool:
        try:
            response = await self.client.get("/system_stats")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"ComfyUI connection failed: {e}")
            return False

    async def upload_image(self, file_content: bytes, filename: str, subfolder: str = "") -> Dict[str, Any]:
        """
        Upload an image to ComfyUI input directory.
        """
        # The multipart format expected by ComfyUI
        files = {"image": (filename, file_content, "image/png")}
        data = {"overwrite": "true"}
        if subfolder:
            data["subfolder"] = subfolder
        
        # Use multipart explicitly
        response = await self.client.post("/upload/image", files=files, data=data)
        if response.status_code != 200:
            logger.error(f"ComfyUI upload error: {response.text}")
        response.raise_for_status()
        return response.json()

    async def queue_prompt(self, prompt: Dict[str, Any], client_id: str) -> str:
        """
        Submit a workflow prompt to ComfyUI.
        """
        payload = {"prompt": prompt, "client_id": client_id}
        response = await self.client.post("/prompt", json=payload)
        if response.status_code != 200:
            logger.error(f"ComfyUI prompt error: {response.text}")
        response.raise_for_status()
        data = response.json()
        return data.get("prompt_id")

    async def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """
        Get execution history for a specific prompt_id.
        """
        response = await self.client.get(f"/history/{prompt_id}")
        if response.status_code == 200:
            return response.json()
        return {}

    async def get_view(self, filename: str, subfolder: str = "", type: str = "output") -> bytes:
        """
        Get the raw image/video data from ComfyUI output directory.
        """
        params = {"filename": filename, "subfolder": subfolder, "type": type}
        response = await self.client.get("/view", params=params)
        response.raise_for_status()
        return response.content

    async def close(self):
        await self.client.aclose()
