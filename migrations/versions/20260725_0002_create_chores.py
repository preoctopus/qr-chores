"""create chores and completions

Revision ID: 20260725_0002
Revises: 20260725_0001
Create Date: 2026-07-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0002"
down_revision: Union[str, Sequence[str], None] = "20260725_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("qr_token", sa.String(length=64), nullable=False),
        sa.Column("due_time", sa.Time(), nullable=False),
        sa.Column("schedule_days", sa.String(length=7), nullable=False),
        sa.Column(
            "photo_policy",
            sa.Enum("required", "optional", "none", name="photo_policy", native_enum=False),
            nullable=False,
        ),
        sa.Column("base_points", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chores_qr_token"), "chores", ["qr_token"], unique=True)

    op.create_table(
        "chore_completions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chore_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "timing",
            sa.Enum("early", "on_time", "late", name="timing_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("photo_object_key", sa.String(length=512), nullable=True),
        sa.Column("points_awarded", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chore_id"], ["chores.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chore_id", "local_date", name="uq_chore_completion_day"),
    )
    op.create_index(op.f("ix_chore_completions_chore_id"), "chore_completions", ["chore_id"])
    op.create_index(op.f("ix_chore_completions_user_id"), "chore_completions", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_chore_completions_user_id"), table_name="chore_completions")
    op.drop_index(op.f("ix_chore_completions_chore_id"), table_name="chore_completions")
    op.drop_table("chore_completions")
    op.drop_index(op.f("ix_chores_qr_token"), table_name="chores")
    op.drop_table("chores")
