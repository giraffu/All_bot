from src.database.models import GalleryPost, User, History

def test_gallery_post_history_relationship():
    # Check if uselist=True is configured for histories to avoid warning
    assert GalleryPost.histories.property.uselist is True

def test_user_history_relationship():
    assert User.history.property.uselist is True
