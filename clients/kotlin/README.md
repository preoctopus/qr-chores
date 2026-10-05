# QR Chores — Kotlin client

Android-compatible Kotlin library for the QR Chores internal **`/api/v1`** API.

Pure **JVM** library (`kotlin("jvm")`) with Android-safe dependencies only. Use Ktor’s **OkHttp** engine in Android apps; unit tests use **CIO** + **MockEngine**.

Contract: [`../CONTRACT.md`](../CONTRACT.md) · Server docs: [`../../docs/API.md`](../../docs/API.md)

## Requirements

- **JDK 21** (Gradle toolchain; auto-download supported)
- Kotlin 2.x / Ktor 3.x

## Include in a Gradle project

### Composite / source dependency

```kotlin
// settings.gradle.kts
includeBuild("../path/to/qr-chores/clients/kotlin") {
    dependencySubstitution {
        substitute(module("com.qrchores:qr-chores-client")).using(project(":library"))
    }
}
```

```kotlin
// app/build.gradle.kts
dependencies {
    implementation("com.qrchores:qr-chores-client:0.1.0")
}
```

### Maven local

```bash
cd clients/kotlin
./gradlew :library:publishToMavenLocal
```

```kotlin
dependencies {
    implementation("com.qrchores:qr-chores-client:0.1.0")
}
```

### Android: OkHttp engine

```kotlin
// app/build.gradle.kts
dependencies {
    implementation("com.qrchores:qr-chores-client:0.1.0")
    implementation("io.ktor:ktor-client-okhttp:3.1.1")
}
```

```kotlin
import com.qrchores.client.QrChoresClient
import io.ktor.client.engine.okhttp.OkHttp

val client = QrChoresClient.create(
    baseUrl = "https://your-cloud-run-url.example",
    engine = OkHttp.create(),
)
```

## Usage

### Login (parent or child)

```kotlin
import com.qrchores.client.QrChoresClient
import com.qrchores.client.errors.AuthException

val client = QrChoresClient(baseUrl = "http://127.0.0.1:18080")

try {
    val session = client.login("child@example.com", "child-pass")
    println("Hello ${session.user.displayName}, balance=${session.user.pointsBalance}")
    // access token is stored on the client automatically
} catch (e: AuthException) {
    println("Login failed: ${e.message}")
}
```

### Child: home + complete with photo

```kotlin
val home = client.getHome()
println("Today ${home.localDate}: ${home.doneCount}/${home.totalCount}")

val confirm = client.getConfirm("qr-photo-required")
if (!confirm.alreadyDone) {
    val result = client.completeChore(
        qrToken = "qr-photo-required",
        photoBytes = jpegOrPngBytes,
        photoFileName = "proof.jpg",
        photoContentType = "image/jpeg",
    )
    println("Awarded ${result.points.total} points")
}
```

### Parent: create chore

```kotlin
import com.qrchores.client.models.ChoreCreate

client.login("parent@example.com", "parent-pass")

val chore = client.createChore(
    ChoreCreate(
        title = "Feed the cat",
        description = "Dry food bowl",
        dueTime = "08:00:00",
        scheduleDays = "0123456",
        photoPolicy = "optional",
        basePoints = 5,
    ),
)
println("QR token: ${chore.qrToken}")
val png = client.getQrPng(chore.id)
// print / share png bytes
```

### Error types

| HTTP | Exception |
|------|-----------|
| 401 | `AuthException` |
| 403 | `ForbiddenException` |
| 404 | `NotFoundException` |
| 400 domain | `DomainException(code, message)` |
| 422 | `ValidationException` |
| other | `ApiException` |

All extend `QrChoresException`.

### API surface (camelCase)

`login`, `logout`, `getMe`, `getHome`, `getConfirm`, `completeChore`, `getAchievements`, `getToday`, `getHistory`, `getHistoryDays`, `listChildren`, `createChild`, `getChild`, `updateChild`, `activateChild`, `deactivateChild`, `listChores`, `createChore`, `getChore`, `updateChore`, `deleteChore`, `activateChore`, `deactivateChore`, `getQrInfo`, `getQrPng`, `getRewards`, `updateBonuses`, `createAchievement`, `updateAchievement`, `toggleAchievement`, `getPhoto`

Wire JSON is **snake_case**; models use `@SerialName`.

## Tests

### Prerequisites

- JDK 21
- `uv` on `PATH` (integration tests start `clients/mock-api`)

### Run

```bash
cd clients/kotlin
export JAVA_HOME=$(/usr/libexec/java_home -v 21 2>/dev/null || echo /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home)
./gradlew test integrationTest koverVerify
```

- **Unit tests** (`./gradlew test`): Ktor `MockEngine`, no network.
- **Integration tests** (`./gradlew integrationTest`): start mock-api on `127.0.0.1:18080` if needed (fixture: `parent@example.com` / `parent-pass`, `child@example.com` / `child-pass`).
- **Coverage**: Kover line coverage **≥ 90%** (`koverVerify`).

HTML report: `library/build/reports/kover/html/index.html`

### Manual mock-api

```bash
cd clients/mock-api
uv sync
uv run uvicorn qr_chores_mock_api.app:app --host 127.0.0.1 --port 18080
```

## Layout

```text
clients/kotlin/
  library/
    src/main/kotlin/com/qrchores/client/
      QrChoresClient.kt
      models/
      errors/
    src/test/kotlin/…          # MockEngine unit tests
    src/integrationTest/kotlin/… # live mock-api tests
  README.md
```

## Notes

- Tokens are opaque bearer strings; store them in Keystore / EncryptedSharedPreferences in production apps.
- Prefer **deactivate** over **delete** unless you intend to wipe history and photos.
- Points are always server-awarded — do not invent scores client-side.
