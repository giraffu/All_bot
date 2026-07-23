import io
import os
import tempfile
import uuid
from pathlib import Path

from PIL import Image


test_root = Path(tempfile.gettempdir()) / f"clarity-api-tests-{uuid.uuid4()}"
test_root.mkdir(parents=True)
os.environ["CLARITY_DATABASE_URL"] = (
    f"sqlite+aiosqlite:///{test_root / 'test.sqlite'}"
)
os.environ["CLARITY_LOCAL_STORAGE_PATH"] = str(test_root / "media")
os.environ["CLARITY_ADMIN_EMAIL"] = "admin@example.com"
os.environ["CLARITY_ADMIN_PASSWORD"] = "admin-password-123"
os.environ["CLARITY_AGENT_TOKEN"] = "test-agent-token"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def png_bytes(color: tuple[int, int, int] = (24, 24, 24)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(output, "PNG")
    return output.getvalue()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(client: TestClient, email: str) -> tuple[str, dict]:
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "strong-password-123",
            "accepted_terms": True,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["access_token"], body["user"]


def upload_image(client: TestClient, token: str) -> dict:
    response = client.post(
        "/api/uploads",
        headers=auth_headers(token),
        files={"file": ("source.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_is_independent_and_duplicate_email_is_rejected() -> None:
    with TestClient(app) as client:
        token, user = register(client, "new-user@example.com")
        assert token
        assert user["available_points"] == 100
        assert user["reserved_points"] == 0
        duplicate = client.post(
            "/api/auth/register",
            json={
                "email": "NEW-user@example.com",
                "password": "another-password",
                "accepted_terms": True,
            },
        )
        assert duplicate.status_code == 409


def test_no_worker_keeps_task_queued_and_cancel_releases_reservation() -> None:
    with TestClient(app) as client:
        token, _ = register(client, "queued@example.com")
        source = upload_image(client, token)
        created = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "image_upscale",
                "multiplier": 4,
            },
        )
        assert created.status_code == 201, created.text
        task = created.json()
        assert task["status"] == "queued"
        assert task["status_reason"] == "no_worker_online"
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (96, 4)

        canceled = client.post(
            f"/api/tasks/{task['id']}/cancel", headers=auth_headers(token)
        )
        assert canceled.status_code == 200
        assert canceled.json()["status"] == "canceled"
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (100, 0)


def test_fake_worker_claim_progress_and_complete_captures_points_once() -> None:
    with TestClient(app) as client:
        token, _ = register(client, "worker-flow@example.com")
        source = upload_image(client, token)
        task = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "image_upscale",
                "multiplier": 2,
            },
        ).json()
        agent_headers = {"X-Agent-Token": "test-agent-token"}
        heartbeat = client.post(
            "/api/worker/heartbeat",
            headers=agent_headers,
            json={"worker_id": "fake-gpu-1", "capabilities": ["image_upscale"]},
        )
        assert heartbeat.status_code == 200
        claim = client.post(
            "/api/worker/tasks/claim",
            headers=agent_headers,
            json={"worker_id": "fake-gpu-1"},
        )
        assert claim.status_code == 200
        attempt_id = claim.json()["attempt_id"]
        owned_headers = {
            "X-Agent-Token": "test-agent-token",
            "X-Worker-Id": "fake-gpu-1",
        }
        progress = client.post(
            f"/api/worker/attempts/{attempt_id}/progress",
            headers=owned_headers,
            json={"status": "running", "progress": 54},
        )
        assert progress.status_code == 200
        complete = client.post(
            f"/api/worker/attempts/{attempt_id}/complete",
            headers=owned_headers,
            files={"file": ("result.png", png_bytes((230, 230, 230)), "image/png")},
        )
        assert complete.status_code == 200, complete.text
        result = client.get(
            f"/api/tasks/{task['id']}", headers=auth_headers(token)
        ).json()
        assert result["status"] == "succeeded"
        assert result["progress"] == 100
        assert result["output_file_id"]
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (98, 0)

        admin_login = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "admin-password-123"},
        ).json()
        refund_payload = {
            "points": 1,
            "idempotency_key": f"refund-once-{task['id']}",
            "reason": "quality review",
        }
        first_refund = client.post(
            f"/api/admin/tasks/{task['id']}/refund",
            headers=auth_headers(admin_login["access_token"]),
            json=refund_payload,
        )
        repeated_refund = client.post(
            f"/api/admin/tasks/{task['id']}/refund",
            headers=auth_headers(admin_login["access_token"]),
            json=refund_payload,
        )
        assert first_refund.status_code == repeated_refund.status_code == 200
        assert first_refund.json()["refunded_points"] == 1
        assert repeated_refund.json()["refunded_points"] == 1
        excessive = client.post(
            f"/api/admin/tasks/{task['id']}/refund",
            headers=auth_headers(admin_login["access_token"]),
            json={
                "points": 2,
                "idempotency_key": f"refund-too-much-{task['id']}",
                "reason": "must not exceed charge",
            },
        )
        assert excessive.status_code == 409
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (99, 0)


