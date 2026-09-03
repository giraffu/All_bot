import pytest

from src.services.task_pricing_config_service import (
    TASK_PRICING_CONFIG_KEY,
    TaskPricingConfigValidationError,
    build_task_pricing_catalog,
    normalize_task_pricing_config,
    resolve_configured_task_cost,
    validate_task_pricing_config,
)


def _offers(catalog):
    return {offer["id"]: offer for category in catalog for offer in category["offers"]}


def _variant(offer, **conditions):
    return next(item for item in offer["variants"] if item["conditions"] == conditions)


def test_task_pricing_catalog_uses_sellable_entries_instead_of_execution_registry():
    catalog = build_task_pricing_catalog({"prices": {}})
    offers = _offers(catalog)

    assert set(offers) == {
        "txt2img",
        "fantasy_face",
        "free_edit",
        "free_edit_v2_5",
        "free_edit_v3",
        "face_swap",
        "random_face_swap",
        "image_to_video",
        "image_to_video_v2",
        "advanced_video",
        "advanced_video_v2",
        "text_to_video",
        "advanced_video_pro",
        "video_face_swap",
        "action_transfer",
        "video_replacement",
        "video_face_swap_v2",
        "video_upscale",
        "character_reference",
    }
    serialized = str(catalog)
    assert "blowjob" not in serialized
    assert "undress_tongue" not in serialized
    assert "penetration_step1" not in serialized
    assert "pornmaster_flux2_single_edit" not in serialized
    assert all(category["offers"] for category in catalog)


def test_catalog_exposes_real_image_and_video_pricing_dimensions():
    offers = _offers(build_task_pricing_catalog({"prices": {}}))

    free_edit = offers["free_edit"]
    assert [dimension["key"] for dimension in free_edit["dimensions"]] == [
        "engine",
        "input_count",
    ]
    assert _variant(free_edit, engine="standard", input_count="1")["default_cost"] == 2
    assert _variant(free_edit, engine="standard", input_count="2")["default_cost"] == 6

    pro = offers["advanced_video_pro"]
    assert [dimension["key"] for dimension in pro["dimensions"]] == [
        "mode",
        "resolution",
        "duration",
        "reference_audio",
        "reference_video",
    ]
    assert (
        _variant(
            pro,
            mode="i2v",
            resolution="preview",
            duration="5",
            reference_audio="no",
            reference_video="no",
        )["default_cost"]
        == 10
    )
    assert (
        _variant(
            pro,
            mode="ref2v",
            resolution="hd",
            duration="15",
            reference_audio="yes",
            reference_video="yes",
        )["default_cost"]
        == 91
    )
    assert (
        _variant(
            offers["image_to_video_v2"],
            input_count="2",
            resolution="standard",
            duration="10",
        )["default_cost"]
        == 60
    )
    assert (
        _variant(
            offers["advanced_video"],
            mode="flf2v",
            resolution="1280x704",
            duration="20",
        )["default_cost"]
        == 40
    )
    assert (
        _variant(
            offers["text_to_video"],
            mode="character",
            resolution="768x448",
            duration="20",
        )["default_cost"]
        == 48
    )
    assert _variant(offers["action_transfer"], duration="20")["default_cost"] == 260
    upscale = offers["video_upscale"]
    assert [dimension["key"] for dimension in upscale["dimensions"]] == [
        "resolution",
        "duration",
    ]
    assert _variant(upscale, resolution="720p", duration="10")["default_cost"] == 50
    assert _variant(upscale, resolution="1080p", duration="10")["default_cost"] == 100
    assert _variant(upscale, resolution="2k", duration="10")["default_cost"] == 180


def test_condition_specific_prices_resolve_for_web_and_bot():
    catalog = build_task_pricing_catalog({"prices": {}})
    offers = _offers(catalog)
    one_image = _variant(offers["free_edit_v2_5"], input_count="1")["variant_id"]
    two_images = _variant(offers["free_edit_v2_5"], input_count="2")["variant_id"]
    config = {"prices": {one_image: 4, two_images: 11}}

    upscale_variant = _variant(
        offers["video_upscale"], resolution="1080p", duration="10"
    )["variant_id"]
    assert (
        resolve_configured_task_cost(
            {"prices": {upscale_variant: 123}},
            task_type="ltx25_video_upscale",
            inputs={"images": ["clip.mp4"], "resolution": "1080p", "duration": 10},
            client_type="web",
            default_cost=100,
        )
        == 123
    )

    assert (
        resolve_configured_task_cost(
            config,
            task_type="free_edit_v2_5",
            inputs={"images": ["a.png"]},
            client_type="web",
            default_cost=3,
        )
        == 4
    )
    assert (
        resolve_configured_task_cost(
            config,
            task_type="free_edit_v2_5",
            inputs={"images": ["a.png", "b.png"]},
            client_type="bot",
            default_cost=7,
        )
        == 11
    )
    assert (
        resolve_configured_task_cost(
            config,
            task_type="free_edit_v2_5",
            inputs={},
            client_type="bot",
            default_cost=7,
        )
        == 4
    )
    assert (
        resolve_configured_task_cost(
            config,
            task_type="free_edit_v2_5",
            inputs={"images": ["a.png", "b.png"]},
            client_type="bot:qqcc-private:7",
            default_cost=7,
        )
        == 7
    )

    wan_variant = _variant(
        offers["image_to_video_v2"],
        input_count="2",
        resolution="standard",
        duration="10",
    )["variant_id"]
    assert (
        resolve_configured_task_cost(
            {"prices": {wan_variant: 77}},
            task_type="wan22_video_v2",
            inputs={
                "images": ["first.png", "last.png"],
                "resolution_preset": "standard",
                "duration": 10,
                "use_end_frame": True,
            },
            client_type="web",
            default_cost=60,
        )
        == 77
    )


def test_legacy_flat_overrides_expand_only_to_active_variants():
    normalized = normalize_task_pricing_config(
        {"overrides": {"txt2img": 0, "free_edit_v2_5": 8, "blowjob": 99}}
    )

    assert normalized["schema_version"] == 2
    assert normalized["prices"]
    assert all("blowjob" not in key for key in normalized["prices"])
    assert set(normalized["prices"].values()) == {0, 8}


def test_task_pricing_config_normalizes_missing_prices_without_copying_defaults():
    assert TASK_PRICING_CONFIG_KEY == "task_pricing_config:v1"
    assert normalize_task_pricing_config(None) == {"schema_version": 2, "prices": {}}


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"prices": {"unknown": 1}}, "unknown pricing variant"),
        ({"prices": {"txt2img": -1}}, "non-negative integer"),
        ({"prices": {"txt2img": True}}, "non-negative integer"),
        ({"prices": {"txt2img": 100001}}, "at most 100000"),
    ],
)
def test_task_pricing_config_rejects_unknown_or_invalid_prices(payload, message):
    with pytest.raises(TaskPricingConfigValidationError, match=message):
        validate_task_pricing_config(payload)
