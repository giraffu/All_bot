import importlib.util
import base64
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "validate_private_qqcc_bot_env.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_private_qqcc_bot_env",
        MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_disabled_rollout_does_not_require_activation_secrets():
    module = _load_module()

    module.validate(
        {"PRIVATE_QQCC_BOT_ENABLED": "false"},
        allow_disabled=True,
    )
    module.validate({}, allow_disabled=True)


def test_strict_activation_rejects_disabled_rollout():
    module = _load_module()

    with pytest.raises(module.ContractError, match="must be true"):
        module.validate({"PRIVATE_QQCC_BOT_ENABLED": "false"})


def test_enabled_rollout_still_requires_the_complete_security_contract():
    module = _load_module()

    with pytest.raises(module.ContractError, match="missing required"):
        module.validate(
            {"PRIVATE_QQCC_BOT_ENABLED": "true"},
            allow_disabled=True,
        )


def test_cli_can_validate_a_production_env_without_persisting_bot_type(tmp_path):
    def encode(value):
        return base64.urlsafe_b64encode(value * 32).decode()

    env_file = tmp_path / ".env.cloud.prod"
    env_file.write_text(
        "\n".join(
            (
                "PRIVATE_QQCC_BOT_ENABLED=true",
                f"PRIVATE_QQCC_BOT_TOKEN_KEYRING='{{\"1\":\"{encode(b'a')}\"}}'",
                "PRIVATE_QQCC_BOT_TOKEN_ACTIVE_KEY_VERSION=1",
                f"PRIVATE_QQCC_BOT_TOKEN_FINGERPRINT_KEY={encode(b'b')}",
                f"PRIVATE_QQCC_BOT_OWNER_JWT_SECRET={encode(b'c')}",
                "PRIVATE_QQCC_BOT_FORBIDDEN_BOT_IDS=1,2,3",
                "PRIVATE_QQCC_BOT_TELEGRAM_API_BASE_URL=https://api.telegram.org",
                "PRIVATE_QQCC_BOT_TELEGRAM_FILE_BASE_URL=https://api.telegram.org/file/bot",
                "PRIVATE_QQCC_BOT_WEBHOOK_BASE_URL=https://api.example.test/api/private-bots/webhook",
                "PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL=https://owner.example.test/",
                "PRIVATE_QQCC_BOT_OWNER_HOST=owner.example.test",
                "QQCC_CONFIG_ADMIN_HOST=admin.example.test",
                "R2_ENDPOINT=https://r2.example.test",
                "R2_ACCESS_KEY=test-access",
                "R2_SECRET_KEY=test-secret",
                "R2_BUCKET=test-bucket",
                "QQCC_BOT_TOKEN=123456:test-token",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python",
            str(MODULE_PATH),
            "--env-file",
            str(env_file),
            "--bot-type",
            "PROD",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
