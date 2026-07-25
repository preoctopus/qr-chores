"""Chore and completion models."""

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from qr_chores.db import Base


class PhotoPolicy(str, enum.Enum):
    required = "required"
    optional = "optional"
    none = "none"


class TimingStatus(str, enum.Enum):
    early = "early"
    on_time = "on_time"
    late = "late"


# Python weekday(): Monday=0 … Sunday=6
ALL_DAYS = "0123456"


class Chore(Base):
    __tablename__ = "chores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    due_time: Mapped[time] = mapped_column(Time, nullable=False)
    # Concatenated weekday digits, e.g. "0123456" daily, "01234" weekdays
    schedule_days: Mapped[str] = mapped_column(String(7), nullable=False, default=ALL_DAYS)
    photo_policy: Mapped[PhotoPolicy] = mapped_column(
        Enum(PhotoPolicy, name="photo_policy", native_enum=False),
        nullable=False,
        default=PhotoPolicy.none,
    )
    base_points: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    completions: Mapped[list["ChoreCompletion"]] = relationship(back_populates="chore")


class ChoreCompletion(Base):
    __tablename__ = "chore_completions"
    __table_args__ = (
        UniqueConstraint("chore_id", "local_date", name="uq_chore_completion_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chore_id: Mapped[int] = mapped_column(ForeignKey("chores.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timing: Mapped[TimingStatus] = mapped_column(
        Enum(TimingStatus, name="timing_status", native_enum=False),
        nullable=False,
    )
    photo_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    chore: Mapped[Chore] = relationship(back_populates="completions")
