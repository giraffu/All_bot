from minio import Minio


DEFAULT_MINIO_BUCKET_NAMES = ("comfyui-temp", "bot-data")


def apply_default_minio_region_map(
    client: Minio,
    *,
    bucket_names: list[str],
    region: str = "us-east-1",
) -> Minio:
    for bucket_name in bucket_names:
        if bucket_name:
            client._region_map[bucket_name] = region
    return client


def build_configured_bucket_names(*bucket_names: str | None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for bucket_name in (*bucket_names, *DEFAULT_MINIO_BUCKET_NAMES):
        if bucket_name and bucket_name not in seen:
            names.append(bucket_name)
            seen.add(bucket_name)
    return names


def build_minio_client(
    *,
    endpoint: str,
    access_key: str,
    secret_key: str,
    secure: bool,
    bucket_names: list[str] | None = None,
    region: str = "us-east-1",
    http_client=None,
) -> Minio:
    client = Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        region=region,
        http_client=http_client,
    )
    if bucket_names:
        apply_default_minio_region_map(
            client,
            bucket_names=bucket_names,
            region=region,
        )
    return client


def build_public_minio_client(
    *,
    public_url: str,
    access_key: str,
    secret_key: str,
    bucket_names: list[str] | None = None,
    region: str = "us-east-1",
    http_client=None,
) -> Minio:
    public_host = public_url.replace("https://", "").replace("http://", "")
    secure = public_url.startswith("https")
    return build_minio_client(
        endpoint=public_host,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        bucket_names=bucket_names,
        region=region,
        http_client=http_client,
    )


def ensure_bucket_exists(
    client: Minio,
    *,
    bucket_name: str | None,
    logger,
    label: str,
) -> None:
    if not bucket_name:
        return

    if client.bucket_exists(bucket_name):
        return

    try:
        client.make_bucket(bucket_name)
        logger.info("Created MinIO %s bucket: %s", label, bucket_name)
    except Exception as exc:
        logger.error("Failed to create %s bucket %s: %s", label, bucket_name, exc)
