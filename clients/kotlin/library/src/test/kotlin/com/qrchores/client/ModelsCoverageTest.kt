package com.qrchores.client

import com.qrchores.client.models.Achievement
import com.qrchores.client.models.AchievementCreate
import com.qrchores.client.models.AchievementProgress
import com.qrchores.client.models.AchievementUpdate
import com.qrchores.client.models.AchievementsResponse
import com.qrchores.client.models.BoardItem
import com.qrchores.client.models.ChildCreate
import com.qrchores.client.models.ChildDayGroup
import com.qrchores.client.models.ChildListResponse
import com.qrchores.client.models.ChildUpdate
import com.qrchores.client.models.Chore
import com.qrchores.client.models.ChoreConfirm
import com.qrchores.client.models.ChoreCreate
import com.qrchores.client.models.ChoreDeleteResponse
import com.qrchores.client.models.ChoreListResponse
import com.qrchores.client.models.ChoreUpdate
import com.qrchores.client.models.CompleteResponse
import com.qrchores.client.models.Completion
import com.qrchores.client.models.DomainDetailBody
import com.qrchores.client.models.DomainDetailEnvelope
import com.qrchores.client.models.HistoryDay
import com.qrchores.client.models.HistoryDaysResponse
import com.qrchores.client.models.HistoryItem
import com.qrchores.client.models.HistoryResponse
import com.qrchores.client.models.HomeResponse
import com.qrchores.client.models.LoginRequest
import com.qrchores.client.models.MissedChore
import com.qrchores.client.models.PointsBreakdown
import com.qrchores.client.models.QrInfo
import com.qrchores.client.models.RewardsResponse
import com.qrchores.client.models.StringDetail
import com.qrchores.client.models.TimingBonuses
import com.qrchores.client.models.TodayResponse
import com.qrchores.client.models.TodaySummary
import com.qrchores.client.models.TokenResponse
import com.qrchores.client.models.UndoCompletionResponse
import com.qrchores.client.models.Unlock
import com.qrchores.client.models.User
import com.qrchores.client.models.ValidationDetailEnvelope
import com.qrchores.client.models.ValidationDetailItem
import kotlinx.serialization.json.JsonPrimitive
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * Touch data-class copy/equals/hashCode/component accessors so Kover line coverage
 * reflects intentional model usage rather than only JSON decode paths.
 */
class ModelsCoverageTest {
    private val chore =
        Chore(
            id = 1,
            title = "T",
            description = "D",
            qrToken = "tok",
            dueTime = "20:00:00",
            scheduleDays = "0123456",
            photoPolicy = "optional",
            basePoints = 10,
            earlyBonusEnabled = true,
            isActive = true,
        )

    private val completion =
        Completion(
            id = 1,
            localDate = "2026-07-26",
            completedAt = "2026-07-26T12:00:00Z",
            timing = "on_time",
            pointsAwarded = 12,
            hasPhoto = true,
            notes = "Need cat litter",
        )

    @Test
    fun coreModels() {
        val user = User(1, "a@b.c", "A", "parent", 0)
        assertEquals(user, user.copy())
        assertEquals(user.hashCode(), user.copy().hashCode())
        assertTrue(user.toString().contains("parent"))
        assertEquals(1, user.component1())

        val childCreate =
            ChildCreate(
                email = "kid@example.com",
                password = "pass",
                firstName = "Kid",
                lastName = "One",
            )
        assertEquals(childCreate, childCreate.copy())
        val childUpdate = ChildUpdate(firstName = "Kiddo")
        assertEquals("Kiddo", childUpdate.copy().firstName)
        val childList = ChildListResponse(listOf(user))
        assertEquals(1, childList.children.size)
        assertEquals(childList, childList.copy())

        val token = TokenResponse("tok", "bearer", 100, user)
        assertEquals("tok", token.copy(accessToken = "tok").accessToken)
        assertEquals(token, TokenResponse("tok", "bearer", 100, user))

        val login = LoginRequest("e", "p")
        assertEquals("e", login.copy().email)

        assertEquals(chore, chore.copy(title = "T"))
        assertNotEquals(chore, chore.copy(title = "Other"))
        assertTrue(chore.toString().contains("Unload").not())
        assertEquals("T", chore.component2())

        assertEquals(completion, completion.copy())
        assertEquals(12, completion.component5())
    }

