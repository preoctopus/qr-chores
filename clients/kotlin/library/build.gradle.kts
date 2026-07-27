import java.time.Duration
import kotlinx.kover.gradle.plugin.dsl.CoverageUnit

plugins {
    kotlin("jvm")
    kotlin("plugin.serialization")
    id("org.jetbrains.kotlinx.kover")
    `java-library`
    `maven-publish`
}

group = "com.qrchores"
version = "0.1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
    withSourcesJar()
}

kotlin {
    jvmToolchain(21)
}

val ktorVersion = "3.1.1"
val coroutinesVersion = "1.10.1"
val serializationVersion = "1.8.0"
val junitVersion = "5.11.4"

dependencies {
    api("io.ktor:ktor-client-core:$ktorVersion")
    api("io.ktor:ktor-client-content-negotiation:$ktorVersion")
    api("io.ktor:ktor-serialization-kotlinx-json:$ktorVersion")
    api("org.jetbrains.kotlinx:kotlinx-coroutines-core:$coroutinesVersion")
    api("org.jetbrains.kotlinx:kotlinx-serialization-json:$serializationVersion")

    // JVM default engine for tests and non-Android hosts.
    // Android apps should use ktor-client-okhttp instead (see README).
    implementation("io.ktor:ktor-client-cio:$ktorVersion")

    testImplementation("io.ktor:ktor-client-mock:$ktorVersion")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:$coroutinesVersion")
    testImplementation(platform("org.junit:junit-bom:$junitVersion"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

// Integration test source set (hits live mock-api).
val integrationTest = sourceSets.create("integrationTest") {
    compileClasspath += sourceSets["main"].output + configurations["testRuntimeClasspath"]
    runtimeClasspath += output + compileClasspath
}

configurations.named(integrationTest.implementationConfigurationName) {
    extendsFrom(configurations.testImplementation.get())
}
configurations.named(integrationTest.runtimeOnlyConfigurationName) {
    extendsFrom(configurations.testRuntimeOnly.get())
}

dependencies {
    add("integrationTestImplementation", sourceSets["test"].output)
    add("integrationTestImplementation", "io.ktor:ktor-client-cio:$ktorVersion")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
    testLogging {
        events("passed", "skipped", "failed")
    }
}

val integrationTestTask =
    tasks.register<Test>("integrationTest") {
        description = "Runs integration tests against mock-api (starts process if needed)."
        group = "verification"
        useJUnitPlatform()
        testClassesDirs = integrationTest.output.classesDirs
        classpath = integrationTest.runtimeClasspath
        shouldRunAfter(tasks.named("test"))
        testLogging {
            events("passed", "skipped", "failed")
            showStandardStreams = true
        }
        timeout.set(Duration.ofMinutes(5))
    }

tasks.named("check") {
    dependsOn(integrationTestTask)
}

kover {
    reports {
        filters {
            excludes {
                // Tests / fixture; kotlinx.serialization Companion objects are pure generated serializers.
                classes(
                    "*Test",
                    "*Test\$*",
                    "*Tests",
                    "*Tests\$*",
                    "*Fixture*",
                    "*Fixture\$*",
                    "*IntegrationTest*",
                    "*IntegrationTest\$*",
                    "*\$Companion",
                )
            }
        }
        total {
            xml {
                onCheck = true
            }
            html {
                onCheck = true
            }
            verify {
                rule {
                    minBound(90)
                    bound {
                        minValue = 90
                        coverageUnits = CoverageUnit.LINE
                    }
                }
            }
        }
    }
}

tasks.named("koverXmlReport") {
    dependsOn(integrationTestTask)
}
tasks.named("koverHtmlReport") {
    dependsOn(integrationTestTask)
}
tasks.named("koverVerify") {
    dependsOn(tasks.named("test"), integrationTestTask)
}

publishing {
    publications {
        create<MavenPublication>("maven") {
            from(components["java"])
            groupId = "com.qrchores"
            artifactId = "qr-chores-client"
            version = project.version.toString()
        }
    }
}
