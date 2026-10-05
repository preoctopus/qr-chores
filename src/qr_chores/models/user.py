"""User account model."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from qr_chores.db import Base

if TYPE_CHECKING:
    from qr_chores.models.chore import Chore


class UserRole(StrEnum):
    parent = "parent"
    child = "child"


def format_display_name(first_name: str, last_name: str) -> str:
    """Build display name from first + last (no email validation)."""
    return f"{first_name.strip()} {last_name.strip()}".strip() or "User"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Username key (stored lowercased). Not validated as an email address.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    # Denormalized for templates / API compatibility; kept in sync with first+last.
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        nullable=False,
    )
    # Primary managing parent. Additional parents are rows in child_parent_links.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    parent: Mapped[Optional["User"]] = relationship(
        remote_side="User.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    children: Mapped[list["User"]] = relationship(
        back_populates="parent",
        foreign_keys=[parent_id],
    )
    assigned_chores: Mapped[list["Chore"]] = relationship(
        back_populates="assignee",
        foreign_keys="Chore.assignee_user_id",
    )

    def sync_display_name(self) -> None:
        self.display_name = format_display_name(self.first_name, self.last_name)


class ChildParentLink(Base):
    """A parent besides ``users.parent_id`` who can see and manage the child.

    The primary ``parent_id`` stays in place. This table is the general
    second-parent (or further parent) link, not a special case for one family.
    """

    __tablename__ = "child_parent_links"
    __table_args__ = (
        CheckConstraint("child_id != parent_id", name="ck_child_parent_links_distinct"),
        Index("ix_child_parent_links_parent_id", "parent_id"),
    )

    child_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    parent_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
