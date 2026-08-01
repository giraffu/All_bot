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
            "character_description": "an adult woman with a short black bob",
        },
    )
    assert (spec.width, spec.height, spec.cost, spec.frame_count) == (
        768,
        448,
        cost,
        frames,
    )


def test_ltx_t2v_ic_requires_character_description():
    with pytest.raises(LtxT2VValidationError, match="人物描述"):
        build_ltx_t2v_spec(
            "ltx_t2v_ic",
            {
                "duration": 5,
                "resolution": "768x448",
                "character_sheet": "private/sheet.png",
            },
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

    assert "258" not in workflow
    assert workflow["274"]["class_type"] == "ResizeImageMaskNode"
    assert workflow["274"]["inputs"] == {
        "input": ["270", 0],
        "resize_type": "scale shorter dimension",
        "resize_type.shorter_size": 448,
        "scale_method": "lanczos",
    }
    assert workflow["5100"]["inputs"] == {"image": ["274", 0]}
    assert workflow["273"]["class_type"] == "RepeatImageBatch"
    assert workflow["273"]["inputs"] == {
        "image": ["274", 0],
        "amount": 121,
    }
    assert "277" not in workflow
    assert "278" not in workflow
    assert workflow["198"]["class_type"] == "LTXVImgToVideoInplace"
    assert workflow["198"]["inputs"] == {
        "vae": ["127", 2],
        "image": ["712", 0],
        "latent": ["26:39", 0],
        "strength": 1.0,
        "bypass": True,
    }
    assert workflow["115"]["inputs"]["latent"] == ["198", 0]
    assert workflow["115"]["inputs"]["image"] == ["273", 0]
    assert workflow["115"]["inputs"]["frame_idx"] == 0
    assert workflow["115"]["inputs"]["strength"] == 1.0
    assert workflow["26:39"]["inputs"]["width"] == ["5100", 0]
    assert workflow["26:39"]["inputs"]["height"] == ["5100", 1]
    assert workflow["106"]["inputs"]["latent"] == ["121", 0]
    assert workflow["105"]["inputs"]["samples"] == ["106", 2]
    assert workflow["61"]["inputs"]["audio"] == ["107", 0]

    forbidden = {
        "LTX2_NAG",
        "LTXVScheduler",
        "LTXVLatentUpsampler",
        "ComfySwitchNode",
        "TwoWaySwitch",
        "LTXVChunkFeedForward",
        "LTX2SamplingPreviewOverride",
        "LTXICLoRALoaderModelOnly",
        "LTXAddVideoICLoRAGuide",
    }
    assert not {node["class_type"] for node in workflow.values()} & forbidden

    reachable = set()
    pending = ["61"]
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        for value in workflow[node_id].get("inputs", {}).values():
            if isinstance(value, list) and value and value[0] in workflow:
                pending.append(value[0])
    assert reachable == set(workflow)


def test_generated_ingredients_workflow_matches_comfy_official_fast_pipeline():
    import json
    from pathlib import Path

    workflow = json.loads(
        Path(
            "workers/comfy_agent/workflows/LTX 2.3 Sulphur Ingredients T2V.json"
        ).read_text()
    )

    assert workflow["127"] == {
        "inputs": {"ckpt_name": "LTX 2.3/ltx-2.3-22b-distilled-fp8.safetensors"},
        "class_type": "CheckpointLoaderSimple",
    }
    assert workflow["126"] == {
        "inputs": {"ckpt_name": "LTX 2.3/ltx-2.3-22b-distilled-fp8.safetensors"},
        "class_type": "LTXVAudioVAELoader",
    }
    assert workflow["103"]["class_type"] == "LTXAVTextEncoderLoader"
    assert workflow["103"]["inputs"] == {
        "text_encoder": "LTX 2.3/gemma_3_12B_it_fp4_mixed.safetensors",
        "ckpt_name": "LTX 2.3/ltx-2.3-22b-distilled-fp8.safetensors",
        "device": "default",
    }
    assert workflow["195"] == {
        "inputs": {
            "model": ["127", 0],
            "lora_name": "ltx2.3/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors",
            "strength_model": 1.0,
        },
        "class_type": "LoraLoaderModelOnly",
    }
    assert workflow["196"] == {
        "inputs": {"iclora_model": ["195", 0]},
        "class_type": "GetICLoRAParameters",
    }
    assert workflow["198"]["class_type"] == "LTXVImgToVideoInplace"
    assert workflow["198"]["inputs"]["bypass"] is True
    assert workflow["115"]["class_type"] == "LTXVAddGuide"
    assert workflow["115"]["inputs"]["iclora_parameters"] == ["196", 0]
    assert workflow["704"]["class_type"] == "KSampler"
    assert workflow["704"]["inputs"] == {
        "model": ["195", 0],
        "positive": ["115", 0],
        "negative": ["115", 1],
        "latent_image": ["119", 0],
        "seed": -1,
        "steps": 8,
        "cfg": 1.0,
        "sampler_name": "euler_ancestral",
        "scheduler": "linear_quadratic",
        "denoise": 1.0,
    }
    forbidden = {
        "DiffusionModelLoaderKJ",
        "LTXICLoRALoaderModelOnly",
        "LTXAddVideoICLoRAGuide",
        "ManualSigmas",
        "SamplerCustomAdvanced",
    }
    assert not {node["class_type"] for node in workflow.values()} & forbidden


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
        if has_ingredients:
            assert ("258" in workflow) is has_sulphur
        else:
            lora_inputs = workflow["256"]["inputs"]
            assert ("lora_2" in lora_inputs) is has_sulphur
        assert ("195" in workflow) is has_ingredients
        assert ("115" in workflow) is has_ingredients
        if has_ingredients:
            assert workflow["274"]["class_type"] == "ResizeImageMaskNode"
            assert "277" not in workflow
            assert "278" not in workflow
            assert workflow["273"]["class_type"] == "RepeatImageBatch"
            assert workflow["273"]["inputs"] == {
                "image": ["274", 0],
                "amount": 121,
            }
            assert workflow["198"]["class_type"] == "LTXVImgToVideoInplace"
            assert workflow["115"]["inputs"]["latent"] == ["198", 0]
            assert workflow["115"]["inputs"]["image"] == ["273", 0]
            assert workflow["115"]["inputs"]["frame_idx"] == 0
            assert workflow["115"]["inputs"]["iclora_parameters"] == ["196", 0]
            assert workflow["106"]["inputs"]["latent"] == ["121", 0]
            assert workflow["105"]["inputs"]["samples"] == ["106", 2]
            assert workflow["61"]["inputs"]["audio"] == ["107", 0]