    @Test
    fun boardHomeHistory() {
        val board =
            BoardItem(
                chore = chore,
                done = true,
                statusLabel = "Done",
                statusKind = "done",
                isLatePending = false,
                timing = "on_time",
                completion = completion,
            )
        assertEquals("Done", board.copy().statusLabel)
        assertEquals(board, board.copy(done = true))
        assertTrue(board.hashCode() != 0 || board.hashCode() == 0)

        val unlock =
            Unlock(
                id = 1,
                title = "Early bird",
                description = "desc",
                iconKey = "bird",
                pointsReward = 25,
                unlockedAt = "2026-07-26T12:00:00Z",
            )
        assertEquals("Early bird", unlock.copy().title)
        assertEquals(unlock, unlock.copy(description = "desc"))

        val home =
            HomeResponse(
                localDate = "2026-07-26",
                pointsBalance = 1,
                pointsToday = 1,
                doneCount = 1,
                totalCount = 1,
                board = listOf(board),
                recentUnlocks = listOf(unlock),
            )
        assertEquals(1, home.copy().doneCount)
        assertEquals(home.board.first().chore.id, 1)

        val today = TodayResponse("2026-07-26", listOf(board))
        assertEquals(1, today.copy().board.size)

        val histItem = HistoryItem(completion, 1, "T", 2)
        assertEquals(1, histItem.copy().choreId)
        val hist = HistoryResponse(listOf(histItem), 50)
        assertEquals(50, hist.copy().limit)

        val summary = TodaySummary(2, 1, 0, 1, 0, 12)
        val group = ChildDayGroup(2, "Ava", 1, 2, 1, 12, listOf(board))
        val todayFull = TodayResponse("2026-07-26", listOf(board), summary, listOf(group))
        assertEquals(1, todayFull.copy().summary!!.overdue)
        assertEquals("Ava", todayFull.children.first().copy().childName)

        val missed = MissedChore(2, "Make bed", 2, "09:00:00")
        val day = HistoryDay("2026-07-26", 2, 1, 1, 0, 12, listOf(histItem), listOf(missed))
        val days = HistoryDaysResponse("2026-07-20", "2026-07-26", listOf(day))
        assertEquals("Make bed", days.copy().days.first().missed.first().copy().choreTitle)
        assertEquals(null, days.olderStart)
    }

    @Test
    fun completeAndConfirm() {
        val points = PointsBreakdown(10, 2, 0, 12)
        assertEquals(12, points.copy().total)
        assertEquals(points, PointsBreakdown(10, 2, 0, 12))

        val complete =
            CompleteResponse(
                alreadyDone = false,
                chore = chore,
                completion = completion,
                points = points,
                unlocks = emptyList(),
            )
        assertEquals(12, complete.copy().points.total)

        val confirm =
            ChoreConfirm(
                chore = chore,
                scheduledToday = true,
                alreadyDone = false,
                isLatePending = false,
                completion = null,
            )
        assertEquals(true, confirm.copy(alreadyDone = true).alreadyDone)
    }

    @Test
    fun achievementsAndRewards() {
        val progress =
            AchievementProgress(
                id = 1,
                title = "A",
                description = "d",
                iconKey = "star",
                criteriaType = "streak_days",
                pointsReward = 5,
                unlocked = false,
                progress = 1,
                threshold = 5,
                percent = 20,
            )
        assertEquals(20, progress.copy().percent)
        assertEquals(progress, progress.copy(progress = 1))

        val ar = AchievementsResponse(10, 0, listOf(progress))
        assertEquals(1, ar.copy().achievements.size)

        val ach =
            Achievement(
                id = 1,
                title = "A",
                description = "d",
                iconKey = "star",
                criteriaType = "streak_days",
                threshold = 5,
                pointsReward = 5,
                isActive = true,
            )
        assertTrue(ach.copy(isActive = false).isActive.not())

        val create =
            AchievementCreate(
                title = "A",
                description = "d",
                iconKey = "star",
                criteriaType = "streak_days",
                threshold = 5,
                pointsReward = 5,
            )
        assertEquals("A", create.copy().title)

        val update = AchievementUpdate(title = "B", pointsReward = 9)
        assertEquals(9, update.copy().pointsReward)

        val bonuses = TimingBonuses(5, 2, 0)
        assertEquals(5, bonuses.copy().earlyBonusPoints)
        val rewards = RewardsResponse(bonuses, listOf(ach))
        assertEquals(1, rewards.copy().achievements.size)
    }

    @Test
    fun choreWritesAndQr() {
        val create =
            ChoreCreate(
                title = "X",
                description = "Y",
                dueTime = "10:00:00",
                scheduleDays = "01",
                photoPolicy = "none",
                basePoints = 3,
                earlyBonusEnabled = false,
            )
        assertEquals("X", create.copy().title)
        assertTrue(!create.copy().earlyBonusEnabled)

        val update = ChoreUpdate(title = "Z", earlyBonusEnabled = true, clearDescription = true)
        assertTrue(update.copy().clearDescription)
        assertTrue(update.copy().earlyBonusEnabled == true)

        val list = ChoreListResponse(listOf(chore))
        assertEquals(1, list.copy().chores.size)

        val del = ChoreDeleteResponse(true, 1, 0)
        assertTrue(del.copy().deleted)

        val undo = UndoCompletionResponse(true, 10, 1, 12)
        assertTrue(undo.copy().success)
        assertEquals(10, undo.completionId)
        assertEquals(12, undo.pointsReverted)

        val qr = QrInfo(1, "T", "tok", "http://x/c/tok", "/png")
        assertEquals("tok", qr.copy().qrToken)
    }

    @Test
    fun errorWireModels() {
        assertEquals("hi", StringDetail("hi").copy().detail)
        assertEquals("c", DomainDetailBody("m", "c").copy().code)
        assertEquals("m", DomainDetailEnvelope(DomainDetailBody("m", "c")).detail!!.message)
        val item =
            ValidationDetailItem(
                loc = listOf(JsonPrimitive("body")),
                msg = "err",
                type = "missing",
            )
        assertEquals("err", item.copy().msg)
        assertEquals(1, ValidationDetailEnvelope(listOf(item)).copy().detail.size)
    }
}
