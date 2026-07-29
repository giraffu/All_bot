import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ltx_unified_prod_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ltx_unified_prod_smoke", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prod_smoke_builds_five_serial_cases_with_public_t2v_left_closed():
    module = _load_module()
    cases = module.build_cases(
        image_key="canary/start.png",
        end_image_key="canary/end.png",
        video_key="canary/input.mp4",
        character_sheet_key="canary/character.png",
    )

    assert [case["expected_central_task_type"] for case in cases] == [
        "ltx_video",
        "ltx_video_flf2v",
        "ltx_video_v2v_audio",
        "ltx_t2v",
        "ltx_t2v_ic",
    ]
    assert all(case["payload"]["inputs"]["duration"] == 5 for case in cases)
    assert cases[1]["payload"]["inputs"]["images"] == [
        "canary/start.png",
        "canary/end.png",
    ]
    assert cases[2]["payload"]["inputs"]["video"] == "canary/input.mp4"
    assert cases[4]["payload"]["inputs"]["character_sheet"] == (
        "canary/character.png"
    )
