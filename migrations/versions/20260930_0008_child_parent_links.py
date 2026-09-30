"""additional parents via child_parent_links

Revision ID: 20260930_0008
Revises: 20260729_0007
Create Date: 2026-09-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260930_0008"
down_revision: Union[str, Sequence[str], None] = "20260729_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "child_parent_links",
        sa.Column("child_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("child_id != parent_id", name="ck_child_parent_links_distinct"),
        sa.ForeignKeyConstraint(["child_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("child_id", "parent_id"),
    )
    op.create_index(
        "ix_child_parent_links_parent_id",
        "child_parent_links",
        ["parent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_child_parent_links_parent_id", table_name="child_parent_links")
    op.drop_table("child_parent_links")
