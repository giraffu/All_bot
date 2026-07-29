from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.avatar_miniapp.service import (
    ensure_fixture_mode,
    ensure_owned_asset,
    ensure_render_job_can_cancel,
)


def test_fixture_build_fails_closed_when_disabled():
    with pytest.raises(HTTPException) as error:
        ensure_fixture_mode(False)

    assert error.value.status_code == 404
    assert error.value.detail["reason"] == "FIXTURE_MODE_DISABLED"


def test_asset_ownership_is_enforced():
    asset = SimpleNamespace(user_id=20)

    with pytest.raises(HTTPException) as error:
        ensure_owned_asset(asset, user_id=21)

    assert error.value.status_code == 404


@pytest.mark.parametrize("status", ["queued", "rendering"])
def test_non_terminal_render_can_be_cancelled(status):
    job = SimpleNamespace(status=status)

    ensure_render_job_can_cancel(job)


@pytest.mark.parametrize("status", ["ready", "failed", "cancelled"])
def test_terminal_render_cannot_be_cancelled(status):
    job = SimpleNamespace(status=status)

    with pytest.raises(HTTPException) as error:
        ensure_render_job_can_cancel(job)

    assert error.value.status_code == 409
