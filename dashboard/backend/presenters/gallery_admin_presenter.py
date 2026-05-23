def build_dashboard_comment_item(comment) -> dict:
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "post_task_id": comment.post.task_id if comment.post else None,
        "post_is_active": comment.post.is_active if comment.post else None,
        "user_id": comment.user_id,
        "author_name": (
            comment.user.full_name
            or comment.user.username
            or f"User {comment.user_id}"
        )
        if comment.user
        else f"User {comment.user_id}",
        "content": comment.content,
        "is_active": comment.is_active,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


def build_gallery_media_url(*, output_file: str | None, task_id: str, storage_service) -> str | None:
    if not output_file:
        return None

    if hasattr(storage_service, "get_file_url"):
        return storage_service.get_file_url(output_file)
    if hasattr(storage_service, "get_presigned_url"):
        return storage_service.get_presigned_url(output_file)
    if hasattr(storage_service, "get_presigned_download_url"):
        return storage_service.get_presigned_download_url(output_file)
    return f"/api/history/media/{task_id}"


def build_gallery_post_item(*, post, storage_service) -> dict:
    first_history = post.histories[0] if post.histories else None
    output_file = first_history.output_file if first_history else None
    return {
        "id": post.id,
        "task_id": post.task_id,
        "user_id": post.user_id,
        "username": post.user.username if post.user else None,
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
