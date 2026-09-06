import pytest

from src.database.models import GalleryPost, History
from src.services.gallery_history_link import load_gallery_history_map


class _Result:
    def __init__(self, values):
        self.values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self.values)


class _Session:
    def __init__(self, values):
        self.values = values

    async def execute(self, _statement):
        return _Result(self.values)


@pytest.mark.asyncio
async def test_bulk_history_map_never_crosses_users_with_same_task_id():
    posts = [
        GalleryPost(id=1, task_id="shared", user_id=10),
        GalleryPost(id=2, task_id="shared", user_id=20),
    ]
    histories = [
        History(id=100, task_id="shared", user_id=10, prompt="owner-10"),
        History(id=200, task_id="shared", user_id=20, prompt="owner-20"),
    ]

    history_map = await load_gallery_history_map(
        session=_Session(histories),
        posts=posts,
    )

    assert history_map[1].prompt == "owner-10"
    assert history_map[2].prompt == "owner-20"


@pytest.mark.asyncio
async def test_bulk_history_map_prefers_explicit_history_id():
    post = GalleryPost(id=1, task_id="shared", user_id=10, history_id=101)
    histories = [
        History(id=100, task_id="shared", user_id=10, prompt="legacy"),
        History(id=101, task_id="shared", user_id=10, prompt="explicit"),
    ]

    history_map = await load_gallery_history_map(
        session=_Session(histories),
        posts=[post],
    )

    assert history_map[1].prompt == "explicit"


@pytest.mark.asyncio
async def test_bulk_history_map_rejects_explicit_history_owned_by_another_user():
    post = GalleryPost(id=1, task_id="shared", user_id=10, history_id=200)
    histories = [
        History(id=200, task_id="shared", user_id=20, prompt="other-owner"),
    ]

    history_map = await load_gallery_history_map(
        session=_Session(histories),
        posts=[post],
    )

    assert history_map == {}
