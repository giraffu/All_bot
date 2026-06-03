from sqlalchemy import select

from src.database.models import SiteNotice
from src.web_api.schemas.site_notice_schema import (
    SiteNoticeItemResponse,
    SiteNoticeResponse,
)


def _normalize_notice_audience(raw_values) -> list[str]:
    if not raw_values:
        return []
    return [str(value) for value in raw_values if str(value).strip()]


def _normalize_notice_title(raw_title) -> str:
    title = str(raw_title or "").strip()
    return title or "站点通知"


def _matches_notice_audience(
    *,
    current_group: str | None,
    current_identity: str | None,
    target_groups: list[str],
    target_identities: list[str],
) -> bool:
    if not target_groups and not target_identities:
        return True

    return (
        (current_group in target_groups if current_group else False)
        or (current_identity in target_identities if current_identity else False)
    )


def _notice_sort_key(notice: SiteNotice) -> tuple[bool, float, float, int]:
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


def _serialize_notice_item(notice: SiteNotice) -> SiteNoticeItemResponse:
    return SiteNoticeItemResponse(
        id=notice.id,
        title=_normalize_notice_title(getattr(notice, "title", "")),
        content=(getattr(notice, "content", "") or "").strip(),
        is_active=bool(getattr(notice, "is_active", False)),
        is_pinned=bool(getattr(notice, "is_pinned", False)),
        published_at=getattr(notice, "published_at", None),
        updated_at=getattr(notice, "updated_at", None),
    )


async def _fetch_all_notices(db) -> list[SiteNotice]:
    result = await db.execute(select(SiteNotice).order_by(SiteNotice.id.asc()))
    scalar_result = result.scalars() if hasattr(result, "scalars") else result
    if hasattr(scalar_result, "all"):
        return list(scalar_result.all())
    return list(getattr(scalar_result, "_value", []) or [])


async def get_active_site_notice_payload(
    *,
    db,
    current_user,
    get_user_detailed_stats_func=None,
) -> SiteNoticeResponse:
    if get_user_detailed_stats_func is None:
        from src.services.permission_service import permission_service

        get_user_detailed_stats_func = permission_service.get_user_detailed_stats_by_user_id

    stats = await get_user_detailed_stats_func(current_user.id)
    current_group = stats.get("group", getattr(current_user, "user_group", None))
    current_identity = stats.get(
        "identity",
        getattr(current_user, "current_identity", None),
    )

    visible_notices: list[SiteNotice] = []
    for notice in await _fetch_all_notices(db):
        if getattr(notice, "deleted_at", None) is not None:
            continue
        if getattr(notice, "published_at", None) is None:
            continue
        if not (getattr(notice, "content", "") or "").strip():
            continue

        target_groups = _normalize_notice_audience(getattr(notice, "target_groups", []))
        target_identities = _normalize_notice_audience(
            getattr(notice, "target_identities", [])
        )
        if _matches_notice_audience(
            current_group=current_group,
            current_identity=current_identity,
            target_groups=target_groups,
            target_identities=target_identities,
        ):
            visible_notices.append(notice)

    sorted_notices = sorted(visible_notices, key=_notice_sort_key, reverse=True)
    featured_notice = next(
        (notice for notice in sorted_notices if bool(getattr(notice, "is_active", False))),
        None,
    )

    return SiteNoticeResponse(
        featured_notice=_serialize_notice_item(featured_notice) if featured_notice else None,
        notices=[_serialize_notice_item(notice) for notice in sorted_notices],
    )
