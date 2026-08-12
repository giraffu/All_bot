from scripts.minimax_h3_prod_smoke import (
    DEFAULT_WEB_URL,
    EXPECTED_TYPES,
    build_cases,
    build_control_config,
)


def test_minimax_h3_smoke_defaults_to_live_web_api_prefix():
    assert DEFAULT_WEB_URL == "https://api.aivison.it.com/api"


def test_minimax_h3_smoke_uses_existing_operator_canary_jwt_channel(monkeypatch):
    monkeypatch.delenv("RUNPOD_CANARY_WEB_BEARER_TOKEN", raising=False)

    config = build_control_config(
        central_url="https://central.example",
        web_user_id=3,
        web_pwd_ver=0,
    )

    assert config.jwt_channel == "runpod_canary"
    assert config.web_bearer_token == ""


def test_minimax_h3_smoke_builds_four_preview_modes_then_standard_t2v():
    cases = build_cases(image_key="inputs/first.png", end_image_key="inputs/last.png")

    assert [case["expected_central_task_type"] for case in cases] == [
        *EXPECTED_TYPES,
        "minimax_h3_t2v",
    ]
    assert [case["expected_duration"] for case in cases] == [5, 5, 5, 5, 10]
    assert cases[2]["payload"]["inputs"]["images"] == [
        "inputs/first.png",
        "inputs/last.png",
    ]
    assert cases[3]["payload"]["inputs"]["reference_descriptions"]
    assert cases[4]["payload"]["inputs"]["resolution_preset"] == "standard"
    assert cases[0]["payload"]["inputs"]["aspect_ratio"] == "16:9"
    assert cases[1]["payload"]["inputs"]["aspect_ratio"] == "source"
    assert cases[2]["payload"]["inputs"]["aspect_ratio"] == "source"
    assert cases[3]["payload"]["inputs"]["aspect_ratio"] == "16:9"
