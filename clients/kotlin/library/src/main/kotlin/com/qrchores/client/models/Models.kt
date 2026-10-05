package com.qrchores.client.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

// --- Auth ---

@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
)

@Serializable
data class User(
    val id: Int,
    val email: String,
    @SerialName("display_name") val displayName: String,
    val role: String,
    @SerialName("points_balance") val pointsBalance: Int = 0,
    @SerialName("first_name") val firstName: String = "",
    @SerialName("last_name") val lastName: String = "",
    @SerialName("parent_id") val parentId: Int? = null,
    @SerialName("is_active") val isActive: Boolean = true,
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
    @SerialName("expires_in") val expiresIn: Int,
    val user: User,
)

// --- Children ---

@Serializable
data class ChildListResponse(
    val children: List<User>,
)

@Serializable
data class ChildCreate(
    val email: String,
    val password: String,
    @SerialName("first_name") val firstName: String,
    @SerialName("last_name") val lastName: String,
)

@Serializable
data class ChildUpdate(
    val email: String? = null,
    val password: String? = null,
    @SerialName("first_name") val firstName: String? = null,
    @SerialName("last_name") val lastName: String? = null,
    @SerialName("is_active") val isActive: Boolean? = null,
)

// --- Chores ---

@Serializable
data class Chore(
    val id: Int,
    val title: String,
    val description: String? = null,
    @SerialName("qr_token") val qrToken: String,
    @SerialName("due_time") val dueTime: String,
    @SerialName("schedule_days") val scheduleDays: String,
    @SerialName("photo_policy") val photoPolicy: String,
    @SerialName("base_points") val basePoints: Int,
    @SerialName("early_bonus_enabled") val earlyBonusEnabled: Boolean = true,
    @SerialName("is_active") val isActive: Boolean,
)

@Serializable
data class Completion(
    val id: Int,
    @SerialName("local_date") val localDate: String,
    @SerialName("completed_at") val completedAt: String,
    val timing: String,
    @SerialName("points_awarded") val pointsAwarded: Int,
    @SerialName("has_photo") val hasPhoto: Boolean,
    val notes: String? = null,
)

@Serializable
data class BoardItem(
    val chore: Chore,
    val done: Boolean,
    @SerialName("status_label") val statusLabel: String,
    @SerialName("status_kind") val statusKind: String,
    @SerialName("is_late_pending") val isLatePending: Boolean,
    val timing: String? = null,
    val completion: Completion? = null,
)

@Serializable
data class Unlock(
    val id: Int,
    val title: String,
    val description: String? = null,
    @SerialName("icon_key") val iconKey: String,
    @SerialName("points_reward") val pointsReward: Int,
    @SerialName("unlocked_at") val unlockedAt: String? = null,
)

@Serializable
data class HomeResponse(
    @SerialName("local_date") val localDate: String,
    @SerialName("points_balance") val pointsBalance: Int,
    @SerialName("points_today") val pointsToday: Int,
    @SerialName("done_count") val doneCount: Int,
    @SerialName("total_count") val totalCount: Int,
    val board: List<BoardItem> = emptyList(),
    @SerialName("recent_unlocks") val recentUnlocks: List<Unlock> = emptyList(),
)

@Serializable
data class ChoreConfirm(
    val chore: Chore,
    @SerialName("scheduled_today") val scheduledToday: Boolean,
    @SerialName("already_done") val alreadyDone: Boolean,
    @SerialName("is_late_pending") val isLatePending: Boolean,
    val completion: Completion? = null,
)

@Serializable
data class PointsBreakdown(
    val base: Int,
    @SerialName("timing_bonus") val timingBonus: Int,
    @SerialName("achievement_points") val achievementPoints: Int,
    val total: Int,
)

@Serializable
data class CompleteResponse(
    @SerialName("already_done") val alreadyDone: Boolean,
    val chore: Chore,
    val completion: Completion,
    val points: PointsBreakdown,
    val unlocks: List<Unlock> = emptyList(),
)

@Serializable
data class AchievementProgress(
    val id: Int,
    val title: String,
    val description: String? = null,
    @SerialName("icon_key") val iconKey: String,
    @SerialName("criteria_type") val criteriaType: String,
    @SerialName("points_reward") val pointsReward: Int,
    val unlocked: Boolean,
    val progress: Int,
    val threshold: Int,
    val percent: Int,
)

@Serializable
data class AchievementsResponse(
    @SerialName("points_balance") val pointsBalance: Int,
    @SerialName("unlocked_count") val unlockedCount: Int,
    val achievements: List<AchievementProgress> = emptyList(),
)

// --- Parent board / history ---

@Serializable
data class TodaySummary(
    val total: Int,
    val done: Int,
    val pending: Int,
    val overdue: Int,
    @SerialName("done_late") val doneLate: Int,
    @SerialName("points_today") val pointsToday: Int,
)

@Serializable
data class ChildDayGroup(
    @SerialName("child_id") val childId: Int,
    @SerialName("child_name") val childName: String,
    val done: Int,
    val total: Int,
    val overdue: Int,
    @SerialName("points_today") val pointsToday: Int,
    val items: List<BoardItem> = emptyList(),
)

@Serializable
data class TodayResponse(
    @SerialName("local_date") val localDate: String,
    val board: List<BoardItem> = emptyList(),
    val summary: TodaySummary? = null,
    val children: List<ChildDayGroup> = emptyList(),
)

@Serializable
data class HistoryItem(
    val completion: Completion,
    @SerialName("chore_id") val choreId: Int,
    @SerialName("chore_title") val choreTitle: String,
    @SerialName("user_id") val userId: Int,
)

