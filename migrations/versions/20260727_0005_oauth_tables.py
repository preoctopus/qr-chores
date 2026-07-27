"""add oauth_clients, oauth_codes, oauth_tokens tables

Revision ID: 20260727_0005
Revises: 20260727_0004
Create Date: 2026-07-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0005"
down_revision: Union[str, Sequence[str], None] = "20260727_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("client_secret", sa.String(length=255), nullable=True),
        sa.Column("client_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("redirect_uris_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("grant_types_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("response_types_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "token_endpoint_auth_method",
            sa.String(length=64),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "oauth_codes",
        sa.Column("code", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column(
            "client_id",
            sa.String(length=255),
            sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.String(length=255), nullable=False),
        sa.Column(
            "code_challenge_method", sa.String(length=32), nullable=False, server_default="S256"
        ),
        sa.Column("scopes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_oauth_codes_user_id", "oauth_codes", ["user_id"])

    op.create_table(
        "oauth_tokens",
        sa.Column("access_token", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("refresh_token", sa.String(length=255), nullable=True),
        sa.Column(
            "client_id",
            sa.String(length=255),
            sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scopes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_oauth_tokens_user_id", "oauth_tokens", ["user_id"])
    op.create_index("ix_oauth_tokens_refresh_token", "oauth_tokens", ["refresh_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_oauth_tokens_refresh_token", table_name="oauth_tokens")
    op.drop_index("ix_oauth_tokens_user_id", table_name="oauth_tokens")
    op.drop_table("oauth_tokens")
    op.drop_index("ix_oauth_codes_user_id", table_name="oauth_codes")
    op.drop_table("oauth_codes")
    op.drop_table("oauth_clients")
