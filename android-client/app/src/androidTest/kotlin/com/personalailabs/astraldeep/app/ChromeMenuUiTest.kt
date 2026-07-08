package com.personalailabs.astraldeep.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.personalailabs.astraldeep.app.ui.SettingsMenu
import com.personalailabs.astraldeep.app.ui.theme.AstralTheme
import com.personalailabs.astraldeep.core.chrome.ChromeMenuModel
import com.personalailabs.astraldeep.core.chrome.MenuGroup
import com.personalailabs.astraldeep.core.chrome.MenuItem
import com.personalailabs.astraldeep.core.chrome.SignOutItem
import com.personalailabs.astraldeep.core.chrome.TopBarControl
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

/**
 * Feature 042 — the Settings dropdown renders the server-owned menu model
 * natively, matching the web exactly. Auth-free: drives [SettingsMenu] with a
 * model directly (the app otherwise needs real Keycloak to receive the model).
 */
class ChromeMenuUiTest {
    @get:Rule val rule = createComposeRule()

    // An admin model (so ADMIN TOOLS is present) mirroring GET /api/chrome/menu.
    private val adminModel =
        ChromeMenuModel(
            version = 1,
            topbar =
                listOf(
                    TopBarControl("brand", "brand"),
                    TopBarControl("timeline", "action", label = "Workspace timeline", icon = "history"),
                    TopBarControl("settings", "menu", label = "Settings", icon = "gear"),
                ),
            menu =
                listOf(
                    MenuGroup(
                        "account",
                        "Account",
                        items =
                            listOf(
                                MenuItem("agents", "Agents & permissions", "agents"),
                                MenuItem("llm", "LLM settings", "llm"),
                                MenuItem("personalization", "Personalization", "personalization"),
                                MenuItem("audit", "Audit log", "audit"),
                                MenuItem("theme", "Theme", "theme"),
                            ),
                    ),
                    MenuGroup(
                        "help",
                        "Help",
                        items =
                            listOf(
                                MenuItem("tour", "Take the tour", "tour"),
                                MenuItem("guide", "User guide", "guide"),
                            ),
                    ),
                    MenuGroup(
                        "admin",
                        "Admin tools",
                        adminOnly = true,
                        items =
                            listOf(
                                MenuItem("tool-quality", "Tool quality", "admin_tools"),
                                MenuItem("tutorial-admin", "Tutorial admin", "admin_tools"),
                            ),
                    ),
                ),
            signout = SignOutItem(),
        )

    @Test
    fun dropdown_shows_all_model_items_matching_the_web() {
        rule.setContent {
            AstralTheme {
                SettingsMenu(model = adminModel, onOpenItem = {}, onSignOut = {})
            }
        }
        rule.onNodeWithContentDescription("Settings").performClick()
        // ACCOUNT + HELP + ADMIN TOOLS items + red Sign out — the exact web set.
        listOf(
            "Agents & permissions", "LLM settings", "Personalization", "Audit log", "Theme",
            "Take the tour", "User guide",
            "Tool quality", "Tutorial admin",
            "Sign out",
        ).forEach { rule.onNodeWithText(it).assertIsDisplayed() }
    }

    @Test
    fun tapping_an_item_invokes_the_callback_with_its_surface() {
        var opened: MenuItem? = null
        rule.setContent {
            AstralTheme {
                SettingsMenu(model = adminModel, onOpenItem = { opened = it }, onSignOut = {})
            }
        }
        rule.onNodeWithContentDescription("Settings").performClick()
        rule.onNodeWithText("Audit log").performClick()
        rule.runOnIdle { assertEquals("audit", opened?.surface) }
    }

    @Test
    fun sign_out_invokes_the_callback() {
        var signedOut = false
        rule.setContent {
            AstralTheme {
                SettingsMenu(model = adminModel, onOpenItem = {}, onSignOut = { signedOut = true })
            }
        }
        rule.onNodeWithContentDescription("Settings").performClick()
        rule.onNodeWithText("Sign out").performClick()
        rule.runOnIdle { assertEquals(true, signedOut) }
    }
}
