"""Points ledger and achievements."""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from qr_chores.db import Base


class CriteriaType(str, enum.Enum):
    total_completions = "total_completions"
    complete_on_time_count = "complete_on_time_count"
    complete_early_count = "complete_early_count"
    photo_completions = "photo_completions"
    streak_days = "streak_days"


class PointLedger(Base):
    __tablename__ = "point_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Achievement(Base):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    icon_key: Mapped[str] = mapped_column(String(40), nullable=False, default="star")
    criteria_type: Mapped[CriteriaType] = mapped_column(
        Enum(CriteriaType, name="criteria_type", native_enum=False),
        nullable=False,
    )
    # JSON object, e.g. {"count": 5} or {"days": 3}
    criteria_json: Mapped[str] = mapped_column(String(255), nullable=False, default="{}")
    points_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    unlocks: Mapped[list["UserAchievement"]] = relationship(back_populates="achievement")


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    achievement_id: Mapped[int] = mapped_column(
        ForeignKey("achievements.id"), nullable=False, index=True
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    achievement: Mapped[Achievement] = relationship(back_populates="unlocks")


class AppSetting(Base):
    """Simple key/value settings (timing bonuses, etc.)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
