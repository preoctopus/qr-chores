"""SQLAlchemy models for OAuth 2.1 metadata, codes, and tokens."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from qr_chores.db import Base


class OAuthClient(Base):
    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    client_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    redirect_uris_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    grant_types_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    response_types_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    token_endpoint_auth_method: Mapped[str] = mapped_column(
        String(64), nullable=False, default="none"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class OAuthCode(Base):
    __tablename__ = "oauth_codes"

    code: Mapped[str] = mapped_column(String(255), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(255), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(32), nullable=False, default="S256")
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    access_token: Mapped[str] = mapped_column(String(255), primary_key=True)
    refresh_token: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    client_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
