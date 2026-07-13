from dashboard.backend.presenters.storage_presenter_utils import build_storage_url


def build_dashboard_comment_item(comment) -> dict:
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "post_task_id": comment.post.task_id if comment.post else None,
        "post_is_active": comment.post.is_active if comment.post else None,
        "user_id": comment.user_id,
        "author_name": (
            comment.user.full_name or comment.user.username or f"User {comment.user_id}"
        )
        if comment.user
        else f"User {comment.user_id}",
        "content": comment.content,
        "is_active": comment.is_active,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


def _build_user_display_name(user, user_id) -> str:
    if user:
        return user.full_name or user.username or f"User {user_id}"
    if user_id:
        return f"User {user_id}"
    return "Unknown"


def build_gallery_media_url(
    *, output_file: str | None, task_id: str, storage_service
) -> str | None:
    return build_storage_url(
        storage_service=storage_service,
        object_name=output_file,
        fallback_url=f"/api/history/media/{task_id}" if output_file else None,
    )


def build_gallery_post_item(*, post, storage_service) -> dict:
    first_history = post.histories[0] if post.histories else None
    output_file = first_history.output_file if first_history else None
    author_full_name = getattr(post.user, "full_name", None) if post.user else None
    author_username = getattr(post.user, "username", None) if post.user else None
    author_name = author_full_name or author_username or f"User {post.user_id}"
    return {
        "id": post.id,
        "task_id": post.task_id,
        "user_id": post.user_id,
        "username": author_username,
        "full_name": author_full_name,
        "author_name": author_name,
        "is_submission_banned": bool(getattr(post.user, "is_submission_banned", False))
        if post.user
        else False,
        "submission_ban_reason": getattr(post.user, "submission_ban_reason", None)
        if post.user
        else None,
        "media_type": post.media_type,
        "task_type": first_history.type if first_history else "unknown",
        "width": post.width,
        "height": post.height,
        "duration": post.duration,
        "tags": post.tags,
        "likes_count": post.likes_count,
        "dislikes_count": post.dislikes_count,
        "applied_count": post.applied_count,
        "comments_count": post.comments_count,
        "is_active": post.is_active,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "media_url": build_gallery_media_url(
            output_file=output_file,
            task_id=post.task_id,
            storage_service=storage_service,
        ),
        "prompt": first_history.prompt if first_history else None,
    }


def build_dashboard_report_item(*, report, storage_service) -> dict:
    post = report.post
    first_history = post.histories[0] if post and post.histories else None
    output_file = first_history.output_file if first_history else None
    task_id = report.post_task_id or (post.task_id if post else None)
    return {
        "id": report.id,
        "post_id": report.post_id,
        "post_task_id": task_id,
        "post_is_active": post.is_active if post else None,
        "post_author_user_id": report.post_author_user_id,
        "post_author_name": _build_user_display_name(
            report.post_author,
            report.post_author_user_id,
        ),
        "reporter_user_id": report.reporter_user_id,
        "reporter_name": _build_user_display_name(
            report.reporter,
            report.reporter_user_id,
        ),
        "reason": report.reason,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "resolved_at": report.resolved_at.isoformat() if report.resolved_at else None,
        "resolution_action": report.resolution_action,
        "media_type": post.media_type if post else None,
        "media_url": build_gallery_media_url(
            output_file=output_file,
            task_id=task_id,
            storage_service=storage_service,
        )
        if task_id
        else None,
        "prompt": first_history.prompt if first_history else None,
    }
