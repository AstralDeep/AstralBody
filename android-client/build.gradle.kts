// Root build for the AstralDeep Android client. Plugins are declared here
// (apply false) and applied per-module; see core/ and app/.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.compose.compiler) apply false
    alias(libs.plugins.kover) apply false
    alias(libs.plugins.ktlint) apply false
}
