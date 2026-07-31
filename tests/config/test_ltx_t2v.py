import pytest

from src.domain_config.ltx_t2v import (
    DISTILLED_LORA_NAME,
    LtxT2VValidationError,
    SULPHUR_LORA_NAME,
    build_ltx_t2v_spec,
)


@pytest.mark.parametrize(
    ("duration", "cost", "frames"),
    [(5, 10, 121), (10, 20, 241), (15, 30, 361), (20, 40, 481)],
)
def test_ltx_t2v_duration_cost_and_frames(duration, cost, frames):
    spec = build_ltx_t2v_spec(
        "ltx_t2v", {"duration": duration, "resolution": "1280x704"}
    )
    assert (spec.cost, spec.frame_count, spec.fps) == (cost, frames, 24)


@pytest.mark.parametrize(
    ("duration", "cost", "frames"),
    [(5, 12, 121), (10, 24, 241), (15, 36, 361), (20, 48, 481)],
)
def test_ltx_t2v_ic_duration_cost_and_frames(duration, cost, frames):
    spec = build_ltx_t2v_spec(
        "ltx_t2v_ic",
        {
            "duration": duration,
            "resolution": "768x448",
            "character_sheet": "private/sheet.png",
        },
    )
    assert (spec.width, spec.height, spec.cost, spec.frame_count) == (
        768,
        448,
        cost,
        frames,
    )


@pytest.mark.parametrize(
    "extra", [{"lora_name": "x.safetensors"}, {"lora_items": [{"name": "x"}]}]
)
def test_ltx_t2v_rejects_user_lora(extra):
    with pytest.raises(LtxT2VValidationError):
        build_ltx_t2v_spec("ltx_t2v", {"duration": 5, **extra})


def test_generated_workflows_have_only_the_fixed_lora_stack():
    import json
    from pathlib import Path

    workflow = json.loads(
        Path("workers/comfy_agent/workflows/LTX 2.3 Sulphur T2V.json").read_text()
    )
    lora_nodes = [
        node
        for node in workflow.values()
        if node.get("class_type") == "Power Lora Loader (rgthree)"
    ]

    assert len(lora_nodes) == 1
    inputs = lora_nodes[0]["inputs"]
    assert inputs["lora_1"] == {
        "on": True,
        "lora": f"ltx2.3/{DISTILLED_LORA_NAME}",
        "strength": 0.5,
    }
    assert inputs["lora_2"] == {
        "on": True,
        "lora": f"ltx2.3/{SULPHUR_LORA_NAME}",
        "strength": 1.0,
    }


def test_generated_ingredients_workflow_uses_official_static_reference_video():
    import json
    from pathlib import Path

    workflow = json.loads(
        Path(
            "workers/comfy_agent/workflows/LTX 2.3 Sulphur Ingredients T2V.json"
        ).read_text()
    )

    assert "lora_2" not in workflow["256"]["inputs"]
    assert workflow["274"]["class_type"] == "ImageScale"
    assert workflow["274"]["inputs"] == {
        "image": ["270", 0],
        "upscale_method": "lanczos",
        "width": 768,
        "height": 448,
        "crop": "disabled",
    }
    assert workflow["273"]["class_type"] == "RepeatImageBatch"
    assert workflow["273"]["inputs"] == {
        "image": ["274", 0],
        "amount": 121,
    }
    assert "277" not in workflow
    assert "278" not in workflow
    assert workflow["275"]["class_type"] == "LTXVPreprocess"
    assert workflow["275"]["inputs"] == {
        "image": ["274", 0],
        "img_compression": 18,
    }
    assert workflow["276"]["class_type"] == "LTXVImgToVideoConditionOnly"
    assert workflow["276"]["inputs"] == {
        "vae": ["283", 0],
        "image": ["275", 0],
        "latent": ["26:39", 0],
        "strength": 1.0,
        "bypass": True,
    }
    assert workflow["272"]["inputs"]["latent"] == ["276", 0]
    assert workflow["272"]["inputs"]["image"] == ["273", 0]
    assert workflow["272"]["inputs"]["frame_idx"] == 0
    assert workflow["26:39"]["inputs"]["width"] == 768
    assert workflow["26:39"]["inputs"]["height"] == 448
    # Ingredients follows the official single-stage path: crop the guide from
    # the first pass and decode it directly instead of spatially upscaling the
    # reference-sheet layout through the legacy second pass.
    assert workflow["26:91"]["inputs"]["latent"] == ["26:153", 0]
    assert workflow["26:149"]["inputs"]["latents"] == ["26:91", 2]
    assert workflow["61"]["inputs"]["audio"] == ["26:154", 0]


def test_ltx_t2v_ab_validation_workflows_encode_the_four_required_stacks():
    import json
    from pathlib import Path

    root = Path("ops/gpu_pool_controller/validation_workflows/ltx_t2v")
    expected = {
        "01_dev_distilled_t2v.json": (False, False),
        "02_dev_distilled_sulphur_t2v.json": (True, False),
        "03_dev_distilled_ingredients_t2v.json": (False, True),
        "04_dev_distilled_sulphur_ingredients_t2v.json": (True, True),
    }
    for filename, (has_sulphur, has_ingredients) in expected.items():
        workflow = json.loads((root / filename).read_text())
        lora_inputs = workflow["256"]["inputs"]
        assert ("lora_2" in lora_inputs) is has_sulphur
        assert ("271" in workflow) is has_ingredients
        assert ("272" in workflow) is has_ingredients
        if has_ingredients:
            assert workflow["274"]["class_type"] == "ImageScale"
            assert "277" not in workflow
            assert "278" not in workflow
            assert workflow["273"]["class_type"] == "RepeatImageBatch"
            assert workflow["273"]["inputs"] == {
                "image": ["274", 0],
                "amount": 121,
            }
            assert workflow["275"]["class_type"] == "LTXVPreprocess"
            assert workflow["276"]["class_type"] == "LTXVImgToVideoConditionOnly"
            assert workflow["272"]["inputs"]["latent"] == ["276", 0]
            assert workflow["272"]["inputs"]["image"] == ["273", 0]
            assert workflow["272"]["inputs"]["frame_idx"] == 0
            # Ingredients decodes the first pass directly. The legacy x2
            # second pass is deliberately orphaned for this profile.
            assert workflow["26:91"]["inputs"]["latent"] == ["26:153", 0]
            assert workflow["26:149"]["inputs"]["latents"] == ["26:91", 2]
            assert workflow["61"]["inputs"]["audio"] == ["26:154", 0]
