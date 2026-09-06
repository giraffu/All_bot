from src.database.models import GalleryPost, User


def test_gallery_post_history_relationship():
    # Check if uselist=True is configured for histories to avoid warning
    assert GalleryPost.histories.property.uselist is True
    primaryjoin = str(GalleryPost.histories.property.primaryjoin).lower()
    assert "gallery_posts.task_id = history.task_id" in primaryjoin
    assert "gallery_posts.user_id = history.user_id" in primaryjoin


def test_gallery_post_has_explicit_history_link():
    assert GalleryPost.history_id.property.columns[0].nullable is True
    assert GalleryPost.history.property.uselist is False


def test_user_history_relationship():
    assert User.history.property.uselist is True
