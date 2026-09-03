from __future__ import annotations

import importlib.util
import hashlib
import json
import threading
import time
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


class _RangeClient:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.requests: list[tuple[int, int | None]] = []
        self.active = 0
        self.maximum_active = 0
        self.lock = threading.Lock()
        self.barrier = threading.Barrier(4)

    def get_object(
        self,
        bucket: str,
        key: str,
        *,
        offset: int = 0,
        length: int | None = None,
    ):
        assert bucket == "allbot-model-cache"
        assert key == "models/big.safetensors"
        with self.lock:
            self.requests.append((offset, length))
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        try:
            self.barrier.wait(timeout=1)
        except threading.BrokenBarrierError:
            pass
        end = None if length is None else offset + length
        response = _FakeResponse([self.payload[offset:end]])
        original_close = response.close

        def close() -> None:
            original_close()
            with self.lock:
                self.active -= 1

        response.close = close
        return response


def test_runpod_model_sync_downloads_one_file_with_parallel_ranges(
    monkeypatch, tmp_path
):
    sync_module = _load_module()
    payload = bytes(range(64))
    temp_target = tmp_path / "big.safetensors.partial"
    temp_target.write_bytes(payload[:8])
    client = _RangeClient(payload)
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_PARTS_PER_FILE", "4")
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_RETRY_SECONDS", "0")

    sync_module._download_object_with_parallel_ranges(
        client,
        bucket="allbot-model-cache",
        key="models/big.safetensors",
        temp_target=temp_target,
        expected_size=len(payload),
        relative_path="checkpoints/big.safetensors",
    )

    assert client.maximum_active == 4
    assert sorted(client.requests) == [
        (8, 14),
        (22, 14),
        (36, 14),
        (50, 14),
    ]
    assert temp_target.read_bytes() == payload
    assert not list(tmp_path.glob("*.range-*"))


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


def test_runpod_model_sync_merges_multiple_manifests_by_relative_path(tmp_path):
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


def test_runpod_model_sync_rejects_multi_manifest_path_conflict(tmp_path):
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


class _ManifestDownloadClient:
    def __init__(
        self,
        files: dict[str, bytes],
        *,
        fail_key: str = "",
        obsolete_files: list[dict[str, object]] | None = None,
    ) -> None:
        self.files = files
        self.fail_key = fail_key
        self.obsolete_files = obsolete_files or []

    def get_object(self, bucket: str, key: str, *, offset: int = 0):
        del bucket
        if key.endswith("manifest.json"):
            payload = json.dumps(
                {
                    "files": [
                        {
                            "relative_path": name,
                            "size_bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "key": name,
                        }
                        for name, content in self.files.items()
                    ],
                    "obsolete_files": self.obsolete_files,
                }
            ).encode()

            class ManifestResponse:
                def read(self): return payload
                def close(self): pass
                def release_conn(self): pass

            return ManifestResponse()
        if key == self.fail_key:
            return _FakeResponse([self.files[key][offset:offset + 1]], RuntimeError("boom"))
        return _FakeResponse([self.files[key][offset:]])


def test_runpod_model_sync_downloads_at_bounded_concurrency(monkeypatch, tmp_path):
    sync_module = _load_module()
    files = {f"models/{index}.bin": bytes([index]) * 8 for index in range(6)}
    client = _ManifestDownloadClient(files)
    monkeypatch.setattr(sync_module, "_client_from_env", lambda: client)
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_CONCURRENCY", "4")
    monkeypatch.setenv("RUNPOD_MODEL_MIN_FREE_BYTES", "0")

    active = 0
    maximum_active = 0
    lock = threading.Lock()
    barrier = threading.Barrier(4)
    original = sync_module._download_object_with_resume

    def tracked_download(*args, **kwargs):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        if maximum_active <= 4:
            try:
                barrier.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass
        time.sleep(0.01)
        try:
            return original(*args, **kwargs)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(sync_module, "_download_object_with_resume", tracked_download)

    result = sync_module.sync_models(
        bucket="models", prefix="profile", target_dir=tmp_path, verify_existing=True
    )

    assert maximum_active == 4
    assert result["downloaded"] == list(files)
    assert all((tmp_path / name).read_bytes() == content for name, content in files.items())


def test_runpod_model_sync_concurrency_one_remains_serial(monkeypatch, tmp_path):
    sync_module = _load_module()
    files = {"second.bin": b"second", "first.bin": b"first"}
    client = _ManifestDownloadClient(files)
    monkeypatch.setattr(sync_module, "_client_from_env", lambda: client)
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_CONCURRENCY", "1")
    monkeypatch.setenv("RUNPOD_MODEL_MIN_FREE_BYTES", "0")
    observed: list[str] = []
    original = sync_module._download_object_with_resume

    def tracked_download(*args, **kwargs):
        observed.append(kwargs["relative_path"])
        return original(*args, **kwargs)

    monkeypatch.setattr(sync_module, "_download_object_with_resume", tracked_download)
    result = sync_module.sync_models(
        bucket="models", prefix="profile", target_dir=tmp_path, verify_existing=True
    )

    assert observed == list(files)
    assert result["downloaded"] == list(files)


