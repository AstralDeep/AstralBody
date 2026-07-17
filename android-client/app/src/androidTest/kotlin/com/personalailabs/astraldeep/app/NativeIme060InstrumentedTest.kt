package com.personalailabs.astraldeep.app

import android.accessibilityservice.AccessibilityService
import android.provider.Settings
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.test.platform.app.InstrumentationRegistry
import com.personalailabs.astraldeep.app.render.Emit
import com.personalailabs.astraldeep.app.render.Renderer
import com.personalailabs.astraldeep.app.render.renderers.registerAllRenderers
import com.personalailabs.astraldeep.app.rest.AstralRest
import com.personalailabs.astraldeep.app.transport.OrchestratorClient
import com.personalailabs.astraldeep.app.ui.AdaptiveShell
import com.personalailabs.astraldeep.app.ui.AppViewModel
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/** Emulator proof that the shipping composer delegates dismissal to Android's native IME. */
class NativeIme060InstrumentedTest {
    @get:Rule val rule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun composer_uses_the_native_ime_without_an_app_drawn_done_overlay() {
        val vm =
            AppViewModel(
                OrchestratorClient("ws://localhost:9/ws"),
                AstralRest("http://localhost:9"),
            )
        rule.setContent {
            AdaptiveShell(vm, Renderer(Emit { _, _ -> }).registerAllRenderers())
        }

        val composer = rule.onNode(hasSetTextAction(), useUnmergedTree = true)
        composer.performClick().assertIsFocused().performTextInput("native keyboard")

        rule.waitUntil(timeoutMillis = 5_000) { nativeImeVisible() }
        val imePackage = defaultImePackage()
        assertNotNull("Android must configure a native input method", imePackage)
        assertNotEquals(targetPackage(), imePackage)
        rule.onAllNodesWithText("Done", useUnmergedTree = true).assertCountEquals(0)
        Log.i(TAG, "native_ime_package=$imePackage app_done_nodes=0")

        assertTrue(
            "Android system Back must dismiss the native IME",
            instrumentation().uiAutomation.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK),
        )
        rule.waitUntil(timeoutMillis = 5_000) { !nativeImeVisible() }
        composer.assertIsFocused()
        Log.i(TAG, "native_ime_dismissed=true composer_focus_retained=true")
    }

    private fun nativeImeVisible(): Boolean {
        val rootInsets = ViewCompat.getRootWindowInsets(rule.activity.window.decorView)
        return rootInsets?.isVisible(WindowInsetsCompat.Type.ime()) == true
    }

    private fun defaultImePackage(): String? =
        Settings.Secure
            .getString(instrumentation().targetContext.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
            ?.substringBefore('/')

    private fun targetPackage(): String = instrumentation().targetContext.packageName

    private fun instrumentation() = InstrumentationRegistry.getInstrumentation()

    private companion object {
        const val TAG = "NativeIme060"
    }
}
