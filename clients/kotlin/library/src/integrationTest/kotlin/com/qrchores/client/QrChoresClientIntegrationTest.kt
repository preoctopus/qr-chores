package com.qrchores.client

import com.qrchores.client.errors.AuthException
import com.qrchores.client.errors.DomainException
import com.qrchores.client.errors.ForbiddenException
import com.qrchores.client.errors.NotFoundException
import com.qrchores.client.models.AchievementCreate
import com.qrchores.client.models.AchievementUpdate
import com.qrchores.client.models.ChildCreate
import com.qrchores.client.models.ChildUpdate
import com.qrchores.client.models.ChoreCreate
import com.qrchores.client.models.ChoreUpdate
import com.qrchores.client.models.TimingBonuses
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertArrayEquals
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.junit.jupiter.api.extension.ExtendWith

/**
 * Live tests against mock-api (fixture accounts from CONTRACT.md).
 *
 * Note: mock-api state is process-global and is not reset between tests.
 * Tests prefer read-only fixture data or unique create titles.
 */
@ExtendWith(MockApiFixture::class)
class QrChoresClientIntegrationTest {
    private lateinit var client: QrChoresClient

    // 1x1 transparent PNG (same as mock fixtures)
    private val tinyPng =
        byteArrayOf(
            0x89.toByte(),
            0x50,
            0x4E,
            0x47,
            0x0D,
            0x0A,
            0x1A,
            0x0A,
            0x00,
            0x00,
            0x00,
            0x0D,
            0x49,
            0x48,
            0x44,
            0x52,
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x01,
            0x08,
            0x06,
            0x00,
            0x00,
            0x00,
            0x1F,
            0x15,
            0xC4.toByte(),
            0x89.toByte(),
            0x00,
            0x00,
            0x00,
            0x0A,
            0x49,
            0x44,
            0x41,
            0x54,
            0x78,
            0x9C.toByte(),
            0x63,
            0x00,
            0x01,
            0x00,
            0x00,
            0x05,
            0x00,
            0x01,
            0x0D,
            0x0A,
            0x2D,
            0xB4.toByte(),
            0x00,
            0x00,
            0x00,
            0x00,
            0x49,
            0x45,
            0x4E,
            0x44,
            0xAE.toByte(),
            0x42,
            0x60,
            0x82.toByte(),
        )

    @BeforeEach
    fun setUp() {
        client = QrChoresClient(baseUrl = MockApiFixture.BASE_URL)
    }

    @AfterEach
    fun tearDown() {
        client.close()
    }

    @Test
    fun parentLoginAndBoard() =
        runBlocking {
            val token = client.login("parent@example.com", "parent-pass")
            assertEquals("parent-token", token.accessToken)
            assertEquals("parent", token.user.role)

            val me = client.getMe()
            assertEquals("parent@example.com", me.email)

            val today = client.getToday()
            assertTrue(today.board.isNotEmpty())

            val history = client.getHistory(limit = 10)
            assertTrue(history.items.isNotEmpty())
            assertEquals(10, history.limit)
        }

    @Test
    fun childLoginHomeAndAchievements() =
        runBlocking {
            val token = client.login("child@example.com", "child-pass")
            assertEquals("child-token", token.accessToken)

            val home = client.getHome()
            assertTrue(home.totalCount >= 1)
            assertTrue(home.pointsBalance >= 0)

            val confirm = client.getConfirm("qr-active-1")
            assertEquals("Unload dishwasher", confirm.chore.title)

            val achievements = client.getAchievements()
            assertTrue(achievements.achievements.isNotEmpty())
        }

    @Test
    fun parentChoreCrudAndQr() {
        runBlocking {
            client.login("parent@example.com", "parent-pass")

            val children = client.listChildren(includeInactive = true)
            assertTrue(children.children.isNotEmpty())
            val createdChild =
                client.createChild(
                    ChildCreate(
                        email = "kt-kid-${System.currentTimeMillis()}@example.com",
                        password = "child-pass",
                        firstName = "Kotlin",
                        lastName = "Kid",
                    ),
                )
            assertTrue(createdChild.id > 0)
            assertEquals("child", createdChild.role)
            val fetchedChild = client.getChild(createdChild.id)
            assertEquals(createdChild.id, fetchedChild.id)
            val updatedChild =
                client.updateChild(createdChild.id, ChildUpdate(firstName = "Kt"))
            assertTrue(updatedChild.displayName.contains("Kt"))
            assertFalse(client.deactivateChild(createdChild.id).isActive)
            assertTrue(client.activateChild(createdChild.id).isActive)

            val list = client.listChores(includeInactive = true)
            assertTrue(list.chores.size >= 3)

            val created =
                client.createChore(
                    ChoreCreate(
                        title = "Kotlin IT chore ${System.currentTimeMillis()}",
                        description = "from integration test",
                        dueTime = "18:30:00",
                        scheduleDays = "0123456",
                        photoPolicy = "optional",
                        basePoints = 7,
                    ),
                )
            assertTrue(created.id > 0)
            assertTrue(created.qrToken.isNotBlank())
            assertTrue(created.isActive)

            val fetched = client.getChore(created.id)
            assertEquals(created.title, fetched.title)

            val updated =
                client.updateChore(
                    created.id,
                    ChoreUpdate(title = "${created.title} updated", basePoints = 9),
                )
            assertEquals(9, updated.basePoints)
            assertTrue(updated.title.endsWith("updated"))

            val qr = client.getQrInfo(created.id)
            assertEquals(created.qrToken, qr.qrToken)

            val png = client.getQrPng(created.id)
            assertTrue(png.size >= 8)
            assertEquals(0x89.toByte(), png[0])
            assertEquals('P'.code.toByte(), png[1])

            val deactivated = client.deactivateChore(created.id)
            assertFalse(deactivated.isActive)
            val activated = client.activateChore(created.id)
            assertTrue(activated.isActive)

            val deleted = client.deleteChore(created.id)
            assertTrue(deleted.deleted)
            assertEquals(created.id, deleted.choreId)

            assertThrows<NotFoundException> {
                runBlocking { client.getChore(created.id) }
            }
        }
    }

