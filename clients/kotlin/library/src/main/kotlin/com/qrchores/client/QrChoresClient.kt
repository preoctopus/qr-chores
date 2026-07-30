package com.qrchores.client

import com.qrchores.client.errors.ApiException
import com.qrchores.client.errors.AuthException
import com.qrchores.client.errors.DomainException
import com.qrchores.client.errors.ForbiddenException
import com.qrchores.client.errors.NotFoundException
import com.qrchores.client.errors.QrChoresException
import com.qrchores.client.errors.ValidationErrorItem
import com.qrchores.client.errors.ValidationException
import com.qrchores.client.models.Achievement
import com.qrchores.client.models.AchievementCreate
import com.qrchores.client.models.AchievementUpdate
import com.qrchores.client.models.AchievementsResponse
import com.qrchores.client.models.ChildCreate
import com.qrchores.client.models.ChildListResponse
import com.qrchores.client.models.ChildUpdate
import com.qrchores.client.models.Chore
import com.qrchores.client.models.ChoreConfirm
import com.qrchores.client.models.ChoreCreate
import com.qrchores.client.models.ChoreDeleteResponse
import com.qrchores.client.models.ChoreListResponse
import com.qrchores.client.models.ChoreUpdate
import com.qrchores.client.models.CompleteResponse
import com.qrchores.client.models.DomainDetailEnvelope
import com.qrchores.client.models.HistoryResponse
import com.qrchores.client.models.HomeResponse
import com.qrchores.client.models.LoginRequest
import com.qrchores.client.models.QrInfo
import com.qrchores.client.models.RewardsResponse
import com.qrchores.client.models.StringDetail
import com.qrchores.client.models.TimingBonuses
import com.qrchores.client.models.TodayResponse
import com.qrchores.client.models.TokenResponse
import com.qrchores.client.models.User
import com.qrchores.client.models.ValidationDetailEnvelope
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.HttpResponseValidator
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.accept
import io.ktor.client.request.bearerAuth
import io.ktor.client.request.delete
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.client.statement.readRawBytes
import io.ktor.http.ContentType
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive

/**
 * Android-compatible Kotlin client for the QR Chores internal `/api/v1` API.
 *
 * Uses Ktor Client. Default engine is CIO (fine for JVM tests and non-Android hosts).
 * Android apps should pass an OkHttp engine (see README).
 *
 * After [login], the access token is stored and sent as `Authorization: Bearer …`.
 * You may also set [accessToken] manually.
 *
 * Thread-safety: token field is `@Volatile`; prefer one client per session.
 */
