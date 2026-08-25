import pytest

from scripts.minimax_h3_prod_smoke import (
    DEFAULT_WEB_URL,
    EXPECTED_TYPES,
    MiniMaxH3SmokeError,
    _validate_visual_content,
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


def test_minimax_h3_smoke_covers_both_ref2v_execution_profiles():
    cases = build_cases(image_key="inputs/first.png", end_image_key="inputs/last.png")

    assert [case["expected_central_task_type"] for case in cases] == [
        "minimax_h3_t2v",
        "minimax_h3_i2v",
        "minimax_h3_flf2v",
        "minimax_h3_ref2v",
        "minimax_h3_ref2v",
        "minimax_h3_t2v",
    ]
    assert [case["expected_duration"] for case in cases] == [5, 5, 5, 5, 5, 10]
    assert cases[2]["payload"]["inputs"]["images"] == [
        "inputs/first.png",
        "inputs/last.png",
    ]
    assert cases[3]["payload"]["inputs"]["main_model"] == "10eros"
    assert cases[4]["payload"]["inputs"]["main_model"] == "official"
    assert cases[3]["payload"]["inputs"]["images"] == ["inputs/first.png"]
    assert cases[4]["payload"]["inputs"]["images"] == ["inputs/first.png"]
    assert cases[5]["payload"]["inputs"]["resolution_preset"] == "standard"
    assert cases[0]["payload"]["inputs"]["aspect_ratio"] == "16:9"
    assert cases[1]["payload"]["inputs"]["aspect_ratio"] == "source"
    assert cases[2]["payload"]["inputs"]["aspect_ratio"] == "source"
    assert set(EXPECTED_TYPES) == {
        case["expected_central_task_type"] for case in cases
    }


def test_minimax_h3_smoke_rejects_all_black_video_signalstats():
    output = "\n".join(
        [
            "lavfi.signalstats.YAVG=16",
            "lavfi.signalstats.YMAX=16",
            "lavfi.signalstats.YAVG=16.1",
            "lavfi.signalstats.YMAX=17",
        ]
    )

    with pytest.raises(MiniMaxH3SmokeError, match="all-black"):
        _validate_visual_content(output)


def test_minimax_h3_smoke_accepts_dark_video_with_visible_pixels():
    output = "\n".join(
        [
            "lavfi.signalstats.YAVG=16",
            "lavfi.signalstats.YMAX=18",
            "lavfi.signalstats.YAVG=18",
            "lavfi.signalstats.YMAX=64",
        ]
    )

    stats = _validate_visual_content(output)

    assert stats == {
        "frames_analyzed": 2,
        "min_yavg": 16.0,
        "max_yavg": 18.0,
        "max_ymax": 64.0,
    }


def test_minimax_h3_smoke_rejects_missing_signalstats():
    with pytest.raises(MiniMaxH3SmokeError, match="missing frame luma"):
        _validate_visual_content("ffmpeg produced no metadata")
