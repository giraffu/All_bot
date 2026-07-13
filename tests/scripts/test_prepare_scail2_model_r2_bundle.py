from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path("scripts/prepare_scail2_model_r2_bundle.py")


class FakeClientError(Exception):
    def __init__(self, code: str = "404", message: str = "not found") -> None:
        super().__init__(message)
        self.response = {"Error": {"Code": code, "Message": message}}


class FakeR2Client:
    def __init__(self, *, heads: dict[str, dict] | None = None) -> None:
        self.heads = dict(heads or {})
        self.puts: list[dict] = []
        self.gets: list[dict] = []

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        assert Bucket == "allbot-model-cache"
        if Key not in self.heads:
            raise FakeClientError()
        return self.heads[Key]

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        assert Bucket == "allbot-model-cache"
        self.gets.append({"Bucket": Bucket, "Key": Key})
        raise FakeClientError()

    def put_object(self, **kwargs) -> None:
        assert kwargs["Bucket"] == "allbot-model-cache"
        self.puts.append(kwargs)


def _load_module():
    spec = importlib.util.spec_from_file_location("prepare_scail2_model_r2_bundle", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_scail2_model_file_list_has_required_lora_path():
    module = _load_module()

    relative_paths = [item.relative_path for item in module.SCAIL2_MODEL_FILES]

    assert len(relative_paths) == 6
    assert (
        "loras/Wan2.1/"
        "Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors"
        in relative_paths
    )
    assert module.manifest_key_for(module.DEFAULT_PREFIX) == (
        "scail2/2026-06-17-test/manifest.json"
    )


def test_prepare_scail2_bundle_dry_run_skips_existing_object_with_sha():
    module = _load_module()
    existing_key = module.object_key_for(
        module.DEFAULT_PREFIX,
        module.SCAIL2_MODEL_FILES[0].relative_path,
    )
    client = FakeR2Client(
        heads={
            existing_key: {
                "ContentLength": 123,
                "Metadata": {"sha256": "a" * 64},
            }
        }
    )

    payload = module.prepare_scail2_model_r2_bundle(
        client=client,
        bucket="allbot-model-cache",
        prefix=module.DEFAULT_PREFIX,
        execute=False,
        probe_func=lambda _url: {"content_size": 456},
    )

    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["file_count"] == 6
    assert payload["actions"][0]["action"] == "skip_existing"
    assert payload["manifest"]["files"][0]["sha256"] == "a" * 64
    assert client.puts == []


def test_prepare_scail2_bundle_execute_writes_manifest(monkeypatch):
    module = _load_module()
    client = FakeR2Client()

    def fake_transfer(**kwargs):
        relative_path = kwargs["relative_path"]
        return {
            "ok": True,
            "action": "uploaded",
            "size_bytes": len(relative_path),
            "sha256": (relative_path.encode("utf-8").hex() + "0" * 64)[:64],
            "part_count": 1,
        }

    monkeypatch.setattr(module, "transfer_model_url_to_r2", fake_transfer)

    payload = module.prepare_scail2_model_r2_bundle(
        client=client,
        bucket="allbot-model-cache",
        prefix=module.DEFAULT_PREFIX,
        execute=True,
        probe_func=lambda _url: {"content_size": 456},
    )

    assert payload["ok"] is True
    assert payload["dry_run"] is False
    assert [item["action"] for item in payload["actions"]] == ["uploaded"] * 6
    assert len(client.puts) == 1
    assert client.puts[0]["Key"] == "scail2/2026-06-17-test/manifest.json"
    manifest = json.loads(client.puts[0]["Body"].decode("utf-8"))
    assert manifest["bundle"] == "scail2"
    assert manifest["profile"] == "scail2"
    assert manifest["file_count"] == 6
    assert all(item["sha256"] for item in manifest["files"])
