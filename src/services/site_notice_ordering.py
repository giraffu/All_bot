from typing import Any


def notice_sort_key(notice: Any) -> tuple[bool, float, float, int]:
    published_at = getattr(notice, "published_at", None)
    updated_at = getattr(notice, "updated_at", None)
    created_at = getattr(notice, "created_at", None)
    published_ts = published_at.timestamp() if published_at else 0.0
    updated_source = updated_at or created_at or published_at
    updated_ts = updated_source.timestamp() if updated_source else 0.0
    return (
        bool(getattr(notice, "is_pinned", False)),
        published_ts,
        updated_ts,
        int(getattr(notice, "id", 0) or 0),
    )
