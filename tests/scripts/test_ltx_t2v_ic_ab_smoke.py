import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ltx_t2v_ic_ab_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ltx_t2v_ic_ab_smoke", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ab_cases_keep_baseline_and_sulphur_as_the_only_model_difference():
    module = _load_module()

    cases = module.build_cases(
        repo_root=ROOT,
        character_sheet_name="private-character.png",
        character_description="an adult woman with short black hair",
        prompt="private adult test prompt",
        seed=20260802,
        durations=(5, 10),
    )

    assert [case["label"] for case in cases] == [
        "ingredients_5s",
        "sulphur_ingredients_5s",
        "ingredients_10s",
        "sulphur_ingredients_10s",
    ]
    for case in cases:
        workflow = case["workflow"]
        assert workflow["704"]["inputs"]["seed"] == 20260802
        assert workflow["273"]["inputs"]["amount"] == case["duration"] * 24 + 1
        assert workflow["28"]["inputs"]["text"].startswith(
            "### Reference Sheet Description\n"
        )
        assert workflow["28"]["inputs"]["text"].endswith(
            "### Target Description\nprivate adult test prompt"
        )
        expected_source = ["258", 0] if case["sulphur"] else ["127", 0]
        assert workflow["195"]["inputs"]["model"] == expected_source
        assert ("258" in workflow) is case["sulphur"]


def test_evidence_metadata_does_not_persist_private_inputs():
    module = _load_module()
    case = module.build_cases(
        repo_root=ROOT,
        character_sheet_name="secret-character-object-key.png",
        character_description="private identity description",
        prompt="private adult test prompt",
        seed=20260802,
        durations=(5,),
    )[0]

    evidence = module.case_evidence_metadata(case)
    serialized = json.dumps(evidence, ensure_ascii=False)

    assert evidence["seed"] == 20260802
    assert evidence["duration_seconds"] == 5
    assert len(evidence["workflow_sha256"]) == 64
    assert "private adult test prompt" not in serialized
    assert "private identity description" not in serialized
    assert "secret-character-object-key" not in serialized


def test_validate_media_contract_requires_audio_resolution_fps_and_duration():
    module = _load_module()
    valid = {
        "format": {"duration": "10.03"},
        "streams": [
            {
                "codec_type": "video",
                "avg_frame_rate": "24/1",
                "width": 768,
                "height": 448,
            },
            {"codec_type": "audio"},
        ],
    }

    assert module.validate_media_contract(valid, expected_duration=10) == {
        "duration_seconds": 10.03,
        "fps": 24.0,
        "width": 768,
        "height": 448,
        "has_audio": True,
    }

    without_audio = {**valid, "streams": valid["streams"][:1]}
    with pytest.raises(module.AbCanaryError, match="audio"):
        module.validate_media_contract(without_audio, expected_duration=10)


def test_submit_and_wait_surfaces_comfy_error_and_timeout_without_prompt_content():
    module = _load_module()
    responses = iter(
        [
            {"prompt_id": "prompt-1"},
            {
                "prompt-1": {
                    "status": {
                        "completed": False,
                        "status_str": "error",
                        "messages": [["execution_error", {"node_id": "258"}]],
                    }
                }
            },
        ]
    )

    with pytest.raises(module.AbCanaryError, match="ComfyUI execution failed"):
        module.submit_and_wait(
            comfy_url="http://comfy.invalid",
            workflow={"258": {"class_type": "LoraLoaderModelOnly", "inputs": {}}},
            timeout_seconds=1,
            poll_seconds=0,
            http_json_func=lambda *_args, **_kwargs: next(responses),
            sleep_func=lambda _seconds: None,
        )

    with pytest.raises(TimeoutError, match="prompt-2"):
        module.submit_and_wait(
            comfy_url="http://comfy.invalid",
            workflow={},
            timeout_seconds=0,
            poll_seconds=0,
            http_json_func=lambda method, *_args, **_kwargs: (
                {"prompt_id": "prompt-2"} if method == "POST" else {}
            ),
            sleep_func=lambda _seconds: None,
        )
