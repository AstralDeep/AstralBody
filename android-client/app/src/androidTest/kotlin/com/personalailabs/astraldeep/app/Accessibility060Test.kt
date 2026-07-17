package com.personalailabs.astraldeep.app

import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performSemanticsAction
import com.personalailabs.astraldeep.app.ui.AgentsScreen
import com.personalailabs.astraldeep.core.protocol.Agent
import org.junit.Rule
import org.junit.Test

/** Spec 060 TalkBack semantics for every changed Android authoring control. */
class Accessibility060Test {
    @get:Rule val rule = createComposeRule()

    private val weather =
        Agent(
            id = "weather",
            name = "Weather",
            description = "Forecasts",
            isPublic = false,
            scopes = emptyMap(),
            tools = listOf("get_weather"),
            permissions = mapOf("get_weather" to false),
        )

    private fun render() {
        rule.setContent {
            AgentsScreen(
                agents = listOf(weather),
                loading = false,
                onToggleAgent = { _, _ -> },
                onToggleTool = { _, _, _ -> },
                onEnableRecommended = {},
            )
        }
    }

    @Test
    fun agent_switch_has_stable_name_role_state_action_and_focus() {
        render()
        val switch = rule.onNodeWithTag("agent-toggle:weather", useUnmergedTree = true)

        switch
            .assert(
                SemanticsMatcher.expectValue(
                    SemanticsProperties.ContentDescription,
                    listOf("Enable Weather agent"),
                ),
            ).assert(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Switch))
            .assert(
                SemanticsMatcher.expectValue(
                    SemanticsProperties.ToggleableState,
                    ToggleableState.Off,
                ),
            ).assert(
                SemanticsMatcher.expectValue(
                    SemanticsProperties.StateDescription,
                    "Disabled",
                ),
            ).assertHasClickAction()

        switch.performSemanticsAction(SemanticsActions.RequestFocus).assertIsFocused()
    }

    @Test
    fun expanded_tool_switch_has_stable_name_role_state_action_and_focus() {
        render()
        rule.onNodeWithText("Weather", substring = true).performClick()
        val switch =
            rule.onNodeWithTag(
                "agent-tool-toggle:weather:get_weather",
                useUnmergedTree = true,
            )

        switch
            .assert(
                SemanticsMatcher.expectValue(
                    SemanticsProperties.ContentDescription,
                    listOf("Enable get_weather for Weather"),
                ),
            ).assert(SemanticsMatcher.expectValue(SemanticsProperties.Role, Role.Switch))
            .assert(
                SemanticsMatcher.expectValue(
                    SemanticsProperties.ToggleableState,
                    ToggleableState.Off,
                ),
            ).assert(
                SemanticsMatcher.expectValue(
                    SemanticsProperties.StateDescription,
                    "Disabled",
                ),
            ).assertHasClickAction()

        switch.performSemanticsAction(SemanticsActions.RequestFocus).assertIsFocused()
    }
}
