"""points ledger and achievements

Revision ID: 20260725_0003
Revises: 20260725_0002
Create Date: 2026-07-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0003"
down_revision: Union[str, Sequence[str], None] = "20260725_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "point_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("ref_type", sa.String(length=40), nullable=True),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_point_ledger_user_id"), "point_ledger", ["user_id"])

    op.create_table(
        "achievements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon_key", sa.String(length=40), nullable=False),
        sa.Column(
            "criteria_type",
            sa.Enum(
                "total_completions",
                "complete_on_time_count",
                "complete_early_count",
                "photo_completions",
                "streak_days",
                name="criteria_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("criteria_json", sa.String(length=255), nullable=False),
        sa.Column("points_reward", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("achievement_id", sa.Integer(), nullable=False),
        sa.Column(
            "unlocked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["achievement_id"], ["achievements.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )
    op.create_index(op.f("ix_user_achievements_user_id"), "user_achievements", ["user_id"])
    op.create_index(
        op.f("ix_user_achievements_achievement_id"), "user_achievements", ["achievement_id"]
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index(op.f("ix_user_achievements_achievement_id"), table_name="user_achievements")
    op.drop_index(op.f("ix_user_achievements_user_id"), table_name="user_achievements")
    op.drop_table("user_achievements")
    op.drop_table("achievements")
    op.drop_index(op.f("ix_point_ledger_user_id"), table_name="point_ledger")
    op.drop_table("point_ledger")
