"""harden gallery uniqueness after consistency repair

Revision ID: d1e2f3a4b5c6
Revises: c8e1f4a6b2d9
"""

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "c8e1f4a6b2d9"
branch_labels = None
depends_on = None


_PREFLIGHT_SQL = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM user_interactions
        WHERE user_id IS NULL OR post_id IS NULL OR action_type IS NULL
           OR action_type NOT IN ('like', 'dislike', 'apply')
    ) THEN
        RAISE EXCEPTION 'gallery consistency repair required: invalid interaction';
    END IF;
    IF EXISTS (
        SELECT 1 FROM gallery_posts
        GROUP BY task_id, user_id HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'gallery consistency repair required: duplicate posts';
    END IF;
    IF EXISTS (
        SELECT 1 FROM user_interactions
        WHERE action_type = 'apply'
        GROUP BY user_id, post_id HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'gallery consistency repair required: duplicate apply';
    END IF;
    IF EXISTS (
        SELECT 1 FROM user_interactions
        WHERE action_type IN ('like', 'dislike')
        GROUP BY user_id, post_id HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'gallery consistency repair required: duplicate reaction';
    END IF;
END $$;
"""


def _create_indexes(*, concurrently: bool) -> None:
    kwargs = {"postgresql_concurrently": True} if concurrently else {}
    op.create_index(
        "uq_gallery_posts_task_user",
        "gallery_posts",
        ["task_id", "user_id"],
        unique=True,
        **kwargs,
    )
    op.create_index(
        "uq_user_interactions_apply",
        "user_interactions",
        ["user_id", "post_id"],
        unique=True,
        postgresql_where=sa.text("action_type = 'apply'"),
        **kwargs,
    )
    op.create_index(
        "uq_user_interactions_reaction",
        "user_interactions",
        ["user_id", "post_id"],
        unique=True,
        postgresql_where=sa.text("action_type IN ('like', 'dislike')"),
        **kwargs,
    )


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(sa.text(_PREFLIGHT_SQL))
            _create_indexes(concurrently=True)
        return
    _create_indexes(concurrently=False)


def downgrade() -> None:
    concurrently = op.get_bind().dialect.name == "postgresql"

    def _drop() -> None:
        kwargs = {"postgresql_concurrently": True} if concurrently else {}
        op.drop_index(
            "uq_user_interactions_reaction",
            table_name="user_interactions",
            **kwargs,
        )
        op.drop_index(
            "uq_user_interactions_apply",
            table_name="user_interactions",
            **kwargs,
        )
        op.drop_index(
            "uq_gallery_posts_task_user",
            table_name="gallery_posts",
            **kwargs,
        )

    if concurrently:
        with op.get_context().autocommit_block():
            _drop()
        return
    _drop()
