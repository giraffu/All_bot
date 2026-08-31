import pytest

from src.domain_config.task_type_registry import TASK_TYPE_REGISTRY
from src.services.task_pricing_config_service import (
    TASK_PRICING_CONFIG_KEY,
    TaskPricingConfigValidationError,
    build_task_pricing_catalog,
    normalize_task_pricing_config,
    resolve_configured_task_cost,
    validate_task_pricing_config,
)


def test_task_pricing_catalog_covers_every_registered_task_type():
    catalog = build_task_pricing_catalog({"overrides": {"txt2img": 9}})

    assert {item["task_type"] for item in catalog} == set(TASK_TYPE_REGISTRY)
    txt2img = next(item for item in catalog if item["task_type"] == "txt2img")
    assert txt2img["default_cost"] == 2
    assert txt2img["override_cost"] == 9
    assert txt2img["effective_cost"] == 9
    assert txt2img["pricing_mode"] == "fixed"

    dynamic = next(item for item in catalog if item["task_type"] == "image")
    assert dynamic["default_cost"] is None
    assert dynamic["effective_cost"] is None
    assert dynamic["pricing_mode"] == "dynamic"


def test_task_pricing_config_normalizes_missing_tasks_without_copying_defaults():
    assert TASK_PRICING_CONFIG_KEY == "task_pricing_config:v1"
    assert normalize_task_pricing_config(None) == {"overrides": {}}
    assert normalize_task_pricing_config(
        {"overrides": {"txt2img": 0, "face_swap": 4, "unknown": 8}}
    ) == {"overrides": {"txt2img": 0, "face_swap": 4}}


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"overrides": {"unknown": 1}}, "unknown task type"),
        ({"overrides": {"txt2img": -1}}, "non-negative integer"),
        ({"overrides": {"txt2img": True}}, "non-negative integer"),
        ({"overrides": {"txt2img": 100001}}, "at most 100000"),
    ],
)
def test_task_pricing_config_rejects_unknown_or_invalid_overrides(payload, message):
    with pytest.raises(TaskPricingConfigValidationError, match=message):
        validate_task_pricing_config(payload)


def test_configured_price_only_overrides_web_and_main_bot_clients():
    config = {"overrides": {"txt2img": 0}}

    assert resolve_configured_task_cost(
        config,
        task_type="txt2img",
        client_type="web",
        default_cost=2,
    ) == 0
    assert resolve_configured_task_cost(
        config,
        task_type="txt2img",
        client_type="bot",
        default_cost=2,
    ) == 0
    assert resolve_configured_task_cost(
        config,
        task_type="txt2img",
        client_type="bot:qqcc-private:7",
        default_cost=2,
    ) == 2
