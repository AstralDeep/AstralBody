// :core — pure Kotlin (no Android). Protocol decode, SDUI model, streaming
// consumer, and REST shaping live here so they are JVM-unit-testable without an
// emulator (FR-016). Kover enforces the changed-code coverage gate.
plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.kover)
    alias(libs.plugins.ktlint)
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.core)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(kotlin("test"))
}

tasks.test {
    useJUnit()
}

kover {
    reports {
        verify {
            rule {
                // Constitution III — keep module coverage at the gate. CI also
                // runs changed-code coverage; this guards the pure-logic core.
                minBound(90)
            }
        }
    }
}
