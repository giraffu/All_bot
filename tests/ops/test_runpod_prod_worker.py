from __future__ import annotations

from pathlib import Path

from ops.gpu_pool_controller.cli import build_parser
from ops.gpu_pool_controller.providers.runpod import (
    RUNPOD_PROD_AGENT_ID,
    RUNPOD_PROD_GPU_TYPE_IDS,
    RUNPOD_PROD_SUPPORTED_TASK_TYPES,
    RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
    RunPodProvider,
    RunPodSettings,
)
from ops.gpu_pool_controller.runpod_prod_worker import (
    RunPodProdWorkerOptions,
    RunPodProdWorkerRunner,
    load_env_file_for_prod_worker,
)


class FakeRunPodProvider:
    def __init__(self, settings: RunPodSettings | None = None) -> None:
        self.settings = settings or RunPodSettings(api_key="rp_test_key")
        self.create_calls = 0
        self.delete_calls = 0
        self.list_calls = 0

    def validate_key(self):
        return {"ok": True}

    def list_pods(self, *, managed_only=True, desired_status=None):
        self.list_calls += 1
        return {"ok": True, "count": 0, "pods": []}

    def reconcile_managed_pods(self, pods=None):
        return {"ok": True, "managed_count": 0, "orphans": [], "by_task_type": {}}

    def render_create_pod_request(self, *, task_type, environment, redact=True):
        settings = RunPodSettings(
            api_key="rp_test_key",
            image_name_img2img_lora=RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
            minio_endpoint="https://r2.example.test",
        )
        return RunPodProvider(settings).render_create_pod_request(
            task_type=task_type,
            environment=environment,
            redact=redact,
        )

    def create_pod(self, *, task_type, environment, execute):
        self.create_calls += 1
        return {"ok": True, "pod": {"id": "pod-prod-1", "name": "allbot-runpod-prod-img2img-manual-01"}}

    def delete_pod(self, *, pod_id, task_type, execute):
        self.delete_calls += 1
        return {"ok": True}

    def pod_readiness(self, *, pod_id):
        return {"ok": True, "readiness": {"infrastructure_ready": True}}


class FakeHttpProdWorkerRunner(RunPodProdWorkerRunner):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.http_calls = []
        self.control_calls = []

    def _http_json(self, method, url, **kwargs):
        self.http_calls.append({"method": method, "url": url, "kwargs": kwargs})
        if "/api/agent/task/control/" in url:
            self.control_calls.append({"method": method, "url": url, "kwargs": kwargs})
            body = kwargs.get("json_body") or {}
            return {
                "agent_id": RUNPOD_PROD_AGENT_ID,
                "state": body.get("state", "disabled"),
                "reason": body.get("reason", ""),
            }
        if url.endswith("/system/workers"):
            return {"workers": []}
        if url.endswith("/health"):
            return {"ok": True}
        return {"ok": True}


def _settings(**overrides) -> RunPodSettings:
    values = {
        "api_key": "rp_test_key",
        "dry_run": True,
        "autoscaler_enabled": False,
        "max_pods_total": 1,
        "max_pods_per_type": 1,
        "image_name_img2img_lora": RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE,
        "minio_endpoint": "https://r2.example.test",
    }
    values.update(overrides)
    return RunPodSettings(**values)


def test_prod_worker_render_dry_run_uses_verified_image_and_prod_defaults():
    provider = FakeRunPodProvider(_settings())
    options = RunPodProdWorkerOptions(action="render", quiet=True)

    payload = RunPodProdWorkerRunner(provider, options).run()

    assert payload["ok"] is True
    assert payload["render"]["imageName"] == RUNPOD_PUBLIC_IMG2IMG_LORA_IMAGE
    assert payload["render"]["central_api_url"] == "https://worker-central.aivison.it.com"
    assert payload["render"]["agent_id"] == RUNPOD_PROD_AGENT_ID
    assert payload["render"]["gpu_type_ids"] == list(RUNPOD_PROD_GPU_TYPE_IDS)
    assert payload["render"]["supported_task_types"] == ",".join(
        RUNPOD_PROD_SUPPORTED_TASK_TYPES
    )
    assert payload["render"]["buckets"]["result"] == "user-data-prod"
    assert payload["render"]["custom_nodes_enabled"] == "false"
    assert provider.create_calls == 0
    assert provider.delete_calls == 0


def test_prod_worker_up_dry_run_preflights_without_mutation():
    provider = FakeRunPodProvider(_settings())
    options = RunPodProdWorkerOptions(action="up", execute=False, quiet=True)
    runner = FakeHttpProdWorkerRunner(provider, options, sleep_func=lambda _seconds: None)

    payload = runner.run()

    assert payload["ok"] is True
    assert "set Central control" in payload["would_execute"][0]
    assert provider.create_calls == 0
    assert runner.control_calls == []


def test_prod_worker_up_execute_requires_gates_before_control_or_create():
    provider = FakeRunPodProvider(_settings(dry_run=True, autoscaler_enabled=False))
    options = RunPodProdWorkerOptions(
        action="up",
        execute=True,
        agent_token="agent_token",
        quiet=True,
    )
    runner = FakeHttpProdWorkerRunner(provider, options, sleep_func=lambda _seconds: None)

    payload = runner.run()

    assert payload["ok"] is False
    assert "RUNPOD_DRY_RUN=false" in payload["error"]
    assert "RUNPOD_AUTOSCALER_ENABLED=true" in payload["error"]
    assert provider.create_calls == 0
    assert runner.control_calls == []


def test_prod_worker_env_loader_protects_explicit_runpod_gates(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env.cloud.prod"
    env_file.write_text(
        "RUNPOD_DRY_RUN=true\n"
        "AGENT_SECRET_TOKEN=prod_agent_token\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RUNPOD_DRY_RUN", "false")
    monkeypatch.setenv("AGENT_SECRET_TOKEN", "old_agent_token")

    info = load_env_file_for_prod_worker(
        env_file,
        override=True,
        protect_existing_prefixes=("RUNPOD_",),
    )

    assert info["loaded"] is True
    assert info["count"] == 1
    assert info["protected_existing_prefixes"] == ["RUNPOD_"]
    assert __import__("os").environ["RUNPOD_DRY_RUN"] == "false"
    assert __import__("os").environ["AGENT_SECRET_TOKEN"] == "prod_agent_token"


def test_cli_parses_runpod_prod_worker_up_command():
    args = build_parser().parse_args(
        [
            "runpod",
            "prod-worker",
            "up",
            "--runpod-env-file",
            ".env.cloud.test",
            "--prod-env-file",
            ".env.cloud.prod",
            "--execute",
            "--quiet",
        ]
    )

    assert args.runpod_command == "prod-worker"
    assert args.prod_worker_command == "up"
    assert args.runpod_env_file == Path(".env.cloud.test")
    assert args.prod_env_file == Path(".env.cloud.prod")
    assert args.execute is True
    assert args.quiet is True
