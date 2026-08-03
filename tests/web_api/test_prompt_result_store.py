from unittest.mock import AsyncMock

import pytest

from src.web_api.services import prompt_result_store
from src.web_api.services.prompt_result_store import validate_prompt_result


def _expected():
    return {
        "profile_ref": "ltx_eros_v14_i2v@1",
        "template_ref": "ltx_scene_script_cinematic@1",
        "allowed_output_fields": ["positive_prompt"],
    }


def _meta(**optimizer_overrides):
    optimizer = {
        "schema_version": "allbot.prompt_optimizer.v1",
        "profile_ref": "ltx_eros_v14_i2v@1",
        "template_ref": "ltx_scene_script_cinematic@1",
        "primary_field": "positive_prompt",
        "optimized_fields": {"positive_prompt": "final prompt"},
        "warnings": [],
    }
    optimizer.update(optimizer_overrides)
    return {"prompt_optimizer": optimizer}


def test_validate_prompt_result_accepts_profile_whitelisted_output():
    payload = validate_prompt_result(
        result_kind="text",
        result_text="final prompt",
        result_meta=_meta(),
        expected_optimizer_metadata=_expected(),
    )
    assert payload["result_text"] == "final prompt"
    assert payload["result_meta"]["prompt_optimizer"]["warnings"] == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"result_kind": "media"}, "result_kind"),
        ({"result_text": ""}, "empty"),
        ({"result_text": "x" * 2001}, "too long"),
        (
            {"result_meta": _meta(profile_ref="ltx_eros_v14_flf2v@1")},
            "profile_ref mismatch",
        ),
        (
            {
                "result_meta": _meta(
                    optimized_fields={"negative_prompt": "final prompt"},
                    primary_field="negative_prompt",
                )
            },
            "violate",
        ),
    ],
)
def test_validate_prompt_result_fails_closed(kwargs, message):
    params = {
        "result_kind": "text",
        "result_text": "final prompt",
        "result_meta": _meta(),
        "expected_optimizer_metadata": _expected(),
    }
    params.update(kwargs)
    with pytest.raises(ValueError, match=message):
        validate_prompt_result(**params)


@pytest.mark.asyncio
async def test_failure_result_retains_only_unvalidated_partial_and_refund_state(monkeypatch):
    setter = AsyncMock()
    monkeypatch.setattr(prompt_result_store.redis_client, "set_prompt_result", setter)
    await prompt_result_store.store_prompt_failure_result(
        task_id="registry-1",
        user_id=7,
        partial_result_text="partial prompt",
        refund_status="refunded",
    )
    payload = setter.await_args.args[1]
    assert payload["status"] == "failed"
    assert payload["partial_result_text"] == "partial prompt"
    assert payload["partial_unvalidated"] is True
    assert payload["refund_status"] == "refunded"
    assert "result_text" not in payload
