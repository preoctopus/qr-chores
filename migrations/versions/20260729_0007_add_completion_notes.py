"""add notes column to chore_completions table

Revision ID: 20260729_0007
Revises: 20260728_0006
Create Date: 2026-07-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0007"
down_revision: Union[str, Sequence[str], None] = "20260728_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chore_completions",
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("chore_completions", "notes")
