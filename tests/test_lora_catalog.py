from src.lora_catalog import get_ltx_video_lora_default_strength


def test_ltx_video_lora_defaults_match_current_recommendations():
    assert (
        get_ltx_video_lora_default_strength(
            "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors"
        )
        == 0.8
    )
    assert (
        get_ltx_video_lora_default_strength(
            "ltx2.3/SynthPussy_01_rank32.safetensors"
        )
        == 0.8
    )
    assert (
        get_ltx_video_lora_default_strength(
            "ltx2.3/pussyjob_v1.1_merged_ltx23.safetensors"
        )
        == 0.8
    )
    assert (
        get_ltx_video_lora_default_strength(
            "ltx2.3/st0mach_bulge_ltx23_v1.1.safetensors"
        )
        == 0.8
    )
    assert (
        get_ltx_video_lora_default_strength(
            "ltx2.3/nsfw_anal_insertion_ltx23_v1.0.safetensors"
        )
        == 0.8
    )
