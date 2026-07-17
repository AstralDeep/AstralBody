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

// Spec 060 T126 (Constitution V): immutable supply chain. Plugin artifacts
// resolve on the root buildscript classpath; lock them so the plugin graph is
// reproducible. Regenerate with:
//   sh ./gradlew --write-locks <android-ci task set> --no-daemon
buildscript {
    configurations.getByName("classpath") {
        resolutionStrategy.activateDependencyLocking()
    }
}

// Lock every lockable configuration in every module (gradle.lockfile per
// project). Verification metadata (gradle/verification-metadata.xml, sha256)
// independently pins artifact digests for everything resolved, plugins
// included.
allprojects {
    dependencyLocking {
        lockAllConfigurations()
    }
}
