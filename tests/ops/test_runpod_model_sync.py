from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path("remote_workers/scripts/runpod_sync_models_from_r2.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("runpod_sync_models_from_r2", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, chunks: list[bytes], error: Exception | None = None) -> None:
        self._chunks = chunks
        self._error = error

    def stream(self, *, amt: int):
        del amt
        yield from self._chunks
        if self._error is not None:
            raise self._error

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class _ResumeClient:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offsets: list[int] = []

    def get_object(self, bucket: str, key: str, *, offset: int = 0):
        assert bucket == "allbot-model-cache"
        assert key == "models/big.safetensors"
        self.offsets.append(offset)
        if len(self.offsets) == 1:
            return _FakeResponse(
                [self.payload[offset : offset + 2]],
                RuntimeError("connection interrupted"),
            )
        return _FakeResponse([self.payload[offset:]])


def test_runpod_model_sync_resumes_partial_download(monkeypatch, tmp_path):
    sync_module = _load_module()
    payload = b"abcdefghi"
    temp_target = tmp_path / "big.safetensors.partial"
    temp_target.write_bytes(payload[:3])
    client = _ResumeClient(payload)
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_RETRY_SECONDS", "0")

    sync_module._download_object_with_resume(
        client,
        bucket="allbot-model-cache",
        key="models/big.safetensors",
        temp_target=temp_target,
        expected_size=len(payload),
        relative_path="checkpoints/big.safetensors",
    )

    assert client.offsets == [3, 5]
    assert temp_target.read_bytes() == payload