def test_runpod_model_sync_downloads_every_partial_before_verifying(
    monkeypatch, tmp_path
):
    sync_module = _load_module()
    files = {"one.bin": b"one", "two.bin": b"two", "three.bin": b"three"}
    client = _ManifestDownloadClient(files)
    monkeypatch.setattr(sync_module, "_client_from_env", lambda: client)
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_CONCURRENCY", "3")
    monkeypatch.setenv("RUNPOD_MODEL_MIN_FREE_BYTES", "0")
    original_sha256 = sync_module._sha256_file
    observed: list[str] = []

    def tracked_sha256(path):
        if not observed:
            assert all((tmp_path / f"{name}.partial").exists() for name in files)
        observed.append(path.name)
        return original_sha256(path)

    monkeypatch.setattr(sync_module, "_sha256_file", tracked_sha256)

    sync_module.sync_models(
        bucket="models", prefix="profile", target_dir=tmp_path, verify_existing=True
    )

    assert observed == [f"{name}.partial" for name in files]


def test_runpod_model_sync_skips_existing_and_override_before_scheduling(
    monkeypatch, tmp_path
):
    sync_module = _load_module()
    files = {"existing.bin": b"old", "override.bin": b"local", "new.bin": b"new"}
    (tmp_path / "existing.bin").write_bytes(files["existing.bin"])
    (tmp_path / "override.bin").write_bytes(files["override.bin"])
    client = _ManifestDownloadClient(files)
    monkeypatch.setattr(sync_module, "_client_from_env", lambda: client)
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_CONCURRENCY", "4")
    monkeypatch.setenv("RUNPOD_MODEL_MIN_FREE_BYTES", "0")
    monkeypatch.setenv(
        "RUNPOD_LAN_LOCAL_MODEL_OVERRIDES",
        json.dumps(
            [
                {
                    "relative_path": "override.bin",
                    "size_bytes": len(files["override.bin"]),
                    "sha256": hashlib.sha256(files["override.bin"]).hexdigest(),
                }
            ]
        ),
    )
    scheduled: list[str] = []
    original = sync_module._download_object_with_resume

    def tracked_download(*args, **kwargs):
        scheduled.append(kwargs["relative_path"])
        return original(*args, **kwargs)

    monkeypatch.setattr(sync_module, "_download_object_with_resume", tracked_download)

    result = sync_module.sync_models(
        bucket="models", prefix="profile", target_dir=tmp_path, verify_existing=True
    )

    assert scheduled == ["new.bin"]
    assert result["downloaded"] == ["new.bin"]
    assert result["skipped_existing"] == ["existing.bin", "override.bin"]


def test_runpod_model_sync_failure_keeps_partials_and_publishes_nothing(
    monkeypatch, tmp_path
):
    sync_module = _load_module()
    files = {"bad.bin": b"broken", "good.bin": b"healthy", "queued.bin": b"queued"}
    client = _ManifestDownloadClient(files, fail_key="bad.bin")
    monkeypatch.setattr(sync_module, "_client_from_env", lambda: client)
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_CONCURRENCY", "2")
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("RUNPOD_MODEL_DOWNLOAD_RETRY_SECONDS", "0")
    monkeypatch.setenv("RUNPOD_MODEL_MIN_FREE_BYTES", "0")

    with pytest.raises(RuntimeError, match="download failed"):
        sync_module.sync_models(
            bucket="models", prefix="profile", target_dir=tmp_path, verify_existing=True
        )

    assert (tmp_path / "bad.bin.partial").exists()
    assert not any((tmp_path / name).exists() for name in files)


def test_runpod_model_sync_removes_only_exact_obsolete_file_after_success(
    monkeypatch, tmp_path
):
    sync_module = _load_module()
    old_payload = b"beta3"
    old_path = tmp_path / "diffusion_models" / "old.safetensors"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(old_payload)
    client = _ManifestDownloadClient(
        {"diffusion_models/new.safetensors": b"beta4"},
        obsolete_files=[
            {
                "relative_path": "diffusion_models/old.safetensors",
                "size_bytes": len(old_payload),
                "sha256": hashlib.sha256(old_payload).hexdigest(),
            }
        ],
    )
    monkeypatch.setattr(sync_module, "_client_from_env", lambda: client)
    monkeypatch.setenv("RUNPOD_MODEL_MIN_FREE_BYTES", "0")

    result = sync_module.sync_models(
        bucket="models", prefix="profile", target_dir=tmp_path, verify_existing=True
    )

    assert not old_path.exists()
    assert result["removed_obsolete"] == ["diffusion_models/old.safetensors"]


def test_runpod_model_sync_keeps_obsolete_path_when_content_identity_differs(
    monkeypatch, tmp_path
):
    sync_module = _load_module()
    old_path = tmp_path / "diffusion_models" / "old.safetensors"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(b"unexpected-content")
    client = _ManifestDownloadClient(
        {"diffusion_models/new.safetensors": b"beta4"},
        obsolete_files=[
            {
                "relative_path": "diffusion_models/old.safetensors",
                "size_bytes": 5,
                "sha256": hashlib.sha256(b"beta3").hexdigest(),
            }
        ],
    )
    monkeypatch.setattr(sync_module, "_client_from_env", lambda: client)
    monkeypatch.setenv("RUNPOD_MODEL_MIN_FREE_BYTES", "0")

    with pytest.raises(RuntimeError, match="obsolete model identity mismatch"):
        sync_module.sync_models(
            bucket="models", prefix="profile", target_dir=tmp_path, verify_existing=True
        )

    assert old_path.exists()


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
