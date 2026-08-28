from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_asyncpg_dsn(database_url: str) -> str:
    """Normalize SQLAlchemy/managed-Postgres URLs for raw asyncpg clients."""

    parsed = urlsplit(
        database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    )
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        query.append(("sslmode" if key == "ssl" else key, value))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )
