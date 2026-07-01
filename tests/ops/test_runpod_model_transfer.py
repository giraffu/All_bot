from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


MODULE_PATH = Path("scripts/create_runpod_model_transfer_pod.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("create_runpod_model_transfer_pod", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**overrides):
    values = {
        "batch_file": None,
        "source_url": "https://example.test/model-a.safetensors",
        "bucket": "allbot-model-cache",
        "key": "wan22_aio_video/2026-06-12-test/models/unet/model-a.safetensors",
        "relative_path": "unet/model-a.safetensors",
        "sha256": "a" * 64,
        "size_bytes": 123,
        "name": "allbot-model-transfer-unit",
        "cloud_type": "SECURE",
        "gpu_type_ids": ["NVIDIA GeForce RTX 4090"],
        "container_disk_gb": 20,
        "image": "python:3.11-slim",
        "keepalive_on_complete": False,
        "civitai_token_secret_ref": "{{ RUNPOD_SECRET_allbot_civitai_api_token }}",
        "pornmaster_flux2_edit": False,
        "confirm_model_transfer": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_batch_transfer_render_redacts_all_source_urls(tmp_path, monkeypatch):
    module = _load_module()
    batch = tmp_path / "transfers.json"
    batch.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "source_url": "https://example.test/private-a",
                        "key": "wan22_aio_video/2026-06-12-test/models/a.safetensors",
                        "relative_path": "a.safetensors",
                        "sha256": "a" * 64,
                        "size_bytes": 1,
                    },
                    {
                        "sourceUrl": "https://example.test/private-b",
                        "objectKey": "wan22_aio_video/2026-06-12-test/models/b.safetensors",
                        "relativePath": "b.safetensors",
                        "sha256": "b" * 64,
                        "sizeBytes": 2,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNPOD_MODEL_ENDPOINT", "https://r2.example.test")

    items = module._load_transfer_items(_args(batch_file=batch))
    body = module._create_body(_args(batch_file=batch), items)
    redacted = module._redacted_body(body)
    rendered = json.dumps(redacted, ensure_ascii=False)

    assert len(items) == 2
    assert body["env"]["RUNPOD_MODEL_TRANSFER_COUNT"] == "2"
    assert body["env"]["RUNPOD_MODEL_ENDPOINT"] == "https://r2.example.test"
    assert "https://example.test/private-a" not in rendered
    assert "https://example.test/private-b" not in rendered
    assert rendered.count("<source-url>") >= 2
    assert redacted["env"]["RUNPOD_MODEL_ACCESS_KEY"] == "<redacted>"
    assert redacted["env"]["RUNPOD_MODEL_SECRET_KEY"] == "<redacted>"
    assert body["env"]["RUNPOD_MODEL_TRANSFER_EXIT_ON_COMPLETE"] == "true"
    assert "tail -f /dev/null" in body["dockerStartCmd"][2]
    assert "exit 0" in body["dockerStartCmd"][2]


def test_pornmaster_flux2_edit_batch_uses_cloud_model_prefix_and_token_secret(monkeypatch):
    module = _load_module()
    monkeypatch.setenv("RUNPOD_MODEL_ENDPOINT", "https://r2.example.test")

    args = _args(pornmaster_flux2_edit=True)
    items = module._load_transfer_items(args)
    body = module._create_body(args, items)
    redacted = module._redacted_body(body)
    rendered = json.dumps(redacted, ensure_ascii=False)

    assert len(items) == 3
    assert body["env"]["RUNPOD_MODEL_TRANSFER_COUNT"] == "3"
    assert body["env"]["CIVITAI_API_TOKEN"] == "{{ RUNPOD_SECRET_allbot_civitai_api_token }}"
    assert items[0]["source_token_env"] == "CIVITAI_API_TOKEN"
    assert items[0]["source_token_query_param"] == "token"
    assert all(
        item["key"].startswith("pornmaster_flux2_edit/2026-06-27/models/")
        for item in items
    )
    assert "https://civitai.com/api/download/models/2973304" not in rendered
    assert "huggingface.co" not in rendered
    assert redacted["env"]["CIVITAI_API_TOKEN"] == "<redacted>"
    assert rendered.count("<source-url>") >= 3


def test_single_transfer_mode_stays_compatible():
    module = _load_module()

    items = module._load_transfer_items(_args())

    assert items == [
        {
            "source_url": "https://example.test/model-a.safetensors",
            "key": "wan22_aio_video/2026-06-12-test/models/unet/model-a.safetensors",
            "relative_path": "unet/model-a.safetensors",
            "sha256": "a" * 64,
            "size_bytes": 123,
        }
    ]


def test_transfer_guard_allows_second_pod_when_explicitly_capped_at_two():
    module = _load_module()

    reasons = module._transfer_guard_reasons(
        dry_run=False,
        autoscaler_enabled=True,
        max_pods_total=2,
        existing_count=1,
    )

    assert reasons == []


def test_transfer_guard_blocks_when_transfer_pod_limit_reached():
    module = _load_module()

    reasons = module._transfer_guard_reasons(
        dry_run=False,
        autoscaler_enabled=True,
        max_pods_total=1,
        existing_count=1,
    )

    assert "model transfer pod limit reached" in reasons


def test_transfer_guard_requires_explicit_confirm_for_execute():
    module = _load_module()

    reasons = module._transfer_guard_reasons(
        dry_run=False,
        autoscaler_enabled=True,
        max_pods_total=1,
        existing_count=0,
        confirmed=False,
    )

    assert "--confirm-model-transfer is required" in reasons


def test_transfer_dry_run_renders_without_runpod_api_key(tmp_path, monkeypatch):
    batch = tmp_path / "transfers.json"
    batch.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.test/private-a",
                    "key": "wan22_aio_video/2026-06-12-test/models/a.safetensors",
                    "relative_path": "a.safetensors",
                    "sha256": "a" * 64,
                    "size_bytes": 1,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.delenv("RUNPOD_DRY_RUN", raising=False)
    monkeypatch.delenv("RUNPOD_AUTOSCALER_ENABLED", raising=False)

    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--env-file",
            str(tmp_path / "missing.env"),
            "--batch-file",
            str(batch),
            "--name",
            "allbot-model-transfer-unit",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["dry_run"] is True
    assert payload["pod_lookup_skipped"] is True
    assert payload["transfer_count"] == 1
    assert payload["request"]["env"]["RUNPOD_MODEL_TRANSFER_COUNT"] == "1"
    assert "missing_RUNPOD_API_KEY" not in result.stdout


def test_transfer_execute_requires_confirm_before_runpod_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "dummy-key")
    monkeypatch.setenv("RUNPOD_DRY_RUN", "false")
    monkeypatch.setenv("RUNPOD_AUTOSCALER_ENABLED", "true")

    env = os.environ.copy()
    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--env-file",
            str(tmp_path / "missing.env"),
            "--pornmaster-flux2-edit",
            "--execute",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert "--confirm-model-transfer is required" in payload["guard"]["reasons"]
    assert payload["pod_lookup_skipped"] is True
    assert "runpod_http" not in result.stdout
