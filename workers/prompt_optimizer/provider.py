from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx


class ModelNotReadyError(RuntimeError):
    pass


class ModelResponseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LMStudioReadiness:
    ready: bool
    reason: str


class LMStudioChatProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 180.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds), trust_env=False
        )

    async def readiness(self) -> LMStudioReadiness:
        try:
            response = await self.client.get(f"{self.base_url}/api/v1/models")
            response.raise_for_status()
            models = response.json().get("models") or response.json().get("data") or []
        except Exception as exc:
            return LMStudioReadiness(False, f"lmstudio_unreachable:{type(exc).__name__}")
        for model in models:
            instances = model.get("loaded_instances") or [model]
            for instance in instances:
                instance_config = instance.get("config") or {}
                identifiers = {
                    str(model.get("key") or ""),
                    str(model.get("id") or ""),
                    str(instance.get("id") or ""),
                    str(instance.get("model") or ""),
                }
                if self.model not in identifiers:
                    continue
                vision = bool(
                    instance.get("vision", (model.get("capabilities") or {}).get("vision", False))
                )
                context = int(
                    instance.get("context_length")
                    or instance.get("context_window")
                    or instance_config.get("context_length")
                    or model.get("context_length")
                    or 0
                )
                parallel = int(
                    instance.get("parallel")
                    or instance.get("max_parallel_requests")
                    or instance_config.get("parallel")
                    or model.get("parallel")
                    or 0
                )
                if not vision:
                    return LMStudioReadiness(False, "model_vision_disabled")
                if context < 16384:
                    return LMStudioReadiness(False, "model_context_below_16k")
                if parallel < 4:
                    return LMStudioReadiness(False, "model_parallel_below_4")
                return LMStudioReadiness(True, "ready")
        return LMStudioReadiness(False, "model_not_loaded")

    async def optimize(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_data_urls: list[str],
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        content.extend(
            {"type": "image_url", "image_url": {"url": data_url}}
            for data_url in image_data_urls
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.35,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "prompt_optimization",
                    "strict": True,
                    "schema": json_schema,
                },
            },
        }
        for attempt in range(2):
            try:
                response = await self.client.post(
                    f"{self.base_url}/v1/chat/completions", json=payload
                )
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                if response.status_code >= 400:
                    raise ModelResponseError(f"lmstudio_http_{response.status_code}")
                content_value = response.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content_value)
                if not isinstance(parsed, dict):
                    raise ModelResponseError("lmstudio_output_not_object")
                return parsed
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 0:
                    await asyncio.sleep(0)
                    continue
                raise
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise ModelResponseError("lmstudio_invalid_json") from exc
        raise ModelResponseError("lmstudio_request_failed")
