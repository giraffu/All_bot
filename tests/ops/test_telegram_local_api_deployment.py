import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _yaml(path: str) -> dict:
    value = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _json(path: str) -> dict:
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_local_bot_api_and_file_gateway_are_internal_profiled_services():
    services = _yaml("deploy/docker-compose-cloud-base.yml")["services"]
    api = services["telegram-local-api"]
    files = services["telegram-local-files"]

    assert api["image"].startswith("${ALLBOT_TELEGRAM_LOCAL_API_IMAGE:")
    assert files["image"].startswith("${ALLBOT_TELEGRAM_LOCAL_FILES_IMAGE:")
    assert api["profiles"] == ["telegram-local-api"]
    assert files["profiles"] == ["telegram-local-api"]
    assert "ports" not in api
    assert "ports" not in files
    assert api["environment"] == {
        "TELEGRAM_LOCAL": "1",
        "TELEGRAM_STAT": "1",
    }
    assert api["env_file"] == [
        {
            "path": (
                "${ALLBOT_SERVICE_ENV_ROOT:?ALLBOT_SERVICE_ENV_ROOT is required}/"
                "telegram-local-api.env"
            ),
            "required": False,
            "format": "raw",
        }
    ]
    assert not any("TELEGRAM_API_ID" in str(value) for value in api.values())
    assert not any("TELEGRAM_API_HASH" in str(value) for value in api.values())
    assert "127.0.0.1:8082" in " ".join(api["healthcheck"]["test"])

    api_mount = next(
        value for value in api["volumes"] if "/var/lib/telegram-bot-api" in value
    )
    file_mount = next(
        value for value in files["volumes"] if "/var/lib/telegram-bot-api" in value
    )
    assert api_mount == (
        "${ALLBOT_STATE_ROOT:?ALLBOT_STATE_ROOT is required}/telegram-local-api:"
        "/var/lib/telegram-bot-api"
    )
    assert file_mount == (
        "${ALLBOT_STATE_ROOT:?ALLBOT_STATE_ROOT is required}/telegram-local-api:"
        "/usr/share/nginx/html/var/lib/telegram-bot-api:ro"
    )


def test_test_overlay_caps_local_bot_api_resources():
    services = _yaml("deploy/docker-compose-cloud-test.overlay.yml")["services"]

    assert services["telegram-local-api"]["mem_limit"] == "384m"
    assert services["telegram-local-api"]["cpus"] == 0.5
    assert services["telegram-local-files"]["mem_limit"] == "64m"
    assert services["telegram-local-files"]["cpus"] == 0.25


def test_local_bot_api_images_are_exactly_pinned_external_modules():
    modules = _json("deploy/module-catalog.json")["modules"]
    api = modules["telegram-local-api"]
    files = modules["telegram-local-files"]

    assert api == {
        "kind": "external-image",
        "adapter": "compose-image",
        "ref": (
            "docker.io/aiogram/telegram-bot-api@sha256:"
            "e0c2d269555a39d37b77ed6dd6fa5e4153b8d8399c6de9f249808682cdd942a5"
        ),
        "service": "telegram-local-api",
        "profile": "telegram-local-api",
        "image_env": "ALLBOT_TELEGRAM_LOCAL_API_IMAGE",
        "environments": ["test", "prod"],
    }
    assert files == {
        "kind": "external-image",
        "adapter": "compose-image",
        "ref": (
            "docker.io/library/nginx@sha256:"
            "65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"
        ),
        "service": "telegram-local-files",
        "profile": "telegram-local-api",
        "image_env": "ALLBOT_TELEGRAM_LOCAL_FILES_IMAGE",
        "environments": ["test", "prod"],
    }


def test_local_bot_api_is_disabled_by_default_and_schema_typed():
    defaults = (ROOT / "deploy/env.defaults").read_text(encoding="utf-8")
    schema = _json("deploy/env.schema.yml")

    assert "TELEGRAM_LOCAL_API_ENABLED=false" in defaults.splitlines()
    assert "TELEGRAM_LOCAL_API_ENABLED" in schema["types"]["boolean"]
