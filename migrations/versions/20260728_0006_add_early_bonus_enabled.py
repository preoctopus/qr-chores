"""add early_bonus_enabled column to chores table

Revision ID: 20260728_0006
Revises: 20260727_0005
Create Date: 2026-07-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0006"
down_revision: Union[str, Sequence[str], None] = "20260727_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chores",
        sa.Column(
            "early_bonus_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("chores", "early_bonus_enabled")