class QrChoresClient(
    baseUrl: String,
    engine: HttpClientEngine? = null,
    private val json: Json = defaultJson,
    private val httpClient: HttpClient? = null,
) : AutoCloseable {
    private val baseUrl: String = baseUrl.trimEnd('/')

    @Volatile
    var accessToken: String? = null

    private val ownsClient: Boolean = httpClient == null

    private val client: HttpClient =
        httpClient ?: HttpClient(engine ?: CIO.create()) {
            expectSuccess = false
            install(ContentNegotiation) {
                json(json)
            }
            defaultRequest {
                accept(ContentType.Application.Json)
            }
            HttpResponseValidator {
                // We map statuses ourselves in [mapErrors]; leave empty.
            }
        }

    // --- Auth ---

    suspend fun login(
        email: String,
        password: String,
    ): TokenResponse {
        val response =
            client.post("$baseUrl/api/v1/auth/login") {
                contentType(ContentType.Application.Json)
                setBody(LoginRequest(email = email, password = password))
            }
        val body = response.decodeOrThrow<TokenResponse>()
        accessToken = body.accessToken
        return body
    }

    suspend fun logout() {
        try {
            val response =
                client.post("$baseUrl/api/v1/auth/logout") {
                    applyAuth()
                }
            // Logout is best-effort; 204 is success, 401 without token is ok.
            if (!response.status.isSuccess() && response.status != HttpStatusCode.Unauthorized) {
                throw mapError(response)
            }
        } finally {
            accessToken = null
        }
    }

    suspend fun getMe(): User =
        get("/api/v1/me")

    // --- Child ---

    suspend fun getHome(): HomeResponse =
        get("/api/v1/home")

    suspend fun getConfirm(qrToken: String): ChoreConfirm =
        get("/api/v1/c/${encodePath(qrToken)}")

    /**
     * Complete a chore by QR token.
     *
     * Optional photo is sent as multipart field `photo`.
     */
    suspend fun completeChore(
        qrToken: String,
        photoBytes: ByteArray? = null,
        photoFileName: String? = null,
        photoContentType: String? = null,
        notes: String? = null,
    ): CompleteResponse {
        val response =
            client.post("$baseUrl/api/v1/c/${encodePath(qrToken)}/complete") {
                applyAuth()
                if (photoBytes != null || notes != null) {
                    setBody(
                        MultiPartFormDataContent(
                            formData {
                                if (photoBytes != null) {
                                    val name = photoFileName ?: "photo.jpg"
                                    val ct = photoContentType ?: "image/jpeg"
                                    append(
                                        key = "photo",
                                        value = photoBytes,
                                        headers =
                                            Headers.build {
                                                append(HttpHeaders.ContentType, ct)
                                                append(
                                                    HttpHeaders.ContentDisposition,
                                                    "filename=\"$name\"",
                                                )
                                            },
                                    )
                                }
                                if (notes != null) {
                                    append(key = "notes", value = notes)
                                }
                            },
                        ),
                    )
                }
            }
        return response.decodeOrThrow()
    }

    suspend fun getAchievements(): AchievementsResponse =
        get("/api/v1/achievements")

    // --- Parent board ---

    suspend fun getToday(): TodayResponse =
        get("/api/v1/today")

    suspend fun getHistory(
        childId: Int? = null,
        choreId: Int? = null,
        startDate: String? = null,
        endDate: String? = null,
        timing: String? = null,
        page: Int = 1,
        limit: Int = 50,
    ): HistoryResponse =
        get("/api/v1/history") {
            parameter("limit", limit)
            parameter("page", page)
            if (childId != null) parameter("child_id", childId)
            if (choreId != null) parameter("chore_id", choreId)
            if (startDate != null) parameter("start_date", startDate)
            if (endDate != null) parameter("end_date", endDate)
            if (timing != null) parameter("timing", timing)
        }


    // --- Children ---

    suspend fun listChildren(includeInactive: Boolean = true): ChildListResponse =
        get("/api/v1/children") {
            parameter("include_inactive", includeInactive)
        }

    suspend fun createChild(body: ChildCreate): User {
        val response =
            client.post("$baseUrl/api/v1/children") {
                applyAuth()
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        return response.decodeOrThrow()
    }

    suspend fun getChild(childId: Int): User =
        get("/api/v1/children/$childId")

    suspend fun updateChild(
        childId: Int,
        body: ChildUpdate,
    ): User {
        val response =
            client.patch("$baseUrl/api/v1/children/$childId") {
                applyAuth()
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        return response.decodeOrThrow()
    }

    suspend fun activateChild(childId: Int): User {
        val response =
            client.post("$baseUrl/api/v1/children/$childId/activate") {
                applyAuth()
            }
        return response.decodeOrThrow()
    }

    suspend fun deactivateChild(childId: Int): User {
        val response =
            client.post("$baseUrl/api/v1/children/$childId/deactivate") {
                applyAuth()
            }
        return response.decodeOrThrow()
    }

    // --- Chores ---

    suspend fun listChores(includeInactive: Boolean = true): ChoreListResponse =
        get("/api/v1/chores") {
            parameter("include_inactive", includeInactive)
        }

    suspend fun createChore(body: ChoreCreate): Chore {
        val response =
            client.post("$baseUrl/api/v1/chores") {
                applyAuth()
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        return response.decodeOrThrow()
    }

    suspend fun getChore(choreId: Int): Chore =
        get("/api/v1/chores/$choreId")

    suspend fun updateChore(
        choreId: Int,
        body: ChoreUpdate,
    ): Chore {
        val response =
            client.patch("$baseUrl/api/v1/chores/$choreId") {
                applyAuth()
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        return response.decodeOrThrow()
    }

    suspend fun deleteChore(choreId: Int): ChoreDeleteResponse {
        val response =
            client.delete("$baseUrl/api/v1/chores/$choreId") {
                applyAuth()
            }
        return response.decodeOrThrow()
    }

    suspend fun activateChore(choreId: Int): Chore {
        val response =
            client.post("$baseUrl/api/v1/chores/$choreId/activate") {
                applyAuth()
            }
        return response.decodeOrThrow()
    }

    suspend fun deactivateChore(choreId: Int): Chore {
        val response =
            client.post("$baseUrl/api/v1/chores/$choreId/deactivate") {
                applyAuth()
            }
        return response.decodeOrThrow()
    }

    suspend fun getQrInfo(choreId: Int): QrInfo =
        get("/api/v1/chores/$choreId/qr")

    suspend fun getQrPng(choreId: Int): ByteArray {
        val response =
            client.get("$baseUrl/api/v1/chores/$choreId/qr.png") {
                applyAuth()
            }
        if (!response.status.isSuccess()) {
            throw mapError(response)
        }
        return response.readRawBytes()
    }

    // --- Rewards ---

    suspend fun getRewards(): RewardsResponse =
        get("/api/v1/rewards")

    suspend fun updateBonuses(bonuses: TimingBonuses): TimingBonuses {
        val response =
            client.put("$baseUrl/api/v1/rewards/bonuses") {
                applyAuth()
                contentType(ContentType.Application.Json)
                setBody(bonuses)
            }
        return response.decodeOrThrow()
    }

    suspend fun createAchievement(body: AchievementCreate): Achievement {
        val response =
            client.post("$baseUrl/api/v1/rewards/achievements") {
                applyAuth()
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        return response.decodeOrThrow()
    }

    suspend fun updateAchievement(
        achievementId: Int,
        body: AchievementUpdate,
    ): Achievement {
        val response =
            client.patch("$baseUrl/api/v1/rewards/achievements/$achievementId") {
                applyAuth()
                contentType(ContentType.Application.Json)
                setBody(body)
            }
        return response.decodeOrThrow()
    }

    suspend fun toggleAchievement(achievementId: Int): Achievement {
        val response =
            client.post("$baseUrl/api/v1/rewards/achievements/$achievementId/toggle") {
                applyAuth()
            }
        return response.decodeOrThrow()
    }

    // --- Photos ---

    suspend fun getPhoto(completionId: Int): ByteArray {
        val response =
            client.get("$baseUrl/api/v1/photos/$completionId") {
                applyAuth()
            }
        if (!response.status.isSuccess()) {
            throw mapError(response)
        }
        return response.readRawBytes()
    }

    override fun close() {
        if (ownsClient) {
            client.close()
        }
    }

    // --- Internals ---

    private suspend inline fun <reified T> get(
        path: String,
        crossinline block: HttpRequestBuilder.() -> Unit = {},
    ): T {
        val response =
            client.get("$baseUrl$path") {
                applyAuth()
                block()
            }
        return response.decodeOrThrow()
    }

    private fun HttpRequestBuilder.applyAuth() {
        val token = accessToken
        if (token != null) {
            bearerAuth(token)
        }
    }

    private suspend inline fun <reified T> HttpResponse.decodeOrThrow(): T {
        if (!status.isSuccess()) {
            throw mapError(this)
        }
        return try {
            body()
        } catch (e: QrChoresException) {
            throw e
        } catch (e: Exception) {
            throw ApiException(
                message = "Failed to decode response: ${e.message}",
                statusCode = status.value,
                cause = e,
            )
        }
    }

    private suspend fun mapError(response: HttpResponse): QrChoresException {
        val status = response.status
        val text =
            try {
                response.bodyAsText()
            } catch (_: Exception) {
                ""
            }

        return when (status.value) {
            401 -> AuthException(detailString(text) ?: "Not authenticated")
            403 -> ForbiddenException(detailString(text) ?: "Insufficient permissions")
            404 -> NotFoundException(detailString(text) ?: "Not found")
            400 -> {
                // CONTRACT: 400 → DomainException. Structured {message, code} when present;
                // plain string detail falls back to code "domain_error" (matches Python client).
                val domain = parseDomain(text)
                if (domain != null) {
                    DomainException(code = domain.code, message = domain.message.ifBlank { "Domain error" })
                } else {
                    DomainException(
                        code = "domain_error",
                        message = detailString(text) ?: "Bad request",
                    )
                }
            }
            422 -> {
                val items = parseValidation(text)
                ValidationException(
                    message = "Validation failed",
                    errors = items,
                )
            }
            else ->
                ApiException(
                    message = detailString(text) ?: "HTTP ${status.value}",
                    statusCode = status.value,
                )
        }
    }

    private fun detailString(text: String): String? {
        if (text.isBlank()) return null
        return try {
            json.decodeFromString(StringDetail.serializer(), text).detail
        } catch (_: Exception) {
            text.take(500)
        }
    }

    private fun parseDomain(text: String): DomainDetail? {
        if (text.isBlank()) return null
        return try {
            val env = json.decodeFromString(DomainDetailEnvelope.serializer(), text)
            val d = env.detail ?: return null
            DomainDetail(code = d.code, message = d.message)
        } catch (_: Exception) {
            null
        }
    }

    private fun parseValidation(text: String): List<ValidationErrorItem> {
        if (text.isBlank()) return emptyList()
        return try {
            val env = json.decodeFromString(ValidationDetailEnvelope.serializer(), text)
            env.detail.map { item ->
                ValidationErrorItem(
                    loc =
                        item.loc.map { el ->
                            when (el) {
                                is JsonPrimitive -> el.content
                                else -> el.toString()
                            }
                        },
                    msg = item.msg,
                    type = item.type,
                )
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    private fun encodePath(segment: String): String =
        // QR tokens are urlsafe; still encode reserved chars safely.
        java.net.URLEncoder.encode(segment, Charsets.UTF_8.name()).replace("+", "%20")

    private data class DomainDetail(
        val code: String,
        val message: String,
    )

    companion object {
        val defaultJson: Json =
            Json {
                ignoreUnknownKeys = true
                isLenient = true
                encodeDefaults = true
                explicitNulls = false
            }

        /**
         * Create a client with a custom Ktor engine (e.g. OkHttp on Android).
         */
        fun create(
            baseUrl: String,
            engine: HttpClientEngine,
        ): QrChoresClient = QrChoresClient(baseUrl = baseUrl, engine = engine)
    }
}
