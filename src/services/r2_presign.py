from src.services.storage import storage


def build_r2_presigned_url(
    object_key: str,
    *,
    expires_hours: float = 1.0,
) -> str:
    r2_client = getattr(storage, "r2_client", None)
    r2_bucket = getattr(storage, "r2_bucket", None)
    if not r2_client or not r2_bucket:
        return ""
    try:
        return (
            r2_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": r2_bucket, "Key": object_key},
                ExpiresIn=int(expires_hours * 3600),
            )
            or ""
        )
    except Exception:
        return ""
