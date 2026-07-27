package com.qrchores.client.errors

/**
 * Base type for all QR Chores API failures.
 *
 * Map from HTTP status:
 * - 401 → [AuthException]
 * - 403 → [ForbiddenException]
 * - 404 → [NotFoundException]
 * - 400 with `{detail: {message, code}}` → [DomainException]
 * - 422 → [ValidationException]
 * - other / network → [ApiException]
 */
sealed class QrChoresException(
    message: String,
    cause: Throwable? = null,
) : Exception(message, cause)

/** Missing/invalid credentials or bad login (HTTP 401). */
class AuthException(
    message: String = "Not authenticated",
    cause: Throwable? = null,
) : QrChoresException(message, cause)

/** Authenticated but wrong role (HTTP 403). */
class ForbiddenException(
    message: String = "Insufficient permissions",
    cause: Throwable? = null,
) : QrChoresException(message, cause)

/** Resource not found (HTTP 404). */
class NotFoundException(
    message: String = "Not found",
    cause: Throwable? = null,
) : QrChoresException(message, cause)

/**
 * Domain rule violation on complete (HTTP 400).
 *
 * Common codes: `photo_required`, `photo_invalid`, `photo_too_large`, `not_scheduled`.
 */
class DomainException(
    val code: String,
    message: String,
    cause: Throwable? = null,
) : QrChoresException(message, cause)

/** Request validation failure (HTTP 422). */
class ValidationException(
    message: String = "Validation failed",
    val errors: List<ValidationErrorItem> = emptyList(),
    cause: Throwable? = null,
) : QrChoresException(message, cause)

/** Single FastAPI-style validation error entry. */
data class ValidationErrorItem(
    val loc: List<String> = emptyList(),
    val msg: String = "",
    val type: String = "",
)

/**
 * Catch-all for unexpected status codes, transport failures, or parse errors.
 */
class ApiException(
    message: String,
    val statusCode: Int? = null,
    cause: Throwable? = null,
) : QrChoresException(message, cause)
