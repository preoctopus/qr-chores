"""merge heads: had_photo + child_parent_links

Revision ID: 20261005_0009
Revises: 20260729_0008, 20260930_0008
Create Date: 2026-10-05

"""

from typing import Sequence, Union

revision: str = "20261005_0009"
down_revision: Union[str, Sequence[str], None] = ("20260729_0008", "20260930_0008")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
