import config


def test_append_version_query_adds_version_to_plain_url():
    url = config.append_version_query(
        "https://web.aivison.it.com/",
        "20260528-1",
    )

    assert url == "https://web.aivison.it.com/?v=20260528-1"


def test_append_version_query_replaces_existing_version_and_keeps_other_params():
    url = config.append_version_query(
        "https://web.aivison.it.com/?from=tg&v=old-build",
        "20260528-2",
    )

    assert url == "https://web.aivison.it.com/?from=tg&v=20260528-2"


def test_build_versioned_mini_app_url_uses_explicit_arguments_without_global_env():
    url = config.build_versioned_mini_app_url(
        base_url="https://web.aivison.it.com/app?from=profile",
        version="release-42",
    )

    assert url == "https://web.aivison.it.com/app?from=profile&v=release-42"


def test_build_ton_payment_mini_app_url_targets_membership_billing():
    url = config.build_ton_payment_mini_app_url(
        base_url="https://web.aivison.it.com/app?from=bot",
        version="release-42",
    )

    assert url == (
        "https://web.aivison.it.com/app/billing"
        "?from=bot&method=ton&kind=membership&v=release-42"
    )
