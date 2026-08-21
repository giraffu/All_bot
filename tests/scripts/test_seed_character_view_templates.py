from scripts.seed_character_view_templates import ASSET_ROOT, TEMPLATES, durable_object_key


def test_character_template_seed_manifest_is_complete_and_deterministic():
    assert [(item.view_type, item.gender) for item in TEMPLATES] == [
        ("torso_front", "female"),
        ("genitals_front", "female"),
        ("genitals_front", "female"),
        ("genitals_front", "male"),
        ("pelvis_back", "female"),
    ]
    assert len({item.id for item in TEMPLATES}) == len(TEMPLATES)
    for item in TEMPLATES:
        path = ASSET_ROOT / item.filename
        payload = path.read_bytes()
        assert payload
        assert durable_object_key(item, payload) == durable_object_key(item, payload)
