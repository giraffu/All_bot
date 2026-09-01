import json
import os
import subprocess
from pathlib import Path


def test_compose_accepts_an_explicit_public_origin_allowlist() -> None:
    platform_root = Path(__file__).resolve().parents[2]
    expected = '["http://localhost:8095","https://wuhanzhenjing.cn","https://www.wuhanzhenjing.cn"]'
    env = os.environ.copy()
    env["CLARITY_ALLOWED_ORIGINS"] = expected

    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            ".env.example",
            "--profile",
            "test-worker",
            "config",
            "--format",
            "json",
        ],
        cwd=platform_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    config = json.loads(result.stdout)
    assert config["services"]["backend"]["environment"]["CLARITY_ALLOWED_ORIGINS"] == expected
    bridge = config["services"]["test-worker-bridge"]
    assert bridge["profiles"] == ["test-worker"]
    assert bridge["environment"]["CLARITY_TEST_WORKER_BRIDGE_ENABLED"] == "true"
    assert bridge["environment"]["CLARITY_TEST_INPUT_S3_BUCKET"] == "user-data-test"
