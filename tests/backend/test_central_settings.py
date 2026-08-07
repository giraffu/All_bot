from app.config import Settings


def test_legacy_media_completion_remains_enabled_until_explicit_cutover():
    settings = Settings(
        redis_url="redis://localhost",
        auth_token="auth",
        minio_endpoint="localhost:9000",
        minio_access_key="access",
        minio_secret_key="secret",
        minio_result_bucket="results",
        agent_secret_token="agent",
    )

    assert settings.legacy_result_completion_enabled is True
