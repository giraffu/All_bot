import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ltx_t2v_msr_ab_smoke.py"


def _load():
    spec = importlib.util.spec_from_file_location("ltx_t2v_msr_ab_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_cases_encodes_one_ingredients_and_three_msr_variants():
    module = _load()
    cases = module.build_cases(
        repo_root=ROOT,
        ingredients_sheet_name="private-sheet.png",
        msr_panel_names=["private-wang-panel.png", "private-man-panel.png"],
        character_descriptions=["same private woman", "same private man"],
        prompt="same private scene",
        seed=20260802,
    )

    assert [case["label"] for case in cases] == [
        "ingredients_5s",
        "msr_v2_5s",
        "msr_v2_sulphur_025_5s",
        "msr_v2_sulphur_050_5s",
    ]
    assert all(case["workflow"]["26:39"]["inputs"]["length"] == 121 for case in cases)
    assert all(case["workflow"]["704"]["inputs"]["seed"] == 20260802 for case in cases)
    assert "msr:800" not in module.case_evidence_metadata(cases[0])["model_chain"]
    for case in cases[1:]:
        workflow = case["workflow"]
        assert workflow["800"]["class_type"] == "LTXICLoRALoaderModelOnly"
        assert workflow["801"]["class_type"] == "LiconMSR"
        assert workflow["801"]["inputs"]["background"] == ["806", 0]
        assert workflow["801"]["inputs"]["1"] == ["802", 0]
        assert workflow["801"]["inputs"]["2"] == ["803", 0]
        assert "3" not in workflow["801"]["inputs"]
        assert workflow["807"]["class_type"] == "LTXAddVideoICLoRAGuide"
        assert workflow["807"]["inputs"]["latent_downscale_factor"] == ["800", 1]
        assert workflow["704"]["inputs"]["model"] in (["800", 0], ["808", 0])
        assert "195" not in workflow
        assert "115" not in workflow
    assert "808" not in cases[1]["workflow"]
    assert cases[2]["workflow"]["808"]["inputs"]["strength_model"] == 0.25
    assert cases[3]["workflow"]["808"]["inputs"]["strength_model"] == 0.5


def test_evidence_does_not_contain_private_inputs():
    module = _load()
    cases = module.build_cases(
        repo_root=ROOT,
        ingredients_sheet_name="secret-sheet.png",
        msr_panel_names=["secret-wang-panel.png", "secret-man-panel.png"],
        character_descriptions=["secret-woman", "secret-man"],
        prompt="secret-prompt",
        seed=7,
    )
    rendered = repr([module.case_evidence_metadata(case) for case in cases])
    assert "secret" not in rendered
