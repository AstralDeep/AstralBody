package com.kyopenscience.astral.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.kyopenscience.astral.app.rest.AuditEvent
import com.kyopenscience.astral.app.ui.AgentsScreen
import com.kyopenscience.astral.app.ui.AuditScreen
import com.kyopenscience.astral.app.ui.HistoryScreen
import com.kyopenscience.astral.core.protocol.Agent
import com.kyopenscience.astral.core.protocol.ChatSummary
import org.junit.Rule
import org.junit.Test

/** US4 (T048): the management surfaces render their data. */
class SurfacesTest {
    @get:Rule val rule = createComposeRule()

    @Test
    fun agents_screen_lists_agent() {
        rule.setContent {
            AgentsScreen(
                agents = listOf(Agent("a1", "Weather", "Forecasts", false, mapOf("get_weather" to true))),
                onToggleAgent = { _, _ -> },
                onToggleTool = { _, _, _ -> },
                onEnableRecommended = {},
            )
        }
        rule.onNodeWithText("Weather").assertIsDisplayed()
    }

    @Test
    fun history_screen_lists_chat() {
        rule.setContent {
            HistoryScreen(listOf(ChatSummary("c1", "My chat")), onOpen = {})
        }
        rule.onNodeWithText("My chat").assertIsDisplayed()
    }

    @Test
    fun audit_screen_shows_event() {
        rule.setContent {
            AuditScreen(listOf(AuditEvent("e1", "auth", "login", "success", "2026-06-30")))
        }
        rule.onNodeWithText("auth · login").assertIsDisplayed()
    }
}
