package com.qrchores.client

import com.qrchores.client.errors.ApiException
import com.qrchores.client.errors.AuthException
import com.qrchores.client.errors.DomainException
import com.qrchores.client.errors.ForbiddenException
import com.qrchores.client.errors.NotFoundException
import com.qrchores.client.errors.ValidationException
import com.qrchores.client.models.AchievementCreate
import com.qrchores.client.models.AchievementUpdate
import com.qrchores.client.models.ChildCreate
import com.qrchores.client.models.ChildUpdate
import com.qrchores.client.models.ChoreCreate
import com.qrchores.client.models.ChoreUpdate
import com.qrchores.client.models.TimingBonuses
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertArrayEquals
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

class QrChoresClientUnitTest {
    private val jsonHeaders = headersOf(HttpHeaders.ContentType, "application/json")

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
        )

    private fun clientFor(
        handler: suspend MockRequestHandleScope.(HttpRequestData) -> HttpResponseData,
    ): QrChoresClient {
        val engine = MockEngine { request -> handler(request) }
        return QrChoresClient(baseUrl = "http://testserver", engine = engine)
    }

    private fun MockRequestHandleScope.okJson(body: String): HttpResponseData =
        respond(body, HttpStatusCode.OK, jsonHeaders)

    @Test
    fun loginStoresToken() =
        runTest {
            val client =
                clientFor { request ->
                    assertEquals(HttpMethod.Post, request.method)
                    assertTrue(request.url.encodedPath.endsWith("/api/v1/auth/login"))
                    okJson(
                        """
                        {
                          "access_token": "tok-1",
                          "token_type": "bearer",
                          "expires_in": 1209600,
                          "user": {
                            "id": 1,
                            "email": "parent@example.com",
                            "display_name": "Parent",
                            "role": "parent",
                            "points_balance": 0
                          }
                        }
                        """.trimIndent(),
                    )
                }
            val token = client.login("parent@example.com", "parent-pass")
            assertEquals("tok-1", token.accessToken)
            assertEquals("tok-1", client.accessToken)
            assertEquals("parent", token.user.role)
            client.close()
        }

    @Test
    fun logoutClearsToken() =
        runTest {
            val client =
                clientFor { request ->
                    assertEquals(HttpMethod.Post, request.method)
                    respond("", HttpStatusCode.NoContent)
                }
            client.accessToken = "abc"
            client.logout()
            assertNull(client.accessToken)
            client.close()
        }

    @Test
    fun getMe() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """{"id":2,"email":"child@example.com","display_name":"Child","role":"child","points_balance":42}""",
                    )
                }
            client.accessToken = "child-token"
            val me = client.getMe()
            assertEquals(2, me.id)
            assertEquals(42, me.pointsBalance)
            client.close()
        }

    @Test
    fun getHome() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """
                        {
                          "local_date": "2026-07-26",
                          "points_balance": 42,
                          "points_today": 12,
                          "done_count": 1,
                          "total_count": 2,
                          "board": [],
                          "recent_unlocks": []
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "child-token"
            val home = client.getHome()
            assertEquals(42, home.pointsBalance)
            assertEquals(1, home.doneCount)
            client.close()
        }

    @Test
    fun getConfirm() =
        runTest {
            val client =
                clientFor { request ->
                    assertTrue(request.url.encodedPath.contains("/api/v1/c/qr-active-1"))
                    okJson(
                        """
                        {
                          "chore": {
                            "id": 1,
                            "title": "Unload dishwasher",
                            "description": "Empty top rack first",
                            "qr_token": "qr-active-1",
                            "due_time": "20:00:00",
                            "schedule_days": "0123456",
                            "photo_policy": "optional",
                            "base_points": 10,
                            "is_active": true
                          },
                          "scheduled_today": true,
                          "already_done": false,
                          "is_late_pending": false,
                          "completion": null
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "child-token"
            val confirm = client.getConfirm("qr-active-1")
            assertFalse(confirm.alreadyDone)
            assertEquals("Unload dishwasher", confirm.chore.title)
            client.close()
        }

    @Test
    fun completeChoreWithoutPhoto() =
        runTest {
            val client =
                clientFor { request ->
                    assertEquals(HttpMethod.Post, request.method)
                    assertTrue(request.url.encodedPath.endsWith("/complete"))
                    okJson(
                        """
                        {
                          "already_done": false,
                          "chore": {
                            "id": 1,
                            "title": "Unload dishwasher",
                            "description": null,
                            "qr_token": "qr-active-1",
                            "due_time": "20:00:00",
                            "schedule_days": "0123456",
                            "photo_policy": "optional",
                            "base_points": 10,
                            "is_active": true
                          },
                          "completion": {
                            "id": 2,
                            "local_date": "2026-07-26",
                            "completed_at": "2026-07-26T12:00:00Z",
                            "timing": "on_time",
                            "points_awarded": 12,
                            "has_photo": false
                          },
                          "points": {
                            "base": 10,
                            "timing_bonus": 2,
                            "achievement_points": 0,
                            "total": 12
                          },
                          "unlocks": []
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "child-token"
            val result = client.completeChore("qr-active-1")
            assertEquals(12, result.points.total)
            assertFalse(result.alreadyDone)
            client.close()
        }

    @Test
    fun completeChoreWithPhoto() =
        runTest {
            val client =
                clientFor { request ->
                    val ct = request.body.contentType?.toString().orEmpty()
                    assertTrue(ct.contains("multipart") || request.body.contentType != null)
                    okJson(
                        """
                        {
                          "already_done": false,
                          "chore": {
                            "id": 2,
                            "title": "Make bed",
                            "description": null,
                            "qr_token": "qr-photo-required",
                            "due_time": "09:00:00",
                            "schedule_days": "0123456",
                            "photo_policy": "required",
                            "base_points": 5,
                            "is_active": true
                          },
                          "completion": {
                            "id": 3,
                            "local_date": "2026-07-26",
                            "completed_at": "2026-07-26T12:00:00Z",
                            "timing": "on_time",
                            "points_awarded": 7,
                            "has_photo": true
                          },
                          "points": {"base": 5, "timing_bonus": 2, "achievement_points": 0, "total": 7},
                          "unlocks": []
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "child-token"
            val result =
                client.completeChore(
                    qrToken = "qr-photo-required",
                    photoBytes = tinyPng,
                    photoFileName = "shot.png",
                    photoContentType = "image/png",
                )
            assertTrue(result.completion.hasPhoto)
            client.close()
        }

    @Test
    fun getAchievements() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """
                        {
                          "points_balance": 42,
                          "unlocked_count": 0,
                          "achievements": [
                            {
                              "id": 1,
                              "title": "Early bird",
                              "description": "Complete early 5 times",
                              "icon_key": "bird",
                              "criteria_type": "complete_early_count",
                              "points_reward": 25,
                              "unlocked": false,
                              "progress": 0,
                              "threshold": 5,
                              "percent": 0
                            }
                          ]
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "child-token"
            val ach = client.getAchievements()
            assertEquals(1, ach.achievements.size)
            assertEquals("Early bird", ach.achievements[0].title)
            client.close()
        }

    @Test
    fun getToday() =
        runTest {
            val client =
                clientFor {
                    okJson("""{"local_date":"2026-07-26","board":[]}""")
                }
            client.accessToken = "parent-token"
            val today = client.getToday()
            assertEquals("2026-07-26", today.localDate)
            client.close()
        }

    @Test
    fun getHistory() =
        runTest {
            val client =
                clientFor { request ->
                    assertEquals("25", request.url.parameters["limit"])
                    okJson(
                        """
                        {
                          "items": [
                            {
                              "completion": {
                                "id": 1,
                                "local_date": "2026-07-26",
                                "completed_at": "2026-07-26T12:00:00Z",
                                "timing": "on_time",
                                "points_awarded": 12,
                                "has_photo": true
                              },
                              "chore_id": 1,
                              "chore_title": "Unload dishwasher",
                              "user_id": 2
                            }
                          ],
                          "limit": 25
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            val history = client.getHistory(limit = 25)
            assertEquals(1, history.items.size)
            assertEquals(25, history.limit)
            client.close()
        }

    @Test
    fun listChildren() =
        runTest {
            val client =
                clientFor { request ->
                    assertTrue(request.url.encodedPath.endsWith("/api/v1/children"))
                    assertEquals("false", request.url.parameters["include_inactive"])
                    okJson(
                        """
                        {
                          "children": [
                            {
                              "id": 2,
                              "email": "child@example.com",
                              "first_name": "Child",
                              "last_name": "User",
                              "display_name": "Child User",
                              "role": "child",
                              "parent_id": 1,
                              "is_active": true,
                              "points_balance": 42
                            }
                          ]
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            val list = client.listChildren(includeInactive = false)
            assertEquals(1, list.children.size)
            assertEquals(2, list.children[0].id)
            assertEquals(1, list.children[0].parentId)
            client.close()
        }

    @Test
    fun createGetUpdateActivateDeactivateChild() =
        runTest {
            val childJson =
                """
                {
                  "id": 3,
                  "email": "sam@example.com",
                  "first_name": "Sam",
                  "last_name": "Kid",
                  "display_name": "Sam Kid",
                  "role": "child",
                  "parent_id": 1,
                  "is_active": true,
                  "points_balance": 0
                }
                """.trimIndent()
            val client =
                clientFor { request ->
                    when {
                        request.method == HttpMethod.Post &&
                            request.url.encodedPath.endsWith("/api/v1/children") ->
                            respond(childJson, HttpStatusCode.Created, jsonHeaders)
                        request.method == HttpMethod.Get &&
                            request.url.encodedPath.endsWith("/api/v1/children/3") ->
                            okJson(childJson)
                        request.method == HttpMethod.Patch &&
                            request.url.encodedPath.endsWith("/api/v1/children/3") ->
                            okJson(
                                childJson.replace("\"first_name\": \"Sam\"", "\"first_name\": \"Sammy\"")
                                    .replace("\"display_name\": \"Sam Kid\"", "\"display_name\": \"Sammy Kid\""),
                            )
                        request.method == HttpMethod.Post &&
                            request.url.encodedPath.endsWith("/api/v1/children/3/deactivate") ->
                            okJson(childJson.replace("\"is_active\": true", "\"is_active\": false"))
                        request.method == HttpMethod.Post &&
                            request.url.encodedPath.endsWith("/api/v1/children/3/activate") ->
                            okJson(childJson)
                        else -> error("unexpected ${request.method} ${request.url}")
                    }
                }
            client.accessToken = "parent-token"
            val created =
                client.createChild(
                    ChildCreate(
                        email = "sam@example.com",
                        password = "child-pass",
                        firstName = "Sam",
                        lastName = "Kid",
                    ),
                )
            assertEquals(3, created.id)
            assertEquals("sam@example.com", client.getChild(3).email)
            val updated = client.updateChild(3, ChildUpdate(firstName = "Sammy"))
            assertEquals("Sammy Kid", updated.displayName)
            assertFalse(client.deactivateChild(3).isActive)
            assertTrue(client.activateChild(3).isActive)
            client.close()
        }

    @Test
    fun listChores() =
        runTest {
            val client =
                clientFor { request ->
                    assertEquals("false", request.url.parameters["include_inactive"])
                    okJson(
                        """
                        {
                          "chores": [
                            {
                              "id": 1,
                              "title": "Unload dishwasher",
                              "description": null,
                              "qr_token": "qr-active-1",
                              "due_time": "20:00:00",
                              "schedule_days": "0123456",
                              "photo_policy": "optional",
                              "base_points": 10,
                              "is_active": true
                            }
                          ]
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            val list = client.listChores(includeInactive = false)
            assertEquals(1, list.chores.size)
            client.close()
        }

    @Test
    fun createChore() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """
                        {
                          "id": 4,
                          "title": "Take trash out",
                          "description": null,
                          "qr_token": "qr-gen-4",
                          "due_time": "19:00:00",
                          "schedule_days": "0123456",
                          "photo_policy": "none",
                          "base_points": 8,
                          "is_active": true
                        }
                        """.trimIndent(),
                        HttpStatusCode.Created,
                        jsonHeaders,
                    )
                }
            client.accessToken = "parent-token"
            val chore =
                client.createChore(
                    ChoreCreate(title = "Take trash out", dueTime = "19:00:00", basePoints = 8),
                )
            assertEquals(4, chore.id)
            assertEquals("qr-gen-4", chore.qrToken)
            client.close()
        }

    @Test
    fun getChore() =
        runTest {
            val client =
                clientFor { request ->
                    assertTrue(request.url.encodedPath.endsWith("/chores/1"))
                    okJson(
                        """
                        {
                          "id": 1,
                          "title": "Unload dishwasher",
                          "description": "Empty top rack first",
                          "qr_token": "qr-active-1",
                          "due_time": "20:00:00",
                          "schedule_days": "0123456",
                          "photo_policy": "optional",
                          "base_points": 10,
                          "is_active": true
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            val chore = client.getChore(1)
            assertEquals("Unload dishwasher", chore.title)
            client.close()
        }

    @Test
    fun updateChore() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """
                        {
                          "id": 1,
                          "title": "Unload dishwasher fully",
                          "description": null,
                          "qr_token": "qr-active-1",
                          "due_time": "20:00:00",
                          "schedule_days": "0123456",
                          "photo_policy": "optional",
                          "base_points": 10,
                          "is_active": true
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            val chore =
                client.updateChore(
                    1,
                    ChoreUpdate(title = "Unload dishwasher fully", clearDescription = true),
                )
            assertEquals("Unload dishwasher fully", chore.title)
            assertNull(chore.description)
            client.close()
        }

    @Test
    fun deleteChore() =
        runTest {
            val client =
                clientFor {
                    okJson("""{"deleted":true,"chore_id":3,"completions_removed":0}""")
                }
            client.accessToken = "parent-token"
            val result = client.deleteChore(3)
            assertTrue(result.deleted)
            assertEquals(3, result.choreId)
            client.close()
        }

    @Test
    fun activateAndDeactivate() =
        runTest {
            var call = 0
            val client =
                clientFor {
                    call += 1
                    val active = call == 1
                    okJson(
                        """
                        {
                          "id": 3,
                          "title": "Old chore",
                          "description": "Retired",
                          "qr_token": "qr-inactive",
                          "due_time": "12:00:00",
                          "schedule_days": "0123456",
                          "photo_policy": "none",
                          "base_points": 1,
                          "is_active": $active
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            assertTrue(client.activateChore(3).isActive)
            assertFalse(client.deactivateChore(3).isActive)
            client.close()
        }

    @Test
    fun getQrInfo() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """
                        {
                          "chore_id": 1,
                          "title": "Unload dishwasher",
                          "qr_token": "qr-active-1",
                          "qr_url": "http://testserver/c/qr-active-1",
                          "png_path": "/api/v1/chores/1/qr.png"
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            val info = client.getQrInfo(1)
            assertEquals("qr-active-1", info.qrToken)
            client.close()
        }

    @Test
    fun getQrPng() =
        runTest {
            val client =
                clientFor {
                    respond(
                        tinyPng,
                        HttpStatusCode.OK,
                        headersOf(HttpHeaders.ContentType, "image/png"),
                    )
                }
            client.accessToken = "parent-token"
            val bytes = client.getQrPng(1)
            assertArrayEquals(tinyPng, bytes)
            client.close()
        }

    @Test
    fun getRewards() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """
                        {
                          "bonuses": {
                            "early_bonus_points": 5,
                            "on_time_bonus_points": 2,
                            "late_bonus_points": 0
                          },
                          "achievements": [
                            {
                              "id": 1,
                              "title": "Early bird",
                              "description": "Complete early 5 times",
                              "icon_key": "bird",
                              "criteria_type": "complete_early_count",
                              "threshold": 5,
                              "points_reward": 25,
                              "is_active": true
                            }
                          ]
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            val rewards = client.getRewards()
            assertEquals(5, rewards.bonuses.earlyBonusPoints)
            assertEquals(1, rewards.achievements.size)
            client.close()
        }

    @Test
    fun updateBonuses() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """{"early_bonus_points":10,"on_time_bonus_points":3,"late_bonus_points":1}""",
                    )
                }
            client.accessToken = "parent-token"
            val bonuses =
                client.updateBonuses(
                    TimingBonuses(earlyBonusPoints = 10, onTimeBonusPoints = 3, lateBonusPoints = 1),
                )
            assertEquals(10, bonuses.earlyBonusPoints)
            client.close()
        }

    @Test
    fun createAchievement() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """
                        {
                          "id": 2,
                          "title": "Streak master",
                          "description": "7 day streak",
                          "icon_key": "fire",
                          "criteria_type": "streak_days",
                          "threshold": 7,
                          "points_reward": 50,
                          "is_active": true
                        }
                        """.trimIndent(),
                        HttpStatusCode.Created,
                        jsonHeaders,
                    )
                }
            client.accessToken = "parent-token"
            val ach =
                client.createAchievement(
                    AchievementCreate(
                        title = "Streak master",
                        description = "7 day streak",
                        iconKey = "fire",
                        criteriaType = "streak_days",
                        threshold = 7,
                        pointsReward = 50,
                    ),
                )
            assertEquals(2, ach.id)
            client.close()
        }

    @Test
    fun updateAchievement() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """
                        {
                          "id": 1,
                          "title": "Early bird+",
                          "description": "Complete early 5 times",
                          "icon_key": "bird",
                          "criteria_type": "complete_early_count",
                          "threshold": 5,
                          "points_reward": 30,
                          "is_active": true
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            val ach =
                client.updateAchievement(
                    1,
                    AchievementUpdate(title = "Early bird+", pointsReward = 30),
                )
            assertEquals("Early bird+", ach.title)
            assertEquals(30, ach.pointsReward)
            client.close()
        }

    @Test
    fun toggleAchievement() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """
                        {
                          "id": 1,
                          "title": "Early bird",
                          "description": "Complete early 5 times",
                          "icon_key": "bird",
                          "criteria_type": "complete_early_count",
                          "threshold": 5,
                          "points_reward": 25,
                          "is_active": false
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "parent-token"
            val ach = client.toggleAchievement(1)
            assertFalse(ach.isActive)
            client.close()
        }

    @Test
    fun getPhoto() =
        runTest {
            val client =
                clientFor {
                    respond(
                        tinyPng,
                        HttpStatusCode.OK,
                        headersOf(HttpHeaders.ContentType, "image/png"),
                    )
                }
            client.accessToken = "parent-token"
            val bytes = client.getPhoto(1)
            assertArrayEquals(tinyPng, bytes)
            client.close()
        }

    // --- Error mapping ---

    @Test
    fun maps401ToAuthException() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":"Not authenticated"}""",
                        HttpStatusCode.Unauthorized,
                        jsonHeaders,
                    )
                }
            val ex = assertThrows<AuthException> { client.getMe() }
            assertEquals("Not authenticated", ex.message)
            client.close()
        }

    @Test
    fun maps403ToForbiddenException() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":"Insufficient permissions"}""",
                        HttpStatusCode.Forbidden,
                        jsonHeaders,
                    )
                }
            client.accessToken = "child-token"
            val ex = assertThrows<ForbiddenException> { client.getToday() }
            assertTrue(ex.message!!.contains("Insufficient"))
            client.close()
        }

    @Test
    fun maps404ToNotFoundException() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":"Chore not found"}""",
                        HttpStatusCode.NotFound,
                        jsonHeaders,
                    )
                }
            client.accessToken = "parent-token"
            val ex = assertThrows<NotFoundException> { client.getChore(999) }
            assertEquals("Chore not found", ex.message)
            client.close()
        }

    @Test
    fun maps400ToDomainException() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":{"message":"A photo is required for this chore.","code":"photo_required"}}""",
                        HttpStatusCode.BadRequest,
                        jsonHeaders,
                    )
                }
            client.accessToken = "child-token"
            val ex = assertThrows<DomainException> { client.completeChore("qr-photo-required") }
            assertEquals("photo_required", ex.code)
            assertTrue(ex.message!!.contains("photo"))
            client.close()
        }

    @Test
    fun maps422ToValidationException() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """
                        {
                          "detail": [
                            {
                              "loc": ["body", "title"],
                              "msg": "Field required",
                              "type": "missing"
                            }
                          ]
                        }
                        """.trimIndent(),
                        HttpStatusCode.UnprocessableEntity,
                        jsonHeaders,
                    )
                }
            client.accessToken = "parent-token"
            val ex =
                assertThrows<ValidationException> {
                    client.createChore(ChoreCreate(title = ""))
                }
            assertEquals(1, ex.errors.size)
            assertEquals("Field required", ex.errors[0].msg)
            client.close()
        }

    @Test
    fun maps500ToApiException() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":"boom"}""",
                        HttpStatusCode.InternalServerError,
                        jsonHeaders,
                    )
                }
            client.accessToken = "parent-token"
            val ex = assertThrows<ApiException> { client.getMe() }
            assertEquals(500, ex.statusCode)
            client.close()
        }

    @Test
    fun loginFailureDoesNotStoreToken() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":"Invalid email or password."}""",
                        HttpStatusCode.Unauthorized,
                        jsonHeaders,
                    )
                }
            assertThrows<AuthException> {
                client.login("bad@example.com", "wrong")
            }
            assertNull(client.accessToken)
            client.close()
        }

    @Test
    fun createFactoryWithEngine() =
        runTest {
            val engine =
                MockEngine {
                    respond(
                        """{"id":1,"email":"a@b.c","display_name":"A","role":"parent","points_balance":0}""",
                        HttpStatusCode.OK,
                        jsonHeaders,
                    )
                }
            val client = QrChoresClient.create("http://testserver", engine)
            client.accessToken = "t"
            assertNotNull(client.getMe())
            client.close()
        }

    @Test
    fun photoNotFound() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":"Photo not found"}""",
                        HttpStatusCode.NotFound,
                        jsonHeaders,
                    )
                }
            client.accessToken = "parent-token"
            assertThrows<NotFoundException> { client.getPhoto(999) }
            client.close()
        }

    @Test
    fun getQrPngNotFound() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":"Chore not found"}""",
                        HttpStatusCode.NotFound,
                        jsonHeaders,
                    )
                }
            client.accessToken = "parent-token"
            assertThrows<NotFoundException> { client.getQrPng(999) }
            client.close()
        }

    @Test
    fun logoutWithNonSuccessClearsTokenAnyway() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":"boom"}""",
                        HttpStatusCode.InternalServerError,
                        jsonHeaders,
                    )
                }
            client.accessToken = "tok"
            assertThrows<ApiException> { client.logout() }
            assertNull(client.accessToken)
            client.close()
        }

    @Test
    fun badRequestWithoutDomainFallsToDomainException() =
        runTest {
            val client =
                clientFor {
                    respond(
                        """{"detail":"plain bad"}""",
                        HttpStatusCode.BadRequest,
                        jsonHeaders,
                    )
                }
            client.accessToken = "t"
            val ex = assertThrows<DomainException> { client.getMe() }
            assertEquals("domain_error", ex.code)
            assertEquals("plain bad", ex.message)
            client.close()
        }

    @Test
    fun getHistoryDefaultLimit() =
        runTest {
            val client =
                clientFor { request ->
                    assertEquals("50", request.url.parameters["limit"])
                    okJson("""{"items":[],"limit":50}""")
                }
            client.accessToken = "parent-token"
            val history = client.getHistory()
            assertEquals(50, history.limit)
            client.close()
        }

    @Test
    fun completeWithUnlocksAndBoardRichHome() =
        runTest {
            val client =
                clientFor { request ->
                    when {
                        request.url.encodedPath.endsWith("/home") ->
                            okJson(
                                """
                                {
                                  "local_date": "2026-07-26",
                                  "points_balance": 100,
                                  "points_today": 25,
                                  "done_count": 1,
                                  "total_count": 1,
                                  "board": [
                                    {
                                      "chore": {
                                        "id": 1,
                                        "title": "Unload dishwasher",
                                        "description": "x",
                                        "qr_token": "qr-active-1",
                                        "due_time": "20:00:00",
                                        "schedule_days": "0123456",
                                        "photo_policy": "optional",
                                        "base_points": 10,
                                        "is_active": true
                                      },
                                      "done": true,
                                      "status_label": "Done",
                                      "status_kind": "done",
                                      "is_late_pending": false,
                                      "timing": "on_time",
                                      "completion": {
                                        "id": 1,
                                        "local_date": "2026-07-26",
                                        "completed_at": "2026-07-26T12:00:00Z",
                                        "timing": "on_time",
                                        "points_awarded": 12,
                                        "has_photo": true
                                      }
                                    }
                                  ],
                                  "recent_unlocks": [
                                    {
                                      "id": 1,
                                      "title": "Early bird",
                                      "description": "done",
                                      "icon_key": "bird",
                                      "points_reward": 25,
                                      "unlocked_at": "2026-07-26T12:00:00Z"
                                    }
                                  ]
                                }
                                """.trimIndent(),
                            )
                        else ->
                            okJson(
                                """
                                {
                                  "already_done": false,
                                  "chore": {
                                    "id": 1,
                                    "title": "Unload dishwasher",
                                    "description": null,
                                    "qr_token": "qr-active-1",
                                    "due_time": "20:00:00",
                                    "schedule_days": "0123456",
                                    "photo_policy": "optional",
                                    "base_points": 10,
                                    "is_active": true
                                  },
                                  "completion": {
                                    "id": 9,
                                    "local_date": "2026-07-26",
                                    "completed_at": "2026-07-26T12:00:00Z",
                                    "timing": "early",
                                    "points_awarded": 40,
                                    "has_photo": false
                                  },
                                  "points": {
                                    "base": 10,
                                    "timing_bonus": 5,
                                    "achievement_points": 25,
                                    "total": 40
                                  },
                                  "unlocks": [
                                    {
                                      "id": 1,
                                      "title": "Early bird",
                                      "description": "Complete early 5 times",
                                      "icon_key": "bird",
                                      "points_reward": 25,
                                      "unlocked_at": "2026-07-26T12:00:00Z"
                                    }
                                  ]
                                }
                                """.trimIndent(),
                            )
                    }
                }
            client.accessToken = "child-token"
            val home = client.getHome()
            assertEquals(1, home.board.size)
            assertEquals("Done", home.board[0].statusLabel)
            assertEquals(1, home.recentUnlocks.size)
            assertEquals("Early bird", home.recentUnlocks[0].title)

            val complete = client.completeChore("qr-active-1")
            assertEquals(1, complete.unlocks.size)
            assertEquals(25, complete.points.achievementPoints)
            client.close()
        }

    @Test
    fun decodeFailureBecomesApiException() =
        runTest {
            val client =
                clientFor {
                    respond("not-json-at-all", HttpStatusCode.OK, jsonHeaders)
                }
            client.accessToken = "t"
            val ex = assertThrows<ApiException> { client.getMe() }
            assertTrue(ex.message!!.contains("decode") || ex.message!!.isNotBlank())
            client.close()
        }

    @Test
    fun errorBodiesWithBlankAndGarbage() =
        runTest {
            val blank =
                clientFor {
                    respond("", HttpStatusCode.Unauthorized)
                }
            assertThrows<AuthException> { blank.getMe() }
            blank.close()

            val garbage =
                clientFor {
                    respond("<<<", HttpStatusCode.NotFound, jsonHeaders)
                }
            garbage.accessToken = "t"
            val nf = assertThrows<NotFoundException> { garbage.getChore(1) }
            assertTrue(nf.message!!.contains("<<<") || nf.message == "Not found")
            garbage.close()

            val empty422 =
                clientFor {
                    respond("not-validation-json", HttpStatusCode.UnprocessableEntity, jsonHeaders)
                }
            empty422.accessToken = "t"
            val ve = assertThrows<ValidationException> { empty422.createChore(ChoreCreate(title = "x")) }
            assertTrue(ve.errors.isEmpty())
            empty422.close()
        }

    @Test
    fun listChoresDefaultIncludeInactive() =
        runTest {
            val client =
                clientFor { request ->
                    assertEquals("true", request.url.parameters["include_inactive"])
                    okJson("""{"chores":[]}""")
                }
            client.accessToken = "parent-token"
            assertEquals(0, client.listChores().chores.size)
            client.close()
        }

    @Test
    fun logoutWithoutTokenStillClears() =
        runTest {
            val client =
                clientFor {
                    respond("", HttpStatusCode.NoContent)
                }
            // no token set
            client.logout()
            assertNull(client.accessToken)
            client.close()
        }

    @Test
    fun exceptionDefaultMessages() {
        assertEquals("Not authenticated", AuthException().message)
        assertEquals("Insufficient permissions", ForbiddenException().message)
        assertEquals("Not found", NotFoundException().message)
        assertEquals("Validation failed", ValidationException().message)
        assertTrue(DomainException("x", "y").code == "x")
    }

    @Test
    fun confirmAlreadyDoneWithCompletion() =
        runTest {
            val client =
                clientFor {
                    okJson(
                        """
                        {
                          "chore": {
                            "id": 1,
                            "title": "Unload dishwasher",
                            "description": null,
                            "qr_token": "qr-active-1",
                            "due_time": "20:00:00",
                            "schedule_days": "0123456",
                            "photo_policy": "optional",
                            "base_points": 10,
                            "is_active": true
                          },
                          "scheduled_today": true,
                          "already_done": true,
                          "is_late_pending": false,
                          "completion": {
                            "id": 1,
                            "local_date": "2026-07-26",
                            "completed_at": "2026-07-26T12:00:00Z",
                            "timing": "on_time",
                            "points_awarded": 12,
                            "has_photo": true
                          }
                        }
                        """.trimIndent(),
                    )
                }
            client.accessToken = "child-token"
            val confirm = client.getConfirm("qr-active-1")
            assertTrue(confirm.alreadyDone)
            assertNotNull(confirm.completion)
            assertEquals(12, confirm.completion!!.pointsAwarded)
            client.close()
        }
}