@Serializable
data class HistoryStats(
    @SerialName("total_completions") val totalCompletions: Int,
    @SerialName("completions_this_week") val completionsThisWeek: Int,
    @SerialName("on_time_count") val onTimeCount: Int,
    @SerialName("on_time_rate") val onTimeRate: Double,
    @SerialName("total_points") val totalPoints: Int,
    @SerialName("current_streak") val currentStreak: Int,
)

@Serializable
data class HistoryPagination(
    val page: Int,
    val limit: Int,
    @SerialName("total_count") val totalCount: Int,
    @SerialName("total_pages") val totalPages: Int,
    @SerialName("has_next") val hasNext: Boolean,
    @SerialName("has_prev") val hasPrev: Boolean,
)

@Serializable
data class HistoryResponse(
    val items: List<HistoryItem> = emptyList(),
    val limit: Int,
    val stats: HistoryStats? = null,
    val pagination: HistoryPagination? = null,
)

@Serializable
data class MissedChore(
    @SerialName("chore_id") val choreId: Int,
    @SerialName("chore_title") val choreTitle: String,
    @SerialName("user_id") val userId: Int? = null,
    @SerialName("due_time") val dueTime: String,
)

@Serializable
data class HistoryDay(
    @SerialName("local_date") val localDate: String,
    val scheduled: Int,
    val done: Int,
    @SerialName("missed_count") val missedCount: Int,
    @SerialName("open_count") val openCount: Int = 0,
    val points: Int,
    val completions: List<HistoryItem> = emptyList(),
    val missed: List<MissedChore> = emptyList(),
)

@Serializable
data class HistoryDaysResponse(
    @SerialName("start_date") val startDate: String,
    @SerialName("end_date") val endDate: String,
    val days: List<HistoryDay> = emptyList(),
    @SerialName("older_start") val olderStart: String? = null,
    @SerialName("older_end") val olderEnd: String? = null,
    @SerialName("newer_start") val newerStart: String? = null,
    @SerialName("newer_end") val newerEnd: String? = null,
)


@Serializable
data class ChoreListResponse(
    val chores: List<Chore> = emptyList(),
)

@Serializable
data class ChoreCreate(
    val title: String,
    val description: String? = null,
    @SerialName("due_time") val dueTime: String = "20:00:00",
    @SerialName("schedule_days") val scheduleDays: String = "0123456",
    @SerialName("photo_policy") val photoPolicy: String = "none",
    @SerialName("base_points") val basePoints: Int = 10,
    @SerialName("early_bonus_enabled") val earlyBonusEnabled: Boolean = true,
)

@Serializable
data class ChoreUpdate(
    val title: String? = null,
    val description: String? = null,
    @SerialName("due_time") val dueTime: String? = null,
    @SerialName("schedule_days") val scheduleDays: String? = null,
    @SerialName("photo_policy") val photoPolicy: String? = null,
    @SerialName("base_points") val basePoints: Int? = null,
    @SerialName("early_bonus_enabled") val earlyBonusEnabled: Boolean? = null,
    @SerialName("clear_description") val clearDescription: Boolean = false,
)

@Serializable
data class QrInfo(
    @SerialName("chore_id") val choreId: Int,
    val title: String,
    @SerialName("qr_token") val qrToken: String,
    @SerialName("qr_url") val qrUrl: String,
    @SerialName("png_path") val pngPath: String,
)

@Serializable
data class ChoreDeleteResponse(
    val deleted: Boolean,
    @SerialName("chore_id") val choreId: Int,
    @SerialName("completions_removed") val completionsRemoved: Int,
)

// --- Rewards ---

@Serializable
data class TimingBonuses(
    @SerialName("early_bonus_points") val earlyBonusPoints: Int,
    @SerialName("on_time_bonus_points") val onTimeBonusPoints: Int,
    @SerialName("late_bonus_points") val lateBonusPoints: Int,
)

@Serializable
data class Achievement(
    val id: Int,
    val title: String,
    val description: String = "",
    @SerialName("icon_key") val iconKey: String,
    @SerialName("criteria_type") val criteriaType: String,
    val threshold: Int,
    @SerialName("points_reward") val pointsReward: Int,
    @SerialName("is_active") val isActive: Boolean,
)

@Serializable
data class AchievementCreate(
    val title: String,
    val description: String = "",
    @SerialName("icon_key") val iconKey: String = "star",
    @SerialName("criteria_type") val criteriaType: String,
    val threshold: Int = 1,
    @SerialName("points_reward") val pointsReward: Int = 0,
)

@Serializable
data class AchievementUpdate(
    val title: String? = null,
    val description: String? = null,
    @SerialName("icon_key") val iconKey: String? = null,
    @SerialName("criteria_type") val criteriaType: String? = null,
    val threshold: Int? = null,
    @SerialName("points_reward") val pointsReward: Int? = null,
)

@Serializable
data class RewardsResponse(
    val bonuses: TimingBonuses,
    val achievements: List<Achievement> = emptyList(),
)

@Serializable
data class UndoCompletionResponse(
    val success: Boolean = true,
    @SerialName("completion_id") val completionId: Int,
    @SerialName("chore_id") val choreId: Int,
    @SerialName("points_reverted") val pointsReverted: Int,
)

// --- Errors (wire) ---

@Serializable
data class StringDetail(
    val detail: String? = null,
)

@Serializable
data class DomainDetailBody(
    val message: String = "",
    val code: String = "",
)

@Serializable
data class DomainDetailEnvelope(
    val detail: DomainDetailBody? = null,
)

@Serializable
data class ValidationDetailItem(
    val loc: List<JsonElement> = emptyList(),
    val msg: String = "",
    val type: String = "",
)

@Serializable
data class ValidationDetailEnvelope(
    val detail: List<ValidationDetailItem> = emptyList(),
)
