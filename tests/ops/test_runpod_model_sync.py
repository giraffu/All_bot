from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path("workers/runpod_runtime/scripts/runpod_sync_models_from_r2.py")
LOCAL_SYNC_MODULE_PATH = Path("workers/runpod_runtime/scripts/runpod_sync_local_models.py")


def _load_module(path: Path = MODULE_PATH):
    spec = importlib.util.spec_from_file_location(path.stem, path)
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


def test_runpod_model_sync_rejects_invalid_lan_override(monkeypatch, tmp_path):
    sync_module = _load_module()

    class Client:
        def get_object(self, *_args):
            class Response:
                def read(self):
                    return b'{"files":[{"relative_path":"diffusion_models/v11.safetensors","size_bytes":2,"sha256":"00"}]}'
                def close(self): pass
                def release_conn(self): pass
            return Response()

    monkeypatch.setattr(sync_module, "_client_from_env", lambda: Client())
    monkeypatch.setenv("RUNPOD_LAN_LOCAL_MODEL_OVERRIDES", '[{"relative_path":"diffusion_models/v11.safetensors","size_bytes":2,"sha256":"00"}]')
    with pytest.raises(RuntimeError, match="LAN local model override is missing or invalid"):
        sync_module.sync_models(bucket="models", prefix="wan", target_dir=tmp_path, verify_existing=True)


def test_runpod_model_sync_merges_multiple_manifests_by_relative_path(monkeypatch):
    sync_module = _load_module()
    manifests = {
        "img/manifest.json": {
            "files": [
                {
                    "relative_path": "checkpoints/shared.safetensors",
                    "size_bytes": 2,
                    "sha256": "aa",
                    "key": "models/shared",
                }
            ]
        },
        "video/manifest.json": {
            "files": [
                {
                    "relative_path": "checkpoints/shared.safetensors",
                    "size_bytes": 2,
                    "sha256": "aa",
                    "key": "models/shared",
                },
                {
                    "relative_path": "diffusion_models/video.safetensors",
                    "size_bytes": 3,
                    "sha256": "bb",
                    "key": "models/video",
                },
            ]
        },
    }

    merged = sync_module.merge_model_manifests(manifests)

    assert [item["relative_path"] for item in merged] == [
        "checkpoints/shared.safetensors",
        "diffusion_models/video.safetensors",
    ]


def test_runpod_model_sync_rejects_multi_manifest_path_conflict():
    sync_module = _load_module()

    with pytest.raises(RuntimeError, match="conflicting model manifests"):
        sync_module.merge_model_manifests(
            {
                "one/manifest.json": {
                    "files": [
                        {
                            "relative_path": "checkpoints/model.safetensors",
                            "size_bytes": 2,
                            "sha256": "aa",
                        }
                    ]
                },
                "two/manifest.json": {
                    "files": [
                        {
                            "relative_path": "checkpoints/model.safetensors",
                            "size_bytes": 3,
                            "sha256": "bb",
                        }
                    ]
                },
            }
        )


def test_runpod_model_sync_rejects_insufficient_disk_space(
    monkeypatch, tmp_path
):
    sync_module = _load_module()
    monkeypatch.setenv("RUNPOD_MODEL_MIN_FREE_BYTES", "10")
    monkeypatch.setattr(
        sync_module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=12),
    )

    with pytest.raises(RuntimeError, match="insufficient disk space"):
        sync_module._ensure_disk_capacity(
            target_dir=tmp_path,
            required_bytes=3,
        )


def test_lan_local_model_sync_hashes_existing_large_file_in_chunks(monkeypatch, tmp_path):
    sync_module = _load_module(LOCAL_SYNC_MODULE_PATH)
    payload = b"abcdef"
    target = tmp_path / "v11.safetensors"
    target.write_bytes(payload)
    observed_reads: list[int] = []
    original_open = Path.open

    class _TrackedFile:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self._wrapped.close()

        def read(self, size=-1):
            observed_reads.append(size)
            return self._wrapped.read(size)

    def tracked_open(path, *args, **kwargs):
        return _TrackedFile(original_open(path, *args, **kwargs))

    monkeypatch.setattr(Path, "open", tracked_open)
    assert sync_module.sha256_file(target) == __import__("hashlib").sha256(
        payload
    ).hexdigest()
    assert observed_reads == [sync_module.CHUNK_SIZE, sync_module.CHUNK_SIZE]
