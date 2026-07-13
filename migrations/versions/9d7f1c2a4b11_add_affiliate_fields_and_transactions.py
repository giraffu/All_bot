"""add affiliate fields and transactions

Revision ID: 9d7f1c2a4b11
Revises: 32affcec25b0
Create Date: 2026-05-12 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d7f1c2a4b11"
down_revision: Union[str, Sequence[str], None] = "32affcec25b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _print_scalar(bind, label: str, sql: str) -> None:
    value = bind.execute(sa.text(sql)).scalar_one()
    print(f"[affiliate migration] {label}: {value}")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "orders",
        sa.Column(
            "commission_usdt",
            sa.DECIMAL(precision=10, scale=4),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "orders", sa.Column("payment_channel", sa.String(length=20), nullable=True)
    )
    op.add_column("orders", sa.Column("paid_at", sa.DateTime(), nullable=True))
    op.create_index(
        op.f("ix_orders_payment_channel"),
        "orders",
        ["payment_channel"],
        unique=False,
    )
    op.create_index(op.f("ix_orders_paid_at"), "orders", ["paid_at"], unique=False)

    op.create_table(
        "affiliate_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount_usdt", sa.DECIMAL(precision=10, scale=4), nullable=False),
        sa.Column("transaction_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=True,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_affiliate_transactions_user_id"),
        "affiliate_transactions",
        ["user_id"],
        unique=False,
    )

    bind = op.get_bind()

    # 1. 保守回填 payment_channel
    bind.execute(
        sa.text(
            """
            UPDATE orders
            SET payment_channel =
                CASE
                    WHEN order_id LIKE 'RMB_%' OR order_id LIKE 'WEB_%' THEN 'RMB'
                    WHEN order_id LIKE 'ORDER:%' AND LENGTH(COALESCE(tx_hash, '')) > 50 THEN 'XTR'
                    WHEN order_id LIKE 'ORDER:%' AND LENGTH(COALESCE(tx_hash, '')) <= 50 THEN 'TON'
                    ELSE NULL
                END
            WHERE payment_channel IS NULL
            """
        )
    )

    # 2. 回填 paid_at
    bind.execute(
        sa.text(
            """
            UPDATE orders
            SET paid_at = created_at
            WHERE status = 'SUCCESS'
              AND payment_channel IN ('TON', 'XTR')
              AND paid_at IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE orders
            SET paid_at = updated_at
            WHERE status = 'SUCCESS'
              AND payment_channel = 'RMB'
              AND tx_hash IS NOT NULL
              AND tx_hash <> order_id
              AND paid_at IS NULL
            """
        )
    )

    # 3. 固化首单佣金，仅处理 paid_at 可判定的订单
    bind.execute(
        sa.text(
            """
            WITH first_paid_orders AS (
                SELECT
                    o.id AS order_pk,
                    o.telegram_id,
                    o.final_price,
                    o.payment_channel,
                    ROW_NUMBER() OVER (
                        PARTITION BY o.telegram_id
                        ORDER BY o.paid_at ASC, o.id ASC
                    ) AS rn
                FROM orders o
                JOIN referrals r ON r.invitee_id = o.telegram_id
                WHERE
                    o.status = 'SUCCESS'
                    AND o.final_price > 0
                    AND o.paid_at IS NOT NULL
                    AND o.payment_channel IN ('RMB', 'TON', 'XTR')
            )
            UPDATE orders
            SET commission_usdt =
                CASE
                    WHEN f.payment_channel = 'RMB' THEN ROUND((f.final_price * (1.0 / 6.7) * 0.10)::numeric, 4)
                    WHEN f.payment_channel = 'TON' THEN ROUND((f.final_price * 1.4 * 0.10)::numeric, 4)
                    WHEN f.payment_channel = 'XTR' THEN ROUND((f.final_price * 0.013 * 0.10)::numeric, 4)
                    ELSE 0
                END
            FROM first_paid_orders f
            WHERE orders.id = f.order_pk
              AND f.rn = 1
            """
        )
    )

    _print_scalar(
        bind,
        "orders with payment_channel = RMB",
        "SELECT COUNT(*) FROM orders WHERE payment_channel = 'RMB'",
    )
    _print_scalar(
        bind,
        "orders with payment_channel = TON",
        "SELECT COUNT(*) FROM orders WHERE payment_channel = 'TON'",
    )
    _print_scalar(
        bind,
        "orders with payment_channel = XTR",
        "SELECT COUNT(*) FROM orders WHERE payment_channel = 'XTR'",
    )
    _print_scalar(
        bind,
        "orders still missing payment_channel",
        "SELECT COUNT(*) FROM orders WHERE payment_channel IS NULL",
    )
    _print_scalar(
        bind,
        "orders with paid_at",
        "SELECT COUNT(*) FROM orders WHERE paid_at IS NOT NULL",
    )
    _print_scalar(
        bind,
        "successful orders missing paid_at",
        "SELECT COUNT(*) FROM orders WHERE status = 'SUCCESS' AND paid_at IS NULL",
    )
    _print_scalar(
        bind,
        "orders with commission_usdt > 0",
        "SELECT COUNT(*) FROM orders WHERE commission_usdt > 0",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_affiliate_transactions_user_id"), table_name="affiliate_transactions"
    )
    op.drop_table("affiliate_transactions")
    op.drop_index(op.f("ix_orders_paid_at"), table_name="orders")
    op.drop_index(op.f("ix_orders_payment_channel"), table_name="orders")
    op.drop_column("orders", "paid_at")
    op.drop_column("orders", "payment_channel")
    op.drop_column("orders", "commission_usdt")
