package com.kyopenscience.astral.core.chrome

import com.kyopenscience.astral.core.protocol.Inbound
import com.kyopenscience.astral.core.protocol.Wire
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ChromeMenuTest {
    private val adminModel =
        """
        {"version":1,
         "topbar":[
           {"key":"brand","kind":"brand"},
           {"key":"status","kind":"status"},
           {"key":"pulse","kind":"action","label":"Pulse digest","icon":"sparkle","action":{"surface":"pulse","params":{}}},
           {"key":"timeline","kind":"action","label":"Workspace timeline","icon":"history","action":{"surface":"workspace_timeline","params":{}}},
           {"key":"settings","kind":"menu","label":"Settings","icon":"gear"}],
         "menu":[
           {"key":"account","label":"Account","admin_only":false,"items":[
             {"key":"agents","label":"Agents & permissions","surface":"agents","params":{},"admin_only":false},
             {"key":"llm","label":"LLM settings","surface":"llm","params":{},"admin_only":false},
             {"key":"personalization","label":"Personalization","surface":"personalization","params":{},"admin_only":false},
             {"key":"audit","label":"Audit log","surface":"audit","params":{},"admin_only":false},
             {"key":"theme","label":"Theme","surface":"theme","params":{},"admin_only":false}]},
           {"key":"help","label":"Help","admin_only":false,"items":[
             {"key":"tour","label":"Take the tour","surface":"tour","params":{},"admin_only":false},
             {"key":"guide","label":"User guide","surface":"guide","params":{},"admin_only":false}]},
           {"key":"admin","label":"Admin tools","admin_only":true,"items":[
             {"key":"tool-quality","label":"Tool quality","surface":"admin_tools","params":{"tab":"quality"},"admin_only":true},
             {"key":"tutorial-admin","label":"Tutorial admin","surface":"admin_tools","params":{"tab":"tutorial"},"admin_only":true}]}],
         "signout":{"key":"signout","label":"Sign out","style":"danger","action":"logout"}}
        """.trimIndent()

    private fun parse(s: String): JsonObject = Json.parseToJsonElement(s) as JsonObject

    @Test
    fun decodes_topbar_order_and_kinds() {
        val m = ChromeMenuModel.fromJson(parse(adminModel))!!
        assertEquals(listOf("brand", "status", "pulse", "timeline", "settings"), m.topbar.map { it.key })
        assertEquals(listOf("pulse", "timeline"), m.topbarActions.map { it.key })
        assertEquals("gear", m.settingsControl?.icon)
        val timeline = m.topbar.first { it.key == "timeline" }
        assertEquals("workspace_timeline", timeline.action?.surface)
        assertEquals("sparkle", m.topbar.first { it.key == "pulse" }.icon)
    }

    @Test
    fun decodes_groups_items_order_and_labels() {
        val m = ChromeMenuModel.fromJson(parse(adminModel))!!
        assertEquals(listOf("account", "help", "admin"), m.menu.map { it.key })
        assertEquals(
            listOf("agents", "llm", "personalization", "audit", "theme"),
            m.menu[0].items.map { it.key },
        )
        assertEquals("Agents & permissions", m.menu[0].items[0].label)
        assertEquals(listOf("tour", "guide"), m.menu[1].items.map { it.key })
        // admin group + params
        val adminGroup = m.menu[2]
        assertTrue(adminGroup.adminOnly)
        assertEquals("admin_tools", adminGroup.items[0].surface)
        assertEquals("quality", adminGroup.items[0].params["tab"]?.jsonPrimitive?.contentOrNull)
    }

    @Test
    fun signout_is_danger_logout() {
        val so = ChromeMenuModel.fromJson(parse(adminModel))!!.signout
        assertEquals("signout", so.key)
        assertEquals("Sign out", so.label)
        assertEquals("danger", so.style)
        assertEquals("logout", so.action)
    }

    @Test
    fun non_admin_model_has_no_admin_group() {
        val nonAdmin =
            """
            {"version":1,"topbar":[{"key":"brand","kind":"brand"},{"key":"settings","kind":"menu","icon":"gear"}],
             "menu":[{"key":"account","label":"Account","items":[{"key":"agents","label":"Agents & permissions","surface":"agents","params":{}}]},
                     {"key":"help","label":"Help","items":[]}],
             "signout":{"key":"signout","label":"Sign out","style":"danger","action":"logout"}}
            """.trimIndent()
        val m = ChromeMenuModel.fromJson(parse(nonAdmin))!!
        assertTrue(m.menu.none { it.key == "admin" })
        assertTrue(m.menu.none { it.adminOnly })
    }

    @Test
    fun tolerates_unknown_fields_and_missing_optionals() {
        val weird =
            """
            {"version":2,"future_field":"ignored",
             "topbar":[{"key":"settings","kind":"menu","icon":"gear","brand_new":true}],
             "menu":[{"key":"account","label":"Account","items":[
               {"key":"agents","label":"Agents & permissions","surface":"agents"}]}],
             "signout":{}}
            """.trimIndent()
        val m = ChromeMenuModel.fromJson(parse(weird))!!
        assertEquals(2, m.version)
        assertEquals("agents", m.menu[0].items[0].surface)
        assertEquals(JsonObject(emptyMap()), m.menu[0].items[0].params) // default when absent
        assertEquals("Sign out", m.signout.label) // defaults fill an empty signout
    }

    @Test
    fun chrome_open_payload_for_item_and_control() {
        val m = ChromeMenuModel.fromJson(parse(adminModel))!!
        val toolQuality = m.menu[2].items[0]
        val payload = toolQuality.chromeOpenPayload()
        assertEquals("admin_tools", payload["surface"]?.jsonPrimitive?.contentOrNull)
        assertEquals(
            "quality",
            (payload["params"] as JsonObject)["tab"]?.jsonPrimitive?.contentOrNull,
        )
        val timelinePayload = m.topbar.first { it.key == "timeline" }.chromeOpenPayload()
        assertEquals("workspace_timeline", timelinePayload["surface"]?.jsonPrimitive?.contentOrNull)
    }

    @Test
    fun wire_decodes_chrome_menu_frame() {
        val frame = """{"type":"chrome_menu","model":$adminModel}"""
        val inbound = Wire.decode(frame)
        val cm = assertIs<Inbound.ChromeMenu>(inbound)
        assertEquals(listOf("account", "help", "admin"), cm.model.menu.map { it.key })
    }

    @Test
    fun wire_chrome_menu_without_model_is_unknown() {
        val inbound = Wire.decode("""{"type":"chrome_menu"}""")
        assertIs<Inbound.Unknown>(inbound)
    }

    @Test
    fun fromJson_null_is_null() {
        assertNull(ChromeMenuModel.fromJson(null))
    }

    @Test
    fun data_class_defaults_are_exercised() {
        // Construct via defaults so the default-value expressions are covered.
        assertEquals(JsonObject(emptyMap()), SurfaceRef("pulse").params)
        val c = TopBarControl(key = "k", kind = "action")
        assertNull(c.label)
        assertNull(c.icon)
        assertNull(c.action)
        val item = MenuItem(key = "k", label = "L", surface = "s")
        assertEquals(JsonObject(emptyMap()), item.params)
        assertEquals(false, item.adminOnly)
        val group = MenuGroup(key = "k", label = "L")
        assertEquals(false, group.adminOnly)
        assertEquals(emptyList(), group.items)
        val so = SignOutItem()
        assertEquals("signout", so.key)
        assertEquals("Sign out", so.label)
        assertEquals("danger", so.style)
        assertEquals("logout", so.action)
    }

    @Test
    fun all_items_flattens_in_group_and_item_order() {
        val m = ChromeMenuModel.fromJson(parse(adminModel))!!
        assertEquals(
            listOf(
                "agents", "llm", "personalization", "audit", "theme",
                "tour", "guide", "tool-quality", "tutorial-admin",
            ),
            m.allItems.map { it.key },
        )
    }

    @Test
    fun chrome_open_payload_for_control_without_action_is_empty_surface() {
        val gear = ChromeMenuModel.fromJson(parse(adminModel))!!.settingsControl!!
        val payload = gear.chromeOpenPayload()
        assertEquals("", payload["surface"]?.jsonPrimitive?.contentOrNull)
        assertEquals(JsonObject(emptyMap()), payload["params"])
    }

    @Test
    fun malformed_entries_are_skipped_and_version_defaults() {
        // Missing version → defaults to 1; keyless topbar control, keyless group,
        // and items missing key/surface are all dropped; valid ones kept.
        val malformed =
            """
            {"topbar":[{"kind":"action"},{"key":"settings","kind":"menu"}],
             "menu":[{"label":"NoKeyGroup","items":[]},
                     {"key":"account","label":"Account","items":[
                        {"label":"no key"},
                        {"key":"nosurf","label":"no surface"},
                        {"key":"agents","label":"Agents & permissions","surface":"agents"}]}],
             "signout":{"key":"signout"}}
            """.trimIndent()
        val m = ChromeMenuModel.fromJson(parse(malformed))!!
        assertEquals(1, m.version) // absent → default
        assertEquals(listOf("settings"), m.topbar.map { it.key }) // keyless action dropped
        assertEquals(listOf("account"), m.menu.map { it.key }) // keyless group dropped
        assertEquals(listOf("agents"), m.menu[0].items.map { it.key }) // key/surface-less items dropped
        assertEquals("logout", m.signout.action) // default fills partial signout
    }
}
