import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app.prompt_mart import PROMPT_NORMALIZATION_VERSION
from local_analytics_platform.app.prompt_vectors import DEFAULT_VECTOR_MODEL_ID


@pytest.fixture(autouse=True)
def clear_prompt_vector_resume_state():
    state = analytics_main.app.state._state
    for key in (
        "prompt_vector_resume_process",
        "prompt_vector_resume_started_at",
        "prompt_vector_resume_last_exit",
    ):
        state.pop(key, None)
    yield
    for key in (
        "prompt_vector_resume_process",
        "prompt_vector_resume_started_at",
        "prompt_vector_resume_last_exit",
    ):
        state.pop(key, None)


@pytest.mark.asyncio
async def test_prompt_vectors_returns_stable_empty_state_when_tables_missing(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "analytics_prompt_vector_state" in query:
            return {"ready": False}
        raise AssertionError(f"unexpected query: {query}")

    async def fake_fetch(query, *args):
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-vectors")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["summary"]["candidate_count"] == 0
    assert payload["summary"]["embedded_count"] == 0
    assert payload["summary"]["pending_count"] == 0
    assert payload["summary"]["failed_count"] == 0
    assert payload["distributions"] == {"task_type": [], "status": []}
    assert "clusters" not in payload
    assert payload["resume"]["running"] is False


@pytest.mark.asyncio
async def test_prompt_vectors_returns_embedding_summary_and_distributions(monkeypatch):
    async def fake_fetchrow(query, *args):
        lower = query.lower()
        if "analytics_prompt_vector_state" in lower and "to_regclass" in lower:
            return {"ready": True}
        if "candidate_count" in lower and "embedded_count" in lower and "failed_count" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION)
            return {
                "candidate_count": 100,
                "embedded_count": 80,
                "failed_count": 2,
                "latest_embedded_at": "2026-07-04T12:00:00",
            }
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        lower = query.lower()
        if "from analytics_prompt_vector_state" in lower:
            return [
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:embedding_dim",
                    "value": "4096",
                    "updated_at": "2026-07-04T12:00:00",
                },
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:last_success_at",
                    "value": '"2026-07-04T12:00:00"',
                    "updated_at": "2026-07-04T12:00:00",
                },
                {
                    "key": f"{DEFAULT_VECTOR_MODEL_ID}:{PROMPT_NORMALIZATION_VERSION}:index_dir",
                    "value": '"/legacy/usearch/index"',
                    "updated_at": "2026-07-04T12:00:00",
                },
            ]
        if "from analytics_prompt_embeddings" in lower and "group by task_type" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION)
            return [{"label": "edit", "count": 50}, {"label": "custom_video", "count": 30}]
        if "from analytics_prompt_embeddings" in lower and "group by status" in lower:
            assert args == (DEFAULT_VECTOR_MODEL_ID, PROMPT_NORMALIZATION_VERSION)
            return [{"label": "embedded", "count": 80}, {"label": "error", "count": 2}]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.get("/api/prompt-vectors")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["summary"]["embedding_coverage"] == 80.0
    assert payload["summary"]["pending_count"] == 20
    assert payload["summary"]["failed_count"] == 2
    assert payload["model"]["embedding_dim"] == 4096
    assert "index_dir" not in payload["model"]
    assert payload["distributions"]["task_type"] == [
        {"label": "edit", "count": 50},
        {"label": "custom_video", "count": 30},
    ]
    assert payload["distributions"]["status"] == [
        {"label": "embedded", "count": 80},
        {"label": "error", "count": 2},
    ]
    assert "clusters" not in payload


@pytest.mark.asyncio
async def test_removed_prompt_analysis_routes_are_not_registered():
    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        paths = [
            "/api/prompt-vectors/clusters/cluster1",
            "/api/prompt-near-representatives",
            "/api/prompt-near-graph",
            "/api/prompt-scenes",
            "/api/prompt-graph",
        ]
        responses = [await client.get(path) for path in paths]

    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404]


@pytest.mark.asyncio
async def test_prompt_vectors_resume_starts_embed_only_process(monkeypatch, tmp_path):
    calls = {}

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(analytics_main, "PROMPT_VECTOR_RESUME_LOG", tmp_path / "resume.log")
    monkeypatch.setattr(analytics_main, "_database_url", lambda: "postgresql://local/test")
    monkeypatch.setattr(analytics_main, "_is_prompt_vector_refresh_lock_held", lambda: False)
    monkeypatch.setattr(analytics_main.subprocess, "Popen", fake_popen)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.post("/api/prompt-vectors/resume")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "started"
    assert payload["pid"] == 4242
    assert calls["command"][1:4] == ["-m", "app.refresh_prompt_vectors", "--embed-only"]
    assert "--batch-size" in calls["command"]
    assert "--data-dir" in calls["command"]
    assert calls["kwargs"]["env"]["LOCAL_ANALYTICS_DATABASE_URL"] == "postgresql://local/test"


@pytest.mark.asyncio
async def test_prompt_vectors_resume_reports_running_when_lock_is_held(monkeypatch, tmp_path):
    def fail_popen(*args, **kwargs):
        raise AssertionError("resume should not start a second process")

    monkeypatch.setattr(analytics_main, "PROMPT_VECTOR_RESUME_LOG", tmp_path / "resume.log")
    monkeypatch.setattr(analytics_main, "_is_prompt_vector_refresh_lock_held", lambda: True)
    monkeypatch.setattr(analytics_main.subprocess, "Popen", fail_popen)

    async with AsyncClient(transport=ASGITransport(app=analytics_main.app), base_url="http://test") as client:
        response = await client.post("/api/prompt-vectors/resume")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["resume"]["lock_held"] is True