    @Test
    fun parentRewards() {
        runBlocking {
            client.login("parent@example.com", "parent-pass")

            val rewards = client.getRewards()
            assertTrue(rewards.achievements.isNotEmpty())

            val bonuses =
                client.updateBonuses(
                    TimingBonuses(
                        earlyBonusPoints = rewards.bonuses.earlyBonusPoints,
                        onTimeBonusPoints = rewards.bonuses.onTimeBonusPoints,
                        lateBonusPoints = rewards.bonuses.lateBonusPoints,
                    ),
                )
            assertEquals(rewards.bonuses.earlyBonusPoints, bonuses.earlyBonusPoints)

            val created =
                client.createAchievement(
                    AchievementCreate(
                        title = "Kotlin IT achievement ${System.currentTimeMillis()}",
                        description = "integration",
                        iconKey = "star",
                        criteriaType = "total_completions",
                        threshold = 3,
                        pointsReward = 15,
                    ),
                )
            assertTrue(created.isActive)

            val updated =
                client.updateAchievement(
                    created.id,
                    AchievementUpdate(pointsReward = 20),
                )
            assertEquals(20, updated.pointsReward)

            val toggled = client.toggleAchievement(created.id)
            assertFalse(toggled.isActive)
            // restore
            client.toggleAchievement(created.id)
        }
    }

    @Test
    fun completeFlowWithPhotoAndGetPhoto() =
        runBlocking {
            // Complete photo-required chore (seed chore 2) — may already be done if re-run.
            client.login("child@example.com", "child-pass")

            val confirm = client.getConfirm("qr-photo-required")
            assertEquals("required", confirm.chore.photoPolicy)

            if (!confirm.alreadyDone) {
                // Missing photo → domain error
                val domain =
                    assertThrows<DomainException> {
                        runBlocking { client.completeChore("qr-photo-required") }
                    }
                assertEquals("photo_required", domain.code)

                val result =
                    client.completeChore(
                        qrToken = "qr-photo-required",
                        photoBytes = tinyPng,
                        photoFileName = "proof.png",
                        photoContentType = "image/png",
                    )
                assertFalse(result.alreadyDone)
                assertTrue(result.completion.hasPhoto)
                assertTrue(result.points.total > 0)

                val photo = client.getPhoto(result.completion.id)
                assertTrue(photo.isNotEmpty())
                assertEquals(0x89.toByte(), photo[0])
            } else {
                // Already completed in this mock process — still exercise getPhoto on seed completion 1
                val photo = client.getPhoto(1)
                assertTrue(photo.isNotEmpty())
            }
        }

    @Test
    fun getPhotoSeedCompletion() =
        runBlocking {
            client.login("parent@example.com", "parent-pass")
            val photo = client.getPhoto(1)
            assertTrue(photo.size >= 8)
            assertEquals(0x89.toByte(), photo[0])
            assertEquals('P'.code.toByte(), photo[1])
            assertEquals('N'.code.toByte(), photo[2])
            assertEquals('G'.code.toByte(), photo[3])
        }

    @Test
    fun childCannotAccessParentRoutes() {
        runBlocking {
            client.login("child@example.com", "child-pass")
            assertThrows<ForbiddenException> {
                runBlocking { client.getToday() }
            }
            assertThrows<ForbiddenException> {
                runBlocking { client.listChores() }
            }
        }
    }

    @Test
    fun parentCannotAccessChildRoutes() {
        runBlocking {
            client.login("parent@example.com", "parent-pass")
            assertThrows<ForbiddenException> {
                runBlocking { client.getHome() }
            }
        }
    }

    @Test
    fun badLogin() {
        runBlocking {
            assertThrows<AuthException> {
                runBlocking { client.login("nobody@example.com", "wrong") }
            }
            assertEquals(null, client.accessToken)
        }
    }

    @Test
    fun logout() =
        runBlocking {
            client.login("parent@example.com", "parent-pass")
            assertNotNull(client.accessToken)
            client.logout()
            assertEquals(null, client.accessToken)
        }

    @Test
    fun completeAlreadyDoneChore1() =
        runBlocking {
            // Seed has chore 1 completed today
            client.login("child@example.com", "child-pass")
            val result = client.completeChore("qr-active-1")
            // Either already_done true or we completed it
            assertNotNull(result.completion)
            assertTrue(result.alreadyDone || result.points.total >= 0)
        }
}
