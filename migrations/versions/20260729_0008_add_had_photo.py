"""add had_photo column for photo reaping without losing stats

Revision ID: 20260729_0008
Revises: 20260729_0007
Create Date: 2026-07-29

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0008"
down_revision: Union[str, Sequence[str], None] = "20260729_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chore_completions",
        sa.Column(
            "had_photo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Backfill: any completion that still has a storage key had a photo.
    op.execute(
        sa.text(
            "UPDATE chore_completions SET had_photo = true "
            "WHERE photo_object_key IS NOT NULL AND photo_object_key != ''"
        )
    )


def downgrade() -> None:
    op.drop_column("chore_completions", "had_photo")
