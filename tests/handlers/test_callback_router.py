import pytest

import qqcc_bot.callback_handler as qqcc_callback_handler
import src.handlers.callback_handler as main_callback_handler
import src.handlers.callback_router as router


def test_validate_callback_routes_reports_missing_prefixes():
    with pytest.raises(RuntimeError, match="missing callback route"):
        router.validate_callback_routes(
            required_prefixes=("known_", "missing_"),
            namespace="test",
            routes={"known_": object()},
        )


def test_callback_manifests_are_registered_and_sorted():
    assert set(main_callback_handler.MAIN_BOT_REQUIRED_CALLBACK_PREFIXES).issubset(
        router.CALLBACK_ROUTES
    )
    assert set(qqcc_callback_handler.QQCC_REQUIRED_CALLBACK_PREFIXES).issubset(
        router.CALLBACK_ROUTES
    )
    assert router.SORTED_ROUTES == sorted(
        router.CALLBACK_ROUTES.keys(),
        key=len,
        reverse=True,
    )
