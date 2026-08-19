import logging
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)


class ComfyClient:
    def __init__(
        self,
        base_url: str,
        *,
        upload_timeout_seconds: float = 300.0,
    ):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        self.upload_timeout_seconds = upload_timeout_seconds

    async def check_connection(self) -> bool:
        try:
            response = await self.client.get("/system_stats")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"ComfyUI connection failed: {e}")
            return False

    async def upload_image(
        self, file_content: bytes, filename: str, subfolder: str = ""
    ) -> Dict[str, Any]:
        """
        Upload an image or video to ComfyUI input directory.
        """
        content_type = "image/png"
        if filename.lower().endswith(".mp4"):
            content_type = "video/mp4"
        elif filename.lower().endswith(".gif"):
            content_type = "image/gif"
        elif filename.lower().endswith(".webp"):
            content_type = "image/webp"
        elif filename.lower().endswith((".jpg", ".jpeg")):
            content_type = "image/jpeg"

        # The multipart format expected by ComfyUI
        files = {"image": (filename, file_content, content_type)}
        data = {"overwrite": "true"}
        if subfolder:
            data["subfolder"] = subfolder

        # Use multipart explicitly
        response = await self.client.post(
            "/upload/image",
            files=files,
            data=data,
            timeout=self.upload_timeout_seconds,
        )
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
            detail = _truncate_response_text(response.text)
            logger.error(f"ComfyUI prompt error: {detail}")
            raise RuntimeError(
                f"ComfyUI /prompt returned {response.status_code}: {detail}"
            )
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

    async def interrupt(self) -> bool:
        """
        Ask ComfyUI to interrupt the currently executing prompt.
        """
        try:
            response = await self.client.post("/interrupt", json={})
            response.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"ComfyUI interrupt failed: {e}")
            return False

    async def free_memory(self) -> None:
        """Unload resident models and release ComfyUI's allocator cache."""
        response = await self.client.post(
            "/free",
            json={"unload_models": True, "free_memory": True},
        )
        response.raise_for_status()

    async def get_view(
        self, filename: str, subfolder: str = "", type: str = "output"
    ) -> bytes:
        """
        Get the raw image/video data from ComfyUI output directory.
        Includes a simple retry mechanism for file system I/O delays.
        """
        import asyncio

        params = {"filename": filename, "subfolder": subfolder, "type": type}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.client.get("/view", params=params)
                response.raise_for_status()
                return response.content
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Failed to fetch {filename} (attempt {attempt + 1}/{max_retries}), retrying in 2 seconds... Error: {e}"
                    )
                    await asyncio.sleep(2)
                else:
                    logger.error(
                        f"Failed to fetch {filename} after {max_retries} attempts."
                    )
                    raise e
        raise Exception(f"Failed to fetch {filename}")

    async def close(self):
        await self.client.aclose()


def _truncate_response_text(text: str, *, limit: int = 4000) -> str:
    normalized = (text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit] + "...<truncated>"
