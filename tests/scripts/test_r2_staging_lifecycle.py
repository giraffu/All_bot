import pytest

from scripts.r2_staging_lifecycle import (
    STAGING_RULE_ID,
    build_lifecycle_rules,
    validate_apply_gate,
)


def test_lifecycle_plan_preserves_existing_rules_and_adds_only_staging_expiry():
    existing = [
        {
            "ID": "Default Multipart Abort Rule",
            "Status": "Enabled",
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
        }
    ]
    rules = build_lifecycle_rules(existing)

    assert rules[0] == existing[0]
    assert rules[1] == {
        "ID": STAGING_RULE_ID,
        "Status": "Enabled",
        "Filter": {"Prefix": "staging/"},
        "Expiration": {"Days": 1},
    }


def test_lifecycle_plan_replaces_its_own_rule_without_touching_neighbors():
    rules = build_lifecycle_rules(
        [
            {"ID": STAGING_RULE_ID, "Status": "Disabled", "Prefix": "bad/"},
            {"ID": "keep-me", "Status": "Enabled", "Prefix": "other/"},
        ]
    )
    assert [rule["ID"] for rule in rules] == ["keep-me", STAGING_RULE_ID]


@pytest.mark.parametrize(
    ("bucket", "enabled", "confirmation"),
    [
        ("user-data-test", True, "APPLY_STAGING_24H_user-data-test"),
        ("allbot-model-cache", True, "APPLY_STAGING_24H_allbot-model-cache"),
        ("user-data-prod", False, "APPLY_STAGING_24H_user-data-prod"),
        ("user-data-prod", True, "wrong"),
    ],
)
def test_apply_gate_refuses_wrong_bucket_or_missing_confirmation(
    bucket, enabled, confirmation
):
    with pytest.raises(ValueError):
        validate_apply_gate(
            bucket=bucket,
            enabled=enabled,
            confirmation=confirmation,
        )
