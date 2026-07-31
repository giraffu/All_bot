import pytest
from pydantic import ValidationError

from backend.app.models import LtxT2VRequest


def test_ltx_t2v_request_preserves_nonnegative_seed():
    request = LtxT2VRequest(
        task_id="task-1",
        prompt="scene",
        seed=65608997764964,
    )

    assert request.model_dump()["seed"] == 65608997764964


def test_ltx_t2v_request_rejects_negative_seed():
    with pytest.raises(ValidationError):
        LtxT2VRequest(task_id="task-1", prompt="scene", seed=-1)
