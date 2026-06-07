import pytest

from src import api_client as api_client_module


@pytest.mark.asyncio
async def test_iter_poll_progress_backs_off_and_resets_on_state_change(monkeypatch):
    client = api_client_module.APIClient.__new__(api_client_module.APIClient)
    payloads = iter(
        [
            {"status": "pending", "progress": 0.1, "queue_pos": 2},
            {"status": "pending", "progress": 0.1, "queue_pos": 2},
            {"status": "running", "progress": 0.5, "queue_pos": None},
            {"status": "done", "progress": 1.0, "queue_pos": None},
        ]
    )
    sleeps = []

    async def fake_fetch_progress_status(_status_url):
        return next(payloads)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(client, "_fetch_progress_status", fake_fetch_progress_status)
    monkeypatch.setattr(
        client,
        "_is_terminal_progress_payload",
        lambda payload: payload.get("status") == "done",
    )
    monkeypatch.setattr(api_client_module, "POLL_INTERVAL", 2)
    monkeypatch.setattr(api_client_module, "BOT_STATUS_POLL_INITIAL_INTERVAL", 5)
    monkeypatch.setattr(api_client_module, "BOT_STATUS_POLL_MAX_INTERVAL", 20)
    monkeypatch.setattr(api_client_module.asyncio, "sleep", fake_sleep)

    events = [
        event
        async for event in client._iter_poll_progress(
            task_id="task-1",
            status_url="http://central/status/task-1",
        )
    ]

    assert [event["status"] for event in events] == [
        "pending",
        "pending",
        "running",
        "done",
    ]
    assert sleeps == [5, 7.5, 5]
