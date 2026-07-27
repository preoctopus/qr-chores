"""QR Chores typed HTTP client and FastMCP server."""

from qr_chores_client.client import QrChoresClient
from qr_chores_client.errors import (
    ApiError,
    AuthError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from qr_chores_client.models import (
    AchievementAdmin,
    AchievementCreate,
    AchievementsResponse,
    AchievementUpdate,
    Chore,
    ChoreConfirm,
    ChoreCreate,
    ChoreDeleteResponse,
    ChoreListResponse,
    ChoreUpdate,
    CompleteResponse,
    HistoryResponse,
    HomeResponse,
    QrInfo,
    RewardsResponse,
    TimingBonuses,
    TodayResponse,
    TokenResponse,
    User,
)
from qr_chores_client.sync_client import SyncQrChoresClient

__all__ = [
    "AchievementAdmin",
    "AchievementCreate",
    "AchievementUpdate",
    "AchievementsResponse",
    "ApiError",
    "AuthError",
    "Chore",
    "ChoreConfirm",
    "ChoreCreate",
    "ChoreDeleteResponse",
    "ChoreListResponse",
    "ChoreUpdate",
    "CompleteResponse",
    "DomainError",
    "ForbiddenError",
    "HistoryResponse",
    "HomeResponse",
    "NotFoundError",
    "QrChoresClient",
    "QrInfo",
    "RewardsResponse",
    "SyncQrChoresClient",
    "TimingBonuses",
    "TodayResponse",
    "TokenResponse",
    "User",
    "ValidationError",
]

__version__ = "0.1.0"
