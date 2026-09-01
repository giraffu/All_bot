import asyncio
import io
import itertools
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

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import CreditEntry, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.sms_verification import SmsVerificationProvider, get_sms_provider  # noqa: E402


class FakeSmsVerificationProvider(SmsVerificationProvider):
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    async def send_code(self, phone_number: str, out_id: str) -> str:
        self.codes[phone_number] = "246810"
        return f"fake:{out_id}"

    async def check_code(
        self, phone_number: str, verify_code: str, out_id: str
    ) -> bool:
        return self.codes.get(phone_number) == verify_code


fake_sms = FakeSmsVerificationProvider()
app.dependency_overrides[get_sms_provider] = lambda: fake_sms
phone_sequence = itertools.count(1)


def png_bytes(color: tuple[int, int, int] = (24, 24, 24)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(output, "PNG")
    return output.getvalue()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_unverified(client: TestClient, email: str) -> tuple[str, dict]:
    async def seed_legacy_user() -> None:
        async with SessionLocal() as db:
            user = User(
                email=email.lower(),
                password_hash=hash_password("strong-password-123"),
                available_points=100,
            )
            db.add(user)
            await db.flush()
            db.add(
                CreditEntry(
                    user_id=user.id,
                    kind="welcome",
                    available_delta=100,
                    reserved_delta=0,
                    idempotency_key=f"welcome:{user.id}",
                )
            )
            await db.commit()

    asyncio.run(seed_legacy_user())
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "strong-password-123"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["access_token"], body["user"]


def verify_phone(client: TestClient, token: str, phone_number: str) -> dict:
    sent = client.post(
        "/api/auth/phone/send",
        headers=auth_headers(token),
        json={"phone_number": phone_number},
    )
    assert sent.status_code == 202, sent.text
    verified = client.post(
        "/api/auth/phone/verify",
        headers=auth_headers(token),
        json={
            "challenge_id": sent.json()["challenge_id"],
            "phone_number": phone_number,
            "verify_code": "246810",
        },
    )
    assert verified.status_code == 200, verified.text
    return verified.json()


def register(client: TestClient, email: str) -> tuple[str, dict]:
    phone_number = f"138{next(phone_sequence):08d}"
    sent = client.post(
        "/api/auth/register/phone/send",
        headers={"x-forwarded-for": f"203.0.113.{next(phone_sequence)}"},
        json={"phone_number": phone_number},
    )
    assert sent.status_code == 202, sent.text
    response = client.post(
        "/api/auth/register",
        json={
            "challenge_id": sent.json()["challenge_id"],
            "phone_number": phone_number,
            "verify_code": "246810",
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


def upload_video(
    client: TestClient,
    token: str,
    monkeypatch,
    *,
    duration_seconds: float = 5.0,
    size_bytes: int = 1024,
) -> dict:
    from app import api as api_module

    monkeypatch.setattr(
        api_module,
        "_probe_video",
        lambda _path: ("video/mp4", duration_seconds, 672, 384),
    )
    response = client.post(
        "/api/uploads",
        headers=auth_headers(token),
        files={"file": ("source.mp4", b"v" * size_bytes, "video/mp4")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_phone_verification_is_required_before_upload(monkeypatch) -> None:
    with TestClient(app) as client:
        token, user = register_unverified(client, "phone-gate@example.com")
        assert user["phone_verified"] is False
        blocked = client.post(
            "/api/uploads",
            headers=auth_headers(token),
            files={"file": ("source.mp4", b"video", "video/mp4")},
        )
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "phone_verification_required"

        verified = verify_phone(client, token, "13800138000")
        assert verified["phone_verified"] is True
        assert verified["phone_masked"] == "138****8000"
        uploaded = upload_video(client, token, monkeypatch)
        assert uploaded["media_kind"] == "video"


def test_api_responses_include_browser_security_headers() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "camera=()" in response.headers["permissions-policy"]


def test_phone_verification_throttles_sends_and_failed_checks() -> None:
    with TestClient(app) as client:
        token, _ = register_unverified(client, "phone-limits@example.com")
        phone_number = "13900139000"
        sent = client.post(
            "/api/auth/phone/send",
            headers=auth_headers(token),
            json={"phone_number": phone_number},
        )
        assert sent.status_code == 202
        repeated = client.post(
            "/api/auth/phone/send",
            headers=auth_headers(token),
            json={"phone_number": phone_number},
        )
        assert repeated.status_code == 429
        assert repeated.json()["detail"] == "sms_send_too_frequent"

        payload = {
            "challenge_id": sent.json()["challenge_id"],
            "phone_number": phone_number,
            "verify_code": "000000",
        }
        for _ in range(5):
            failed = client.post(
                "/api/auth/phone/verify",
                headers=auth_headers(token),
                json=payload,
            )
            assert failed.status_code == 422
            assert failed.json()["detail"] == "invalid_verify_code"
        blocked = client.post(
            "/api/auth/phone/verify",
            headers=auth_headers(token),
            json={**payload, "verify_code": "246810"},
        )
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == "sms_verify_attempts_exceeded"


def test_verified_phone_cannot_be_bound_to_another_account() -> None:
    with TestClient(app) as client:
        first_token, _ = register_unverified(client, "phone-owner@example.com")
        verify_phone(client, first_token, "13700137000")
        second_token, _ = register_unverified(client, "phone-other@example.com")
        duplicate = client.post(
            "/api/auth/phone/send",
            headers=auth_headers(second_token),
            json={"phone_number": "13700137000"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "phone_already_bound"


def test_public_submission_is_video_upscale_only(monkeypatch) -> None:
    with TestClient(app) as client:
        token, _ = register(client, "video-only@example.com")
        image = upload_image(client, token)
        video = upload_video(client, token, monkeypatch)

        requests = (
            (image, "image_upscale", 2, "video_upscale_only"),
            (video, "frame_interpolation", 2, "video_upscale_only"),
            (video, "video_upscale", 4, "video_upscale_requires_2x"),
        )
        for source, task_type, multiplier, expected_detail in requests:
            response = client.post(
                "/api/tasks",
                headers=auth_headers(token),
                json={
                    "source_file_id": source["id"],
                    "task_type": task_type,
                    "multiplier": multiplier,
                },
            )
            assert response.status_code == 422
            assert response.json()["detail"] == expected_detail


def test_video_upscale_rejects_test_worker_limit_overruns(monkeypatch) -> None:
    with TestClient(app) as client:
        token, _ = register(client, "video-limits@example.com")
        too_long = upload_video(
            client,
            token,
            monkeypatch,
            duration_seconds=5.01,
        )
        too_large = upload_video(
            client,
            token,
            monkeypatch,
            size_bytes=40 * 1024 * 1024 + 1,
        )

        for source, expected_detail in (
            (too_long, "video_upscale_max_5_seconds"),
            (too_large, "video_upscale_max_40_mb"),
        ):
            response = client.post(
                "/api/tasks",
                headers=auth_headers(token),
                json={
                    "source_file_id": source["id"],
                    "task_type": "video_upscale",
                    "multiplier": 2,
                },
            )
            assert response.status_code == 422
            assert response.json()["detail"] == expected_detail


def test_registration_grants_welcome_credit_once() -> None:
    with TestClient(app) as client:
        token, user = register(client, "new-user@example.com")
        assert token
        assert user["available_points"] == 100
        assert user["reserved_points"] == 0


def test_phone_registration_verifies_identity_and_rejects_email_signup() -> None:
    with TestClient(app) as client:
        phone_number = "13600136000"
        sent = client.post(
            "/api/auth/register/phone/send",
            json={"phone_number": phone_number},
        )
        assert sent.status_code == 202, sent.text

        registered = client.post(
            "/api/auth/register",
            json={
                "challenge_id": sent.json()["challenge_id"],
                "phone_number": phone_number,
                "verify_code": "246810",
                "password": "strong-password-123",
                "accepted_terms": True,
            },
        )
        assert registered.status_code == 201, registered.text
        user = registered.json()["user"]
        assert user["email"] is None
        assert user["phone_verified"] is True
        assert user["phone_masked"] == "136****6000"
        assert user["available_points"] == 100

        login = client.post(
            "/api/auth/login",
            json={
                "identifier": "+86 13600136000",
                "password": "strong-password-123",
            },
        )
        assert login.status_code == 200, login.text
        assert login.json()["user"]["id"] == user["id"]

        duplicate = client.post(
            "/api/auth/register/phone/send",
            json={"phone_number": phone_number},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "phone_already_bound"

        email_signup = client.post(
            "/api/auth/register",
            json={
                "email": "new-email-signup@example.com",
                "password": "strong-password-123",
                "accepted_terms": True,
            },
        )
        assert email_signup.status_code == 422


def test_phone_registration_rejects_bad_code_and_consumed_challenge() -> None:
    with TestClient(app) as client:
        phone_number = "13500135000"
        sent = client.post(
            "/api/auth/register/phone/send",
            headers={"x-forwarded-for": "203.0.113.135"},
            json={"phone_number": phone_number},
        )
        assert sent.status_code == 202, sent.text
        payload = {
            "challenge_id": sent.json()["challenge_id"],
            "phone_number": phone_number,
            "password": "strong-password-123",
            "accepted_terms": True,
        }
        failed = client.post(
            "/api/auth/register", json={**payload, "verify_code": "000000"}
        )
        assert failed.status_code == 422
        assert failed.json()["detail"] == "invalid_verify_code"

        registered = client.post(
            "/api/auth/register", json={**payload, "verify_code": "246810"}
        )
        assert registered.status_code == 201
        replay = client.post(
            "/api/auth/register", json={**payload, "verify_code": "246810"}
        )
        assert replay.status_code == 409
        assert replay.json()["detail"] == "sms_challenge_consumed"


def test_legacy_email_account_can_still_log_in() -> None:
    with TestClient(app) as client:
        token, user = register_unverified(client, "legacy-login@example.com")
        assert token
        assert user["email"] == "legacy-login@example.com"
        assert user["phone_verified"] is False


def test_no_worker_keeps_task_queued_and_cancel_releases_reservation(monkeypatch) -> None:
    with TestClient(app) as client:
        token, _ = register(client, "queued@example.com")
        source = upload_video(client, token, monkeypatch)
        created = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "video_upscale",
                "multiplier": 2,
            },
        )
        assert created.status_code == 201, created.text
        task = created.json()
        assert task["status"] == "queued"
        assert task["status_reason"] == "no_worker_online"
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (95, 5)

        canceled = client.post(
            f"/api/tasks/{task['id']}/cancel", headers=auth_headers(token)
        )
        assert canceled.status_code == 200
        assert canceled.json()["status"] == "canceled"
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (100, 0)


def test_fake_worker_claim_progress_and_complete_captures_points_once(monkeypatch) -> None:
    with TestClient(app) as client:
        token, _ = register(client, "worker-flow@example.com")
        source = upload_video(client, token, monkeypatch)
        task = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "video_upscale",
                "multiplier": 2,
            },
        ).json()
        agent_headers = {"X-Agent-Token": "test-agent-token"}
        heartbeat = client.post(
            "/api/worker/heartbeat",
            headers=agent_headers,
            json={"worker_id": "fake-gpu-1", "capabilities": ["video_upscale"]},
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
            files={"file": ("result.mp4", b"enhanced-video", "video/mp4")},
        )
        assert complete.status_code == 200, complete.text
        result = client.get(
            f"/api/tasks/{task['id']}", headers=auth_headers(token)
        ).json()
        assert result["status"] == "succeeded"
        assert result["progress"] == 100
        assert result["output_file_id"]
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (95, 0)

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
                "points": 5,
                "idempotency_key": f"refund-too-much-{task['id']}",
                "reason": "must not exceed charge",
            },
        )
        assert excessive.status_code == 409
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (96, 0)


def test_refresh_logout_media_validation_and_ownership(monkeypatch) -> None:
    with TestClient(app) as client:
        owner_token, _ = register(client, "owner@example.com")
        other_token, _ = register(client, "other@example.com")
        source = upload_video(client, owner_token, monkeypatch)

        forbidden_download = client.get(
            f"/api/uploads/{source['id']}/download",
            headers=auth_headers(other_token),
        )
        forbidden_task = client.post(
            "/api/tasks",
            headers=auth_headers(other_token),
            json={
                "source_file_id": source["id"],
                "task_type": "video_upscale",
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
                "task_type": "video_upscale",
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


def test_expired_lease_gets_a_new_attempt_identity(monkeypatch) -> None:
    from app import api as api_module

    with TestClient(app) as client:
        token, _ = register(client, "lease@example.com")
        source = upload_video(client, token, monkeypatch)
        task = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "video_upscale",
                "multiplier": 2,
            },
        ).json()
        agent_headers = {"X-Agent-Token": "test-agent-token"}
        client.post(
            "/api/worker/heartbeat",
            headers=agent_headers,
            json={"worker_id": "lease-worker", "capabilities": ["video_upscale"]},
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


def test_bound_provider_attempt_resumes_same_identity_after_lease_expiry(
    monkeypatch,
) -> None:
    from app import api as api_module

    with TestClient(app) as client:
        token, _ = register(client, "provider-resume@example.com")
        source = upload_video(client, token, monkeypatch)
        task = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "video_upscale",
                "multiplier": 2,
            },
        ).json()
        agent_headers = {"X-Agent-Token": "test-agent-token"}
        owned_headers = {**agent_headers, "X-Worker-Id": "bridge-resume"}
        client.post(
            "/api/worker/heartbeat",
            headers=agent_headers,
            json={
                "worker_id": "bridge-resume",
                "capabilities": ["video_upscale"],
            },
        )
        first = client.post(
            "/api/worker/tasks/claim",
            headers=agent_headers,
            json={"worker_id": "bridge-resume"},
        ).json()
        provider_task_id = f"clarity-{task['id']}-{first['attempt_id']}"
        bound = client.post(
            f"/api/worker/attempts/{first['attempt_id']}/provider",
            headers=owned_headers,
            json={
                "provider": "allbot-test-central",
                "provider_task_id": provider_task_id,
            },
        )
        assert bound.status_code == 200, bound.text

        original_lease = api_module.settings.worker_lease_seconds
        try:
            api_module.settings.worker_lease_seconds = -1
            progress = client.post(
                f"/api/worker/attempts/{first['attempt_id']}/progress",
                headers=owned_headers,
                json={"status": "running", "progress": 25},
            )
            assert progress.status_code == 200
            api_module.settings.worker_lease_seconds = original_lease
            resumed = client.post(
                "/api/worker/tasks/claim",
                headers=agent_headers,
                json={"worker_id": "bridge-resume"},
            ).json()
        finally:
            api_module.settings.worker_lease_seconds = original_lease

        assert resumed["attempt_id"] == first["attempt_id"]
        assert resumed["attempt_number"] == 1
        assert resumed["provider_task_id"] == provider_task_id


def test_running_bridge_task_can_be_canceled_without_late_resurrection(
    monkeypatch,
) -> None:
    with TestClient(app) as client:
        token, _ = register(client, "active-cancel@example.com")
        source = upload_video(client, token, monkeypatch)
        task = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "video_upscale",
                "multiplier": 2,
            },
        ).json()
        agent_headers = {"X-Agent-Token": "test-agent-token"}
        owned_headers = {**agent_headers, "X-Worker-Id": "bridge-cancel"}
        client.post(
            "/api/worker/heartbeat",
            headers=agent_headers,
            json={
                "worker_id": "bridge-cancel",
                "capabilities": ["video_upscale"],
            },
        )
        claim = client.post(
            "/api/worker/tasks/claim",
            headers=agent_headers,
            json={"worker_id": "bridge-cancel"},
        ).json()
        client.post(
            f"/api/worker/attempts/{claim['attempt_id']}/progress",
            headers=owned_headers,
            json={"status": "running", "progress": 30},
        )

        canceled = client.post(
            f"/api/tasks/{task['id']}/cancel", headers=auth_headers(token)
        )
        assert canceled.status_code == 200
        assert canceled.json()["status"] == "canceled"
        late_progress = client.post(
            f"/api/worker/attempts/{claim['attempt_id']}/progress",
            headers=owned_headers,
            json={"status": "running", "progress": 60},
        )
        assert late_progress.status_code == 409
        current = client.get(
            f"/api/tasks/{task['id']}", headers=auth_headers(token)
        ).json()
        assert current["status"] == "canceled"
        me = client.get("/api/auth/me", headers=auth_headers(token)).json()
        assert (me["available_points"], me["reserved_points"]) == (100, 0)


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


def test_worker_failure_releases_points_and_admin_retry_reserves_once(monkeypatch) -> None:
    with TestClient(app) as client:
        token, _ = register(client, "retry@example.com")
        source = upload_video(client, token, monkeypatch)
        task = client.post(
            "/api/tasks",
            headers=auth_headers(token),
            json={
                "source_file_id": source["id"],
                "task_type": "video_upscale",
                "multiplier": 2,
            },
        ).json()
        agent_headers = {"X-Agent-Token": "test-agent-token"}
        client.post(
            "/api/worker/heartbeat",
            headers=agent_headers,
            json={"worker_id": "fake-gpu-retry", "capabilities": ["video_upscale"]},
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
        assert (me["available_points"], me["reserved_points"]) == (95, 5)


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
