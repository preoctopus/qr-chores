"""multi-child: names, parent_id, chore assignee

Revision ID: 20260727_0004
Revises: 20260725_0003
Create Date: 2026-07-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0004"
down_revision: Union[str, Sequence[str], None] = "20260725_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("first_name", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("last_name", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch.create_index("ix_users_parent_id", ["parent_id"])
        batch.create_foreign_key(
            "fk_users_parent_id_users",
            "users",
            ["parent_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Backfill names from display_name (first word / rest).
    conn = op.get_bind()
    users = conn.execute(sa.text("SELECT id, display_name FROM users")).fetchall()
    for row in users:
        uid, display = row[0], (row[1] or "").strip()
        parts = display.split(None, 1)
        first = parts[0] if parts else "User"
        last = parts[1] if len(parts) > 1 else ""
        conn.execute(
            sa.text(
                "UPDATE users SET first_name = :f, last_name = :l WHERE id = :id"
            ),
            {"f": first, "l": last, "id": uid},
        )

    with op.batch_alter_table("users") as batch:
        batch.alter_column("first_name", existing_type=sa.String(length=80), nullable=False)
        batch.alter_column("last_name", existing_type=sa.String(length=80), nullable=False)

    # Link the seeded child to the first parent when both exist.
    conn.execute(
        sa.text(
            """
            UPDATE users
            SET parent_id = (
                SELECT p.id FROM users p WHERE p.role = 'parent' ORDER BY p.id LIMIT 1
            )
            WHERE role = 'child' AND parent_id IS NULL
            """
        )
    )

    with op.batch_alter_table("chores") as batch:
        batch.add_column(sa.Column("assignee_user_id", sa.Integer(), nullable=True))
        batch.create_index("ix_chores_assignee_user_id", ["assignee_user_id"])
        batch.create_foreign_key(
            "fk_chores_assignee_user_id_users",
            "users",
            ["assignee_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Assign existing chores to the first child (single-family upgrade path).
    conn.execute(
        sa.text(
            """
            UPDATE chores
            SET assignee_user_id = (
                SELECT c.id FROM users c WHERE c.role = 'child' ORDER BY c.id LIMIT 1
            )
            WHERE assignee_user_id IS NULL
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("chores") as batch:
        batch.drop_constraint("fk_chores_assignee_user_id_users", type_="foreignkey")
        batch.drop_index("ix_chores_assignee_user_id")
        batch.drop_column("assignee_user_id")

    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_parent_id_users", type_="foreignkey")
        batch.drop_index("ix_users_parent_id")
        batch.drop_column("parent_id")
        batch.drop_column("last_name")
        batch.drop_column("first_name")