def test_refresh_logout_media_validation_and_ownership() -> None:
    with TestClient(app) as client:
        owner_token, _ = register(client, "owner@example.com")
        other_token, _ = register(client, "other@example.com")
        source = upload_image(client, owner_token)

        forbidden_download = client.get(
            f"/api/uploads/{source['id']}/download",
            headers=auth_headers(other_token),
        )
        forbidden_task = client.post(
            "/api/tasks",
            headers=auth_headers(other_token),
            json={
                "source_file_id": source["id"],
                "task_type": "image_upscale",
                "multiplier": 2,
            },
        )
        assert forbidden_download.status_code == 404
        assert forbidden_task.status_code == 404

        queued = client.post(
            "/api/tasks",
            headers=auth_headers(owner_token),
            json={
                "source_file_id": source["id"],
                "task_type": "image_upscale",
                "multiplier": 2,
            },
        ).json()
        blocked_delete = client.delete(
            f"/api/uploads/{source['id']}", headers=auth_headers(owner_token)
        )
        assert blocked_delete.status_code == 409
        assert (
            client.post(
                f"/api/tasks/{queued['id']}/cancel",
                headers=auth_headers(owner_token),
            ).status_code
            == 200
        )
        assert (
            client.delete(
                f"/api/uploads/{source['id']}",
                headers=auth_headers(owner_token),
            ).status_code
            == 200
        )
        deleted_download = client.get(
            f"/api/uploads/{source['id']}/download",
            headers=auth_headers(owner_token),
        )
        assert deleted_download.status_code == 410

        invalid = client.post(
            "/api/uploads",
            headers=auth_headers(owner_token),
            files={"file": ("not-an-image.png", b"plain text", "image/png")},
        )
        assert invalid.status_code == 415

        refreshed = client.post("/api/auth/refresh")
        assert refreshed.status_code == 200
        assert refreshed.json()["access_token"]
        assert client.post("/api/auth/logout").status_code == 200
        assert client.post("/api/auth/refresh").status_code == 401


def test_expired_lease_gets_a_new_attempt_identity() -> None:
    from app import api as api_module

    with TestClient(app) as client:
        token, _ = register(client, "lease@example.com")
        source = upload_image(client, token)
        task = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "image_upscale",
                "multiplier": 2,
            },
        ).json()
        agent_headers = {"X-Agent-Token": "test-agent-token"}
        client.post(
            "/api/worker/heartbeat",
            headers=agent_headers,
            json={"worker_id": "lease-worker", "capabilities": ["image_upscale"]},
        )
        original_lease = api_module.settings.worker_lease_seconds
        try:
            api_module.settings.worker_lease_seconds = -1
            first = client.post(
                "/api/worker/tasks/claim",
                headers=agent_headers,
                json={"worker_id": "lease-worker"},
            ).json()
            assert first["task_id"] == task["id"]
            api_module.settings.worker_lease_seconds = original_lease
            second = client.post(
                "/api/worker/tasks/claim",
                headers=agent_headers,
                json={"worker_id": "lease-worker"},
            ).json()
        finally:
            api_module.settings.worker_lease_seconds = original_lease
        assert second["task_id"] == task["id"]
        assert second["attempt_id"] != first["attempt_id"]
        current = client.get(
            f"/api/tasks/{task['id']}", headers=auth_headers(token)
        ).json()
        assert [item["attempt_number"] for item in current["attempts"]] == [1, 2]


def test_admin_role_is_enforced() -> None:
    with TestClient(app) as client:
        token, _ = register(client, "ordinary@example.com")
        forbidden = client.get("/api/admin/summary", headers=auth_headers(token))
        assert forbidden.status_code == 403
        login = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "admin-password-123"},
        )
        assert login.status_code == 200
        summary = client.get(
            "/api/admin/summary",
            headers=auth_headers(login.json()["access_token"]),
        )
        assert summary.status_code == 200
        assert summary.json()["users"] >= 2


def test_worker_failure_releases_points_and_admin_retry_reserves_once() -> None:
    with TestClient(app) as client:
        token, _ = register(client, "retry@example.com")
        source = upload_image(client, token)
        task = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "image_upscale",
                "multiplier": 2,
            },
        ).json()
        agent_headers = {"X-Agent-Token": "test-agent-token"}
        client.post(
            "/api/worker/heartbeat",
            headers=agent_headers,
            json={"worker_id": "fake-gpu-retry", "capabilities": ["image_upscale"]},
        )
        claim = client.post(
            "/api/worker/tasks/claim",
            headers=agent_headers,
            json={"worker_id": "fake-gpu-retry"},
        ).json()
        failed = client.post(
            f"/api/worker/attempts/{claim['attempt_id']}/fail",
            headers={
                **agent_headers,
                "X-Worker-Id": "fake-gpu-retry",
            },
            json={
                "error_code": "gpu_oom",
                "error_detail": "test",
                "retryable": True,
            },
        )
        assert failed.status_code == 200
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (100, 0)

        admin_login = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "admin-password-123"},
        ).json()
        retried = client.post(
            f"/api/admin/tasks/{task['id']}/retry",
            headers=auth_headers(admin_login["access_token"]),
        )
        assert retried.status_code == 200, retried.text
        assert retried.json()["attempts"][-1]["attempt_number"] == 2
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (98, 2)


def test_copyright_complaint_can_be_submitted_without_login() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/legal/copyright-complaints",
            json={
                "email": "rights-holder@example.com",
                "subject": "Copyright notice",
                "content": "I am the rights holder and request a review of the identified media.",
            },
        )
        assert response.status_code == 201
        assert response.json()["kind"] == "copyright"
        assert response.json()["status"] == "open"
