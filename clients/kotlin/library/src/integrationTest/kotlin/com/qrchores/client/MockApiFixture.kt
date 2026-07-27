package com.qrchores.client

import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URI
import java.util.concurrent.TimeUnit
import org.junit.jupiter.api.extension.AfterAllCallback
import org.junit.jupiter.api.extension.BeforeAllCallback
import org.junit.jupiter.api.extension.ExtensionContext

/**
 * JUnit 5 extension that starts the shared mock-api on [PORT] if not already healthy,
 * and stops the process after the suite when we started it.
 */
class MockApiFixture :
    BeforeAllCallback,
    AfterAllCallback {
    companion object {
        const val PORT = 18080
        const val BASE_URL = "http://127.0.0.1:$PORT"

        private const val HEALTH = "$BASE_URL/healthz"
        private val storeKey = ExtensionContext.Namespace.create(MockApiFixture::class.java)
    }

    override fun beforeAll(context: ExtensionContext) {
        if (isHealthy()) {
            context.getStore(storeKey).put("owned", false)
            return
        }
        val process = startMockApi()
        context.getStore(storeKey).put("owned", true)
        context.getStore(storeKey).put("process", process)
        waitUntilHealthy(timeoutMs = 60_000)
    }

    override fun afterAll(context: ExtensionContext) {
        val owned = context.getStore(storeKey).get("owned") as? Boolean ?: false
        if (!owned) return
        val process = context.getStore(storeKey).get("process") as? Process ?: return
        process.destroy()
        if (!process.waitFor(5, TimeUnit.SECONDS)) {
            process.destroyForcibly()
        }
    }

    private fun isHealthy(): Boolean =
        try {
            val conn = URI(HEALTH).toURL().openConnection() as HttpURLConnection
            conn.connectTimeout = 1000
            conn.readTimeout = 1000
            conn.requestMethod = "GET"
            conn.responseCode == 200
        } catch (_: Exception) {
            false
        }

    private fun waitUntilHealthy(timeoutMs: Long) {
        val deadline = System.currentTimeMillis() + timeoutMs
        var lastError: Exception? = null
        while (System.currentTimeMillis() < deadline) {
            if (isHealthy()) return
            try {
                Thread.sleep(250)
            } catch (_: InterruptedException) {
                Thread.currentThread().interrupt()
                break
            }
        }
        // One more check with richer error
        try {
            val conn = URI(HEALTH).toURL().openConnection() as HttpURLConnection
            conn.connectTimeout = 2000
            conn.readTimeout = 2000
            if (conn.responseCode == 200) return
            lastError = IllegalStateException("healthz returned ${conn.responseCode}")
        } catch (e: Exception) {
            lastError = e
        }
        throw IllegalStateException(
            "mock-api did not become healthy on $HEALTH within ${timeoutMs}ms",
            lastError,
        )
    }

    private fun startMockApi(): Process {
        val repoRoot = findRepoRoot()
        val mockDir = File(repoRoot, "clients/mock-api")
        require(mockDir.isDirectory) { "mock-api not found at ${mockDir.absolutePath}" }

        // Ensure deps, then run uvicorn.
        val sync =
            ProcessBuilder("uv", "sync")
                .directory(mockDir)
                .redirectErrorStream(true)
                .start()
        val syncOut = sync.inputStream.bufferedReader().readText()
        if (!sync.waitFor(120, TimeUnit.SECONDS) || sync.exitValue() != 0) {
            throw IllegalStateException("uv sync failed: $syncOut")
        }

        val pb =
            ProcessBuilder(
                "uv",
                "run",
                "uvicorn",
                "qr_chores_mock_api.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                PORT.toString(),
            ).directory(mockDir)
                .redirectErrorStream(true)

        val process = pb.start()
        // Drain stdout in background so the process does not block on a full pipe.
        Thread {
            try {
                BufferedReader(InputStreamReader(process.inputStream)).use { reader ->
                    while (reader.readLine() != null) {
                        // discard (or could log)
                    }
                }
            } catch (_: Exception) {
                // process ended
            }
        }.apply {
            isDaemon = true
            name = "mock-api-stdout"
            start()
        }

        // Fail fast if process dies immediately
        Thread.sleep(300)
        if (!process.isAlive) {
            throw IllegalStateException("mock-api process exited early with ${process.exitValue()}")
        }
        return process
    }

    private fun findRepoRoot(): File {
        // Walk up from user.dir looking for clients/mock-api
        var dir = File(System.getProperty("user.dir")).absoluteFile
        repeat(8) {
            if (File(dir, "clients/mock-api").isDirectory) return dir
            // When running from clients/kotlin or clients/kotlin/library
            if (File(dir, "mock-api").isDirectory && dir.name == "clients") return dir.parentFile
            dir = dir.parentFile ?: return@repeat
        }
        // Fallback: clients/kotlin is two levels under repo root
        val fromKotlin = File(System.getProperty("user.dir")).absoluteFile
        val candidate = fromKotlin.parentFile?.parentFile
        if (candidate != null && File(candidate, "clients/mock-api").isDirectory) {
            return candidate
        }
        throw IllegalStateException(
            "Could not locate repo root with clients/mock-api from ${System.getProperty("user.dir")}",
        )
    }
}
