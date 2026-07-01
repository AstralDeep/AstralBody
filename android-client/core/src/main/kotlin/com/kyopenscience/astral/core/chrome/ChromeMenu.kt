package com.kyopenscience.astral.core.chrome

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put

/**
 * Feature 042 — the client-side model of the server-owned chrome (top bar +
 * settings menu). Decoded from the `chrome_menu` WS frame (and identical to
 * `GET /api/chrome/menu`). The Android app renders its chrome from THIS — it
 * never hard-codes the menu (Constitution XII: one server-owned definition,
 * every client is a thin consumer).
 *
 * Pure Kotlin (no Android) so it is JVM-unit-tested under `:core` (Kover ≥90%).
 * Tolerant of unknown fields so an older client degrades gracefully rather than
 * failing on a newer server model.
 */
data class SurfaceRef(val surface: String, val params: JsonObject = JsonObject(emptyMap()))

/** One top-bar control. [kind] is brand|status|action|menu. */
data class TopBarControl(
    val key: String,
    val kind: String,
    val label: String? = null,
    val icon: String? = null,
    val action: SurfaceRef? = null,
)

/** One selectable Settings entry. */
data class MenuItem(
    val key: String,
    val label: String,
    val surface: String,
    val params: JsonObject = JsonObject(emptyMap()),
    val adminOnly: Boolean = false,
)

/** A labeled, ordered group of items (ACCOUNT / HELP / ADMIN TOOLS). */
data class MenuGroup(
    val key: String,
    val label: String,
    val adminOnly: Boolean = false,
    val items: List<MenuItem> = emptyList(),
)

/** The always-last, visually-distinct (red) sign-out entry. */
data class SignOutItem(
    val key: String = "signout",
    val label: String = "Sign out",
    val style: String = "danger",
    val action: String = "logout",
)

/** The complete chrome description a client renders. */
data class ChromeMenuModel(
    val version: Int,
    val topbar: List<TopBarControl>,
    val menu: List<MenuGroup>,
    val signout: SignOutItem,
) {
    /** Interactive top-bar controls (pulse/timeline) in order. */
    val topbarActions: List<TopBarControl> get() = topbar.filter { it.kind == "action" }

    /** The Settings gear control, if present. */
    val settingsControl: TopBarControl? get() = topbar.firstOrNull { it.kind == "menu" }

    /** Every menu item flattened, in order (for tests / flat clients). */
    val allItems: List<MenuItem> get() = menu.flatMap { it.items }

    companion object {
        /** Decode from the `model` object of a `chrome_menu` frame (or the REST body). */
        fun fromJson(root: JsonObject?): ChromeMenuModel? {
            if (root == null) return null
            val topbar =
                root.arr("topbar")?.mapNotNull { el ->
                    val o = el as? JsonObject ?: return@mapNotNull null
                    val key = o.str("key") ?: return@mapNotNull null
                    TopBarControl(
                        key = key,
                        kind = o.str("kind") ?: "action",
                        label = o.str("label"),
                        icon = o.str("icon"),
                        action =
                            o.obj("action")?.let {
                                SurfaceRef(it.str("surface").orEmpty(), it.obj("params") ?: JsonObject(emptyMap()))
                            },
                    )
                }.orEmpty()
            val menu =
                root.arr("menu")?.mapNotNull { el ->
                    val g = el as? JsonObject ?: return@mapNotNull null
                    val key = g.str("key") ?: return@mapNotNull null
                    MenuGroup(
                        key = key,
                        label = g.str("label").orEmpty(),
                        adminOnly = g.bool("admin_only") ?: false,
                        items =
                            g.arr("items")?.mapNotNull { ie ->
                                val i = ie as? JsonObject ?: return@mapNotNull null
                                val ik = i.str("key") ?: return@mapNotNull null
                                val surface = i.str("surface") ?: return@mapNotNull null
                                MenuItem(
                                    key = ik,
                                    label = i.str("label").orEmpty(),
                                    surface = surface,
                                    params = i.obj("params") ?: JsonObject(emptyMap()),
                                    adminOnly = i.bool("admin_only") ?: false,
                                )
                            }.orEmpty(),
                    )
                }.orEmpty()
            val so = root.obj("signout")
            val signout =
                SignOutItem(
                    key = so?.str("key") ?: "signout",
                    label = so?.str("label") ?: "Sign out",
                    style = so?.str("style") ?: "danger",
                    action = so?.str("action") ?: "logout",
                )
            return ChromeMenuModel(
                version = root.int("version") ?: 1,
                topbar = topbar,
                menu = menu,
                signout = signout,
            )
        }

        private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.contentOrNull

        private fun JsonObject.int(k: String): Int? = (this[k] as? JsonPrimitive)?.intOrNull

        private fun JsonObject.bool(k: String): Boolean? = (this[k] as? JsonPrimitive)?.booleanOrNull

        private fun JsonObject.arr(k: String): JsonArray? = this[k] as? JsonArray

        private fun JsonObject.obj(k: String): JsonObject? = this[k] as? JsonObject
    }
}

/** The `chrome_open` payload ({surface, params}) for a menu item. */
fun MenuItem.chromeOpenPayload(): JsonObject =
    buildJsonObject {
        put("surface", surface)
        put("params", params)
    }

/** The `chrome_open` payload ({surface, params}) for an interactive top-bar control. */
fun TopBarControl.chromeOpenPayload(): JsonObject =
    buildJsonObject {
        put("surface", action?.surface.orEmpty())
        put("params", action?.params ?: JsonObject(emptyMap()))
    }
