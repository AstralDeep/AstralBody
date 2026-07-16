// Feature 051 — the client model of the server-owned chrome (top bar + settings
// menu), a 1:1 port of the Android `ChromeMenu.kt` (Constitution XII: one
// server-owned definition, every client is a thin consumer). Decoded from the
// `chrome_menu` WS frame; tolerant of unknown fields.
import Foundation

public struct SurfaceRef: Equatable, Sendable {
    public let surface: String
    public let params: JSONValue
    public init(surface: String, params: JSONValue = .object([:])) {
        self.surface = surface
        self.params = params
    }
}

/// One top-bar control. `kind` is brand|status|action|menu.
public struct TopBarControl: Equatable, Sendable, Identifiable {
    public let key: String
    public let kind: String
    public let label: String?
    public let icon: String?
    public let action: SurfaceRef?
    public var id: String { key }
}

/// One selectable Settings entry.
public struct ChromeMenuItem: Equatable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let surface: String
    public let params: JSONValue
    public let adminOnly: Bool
    public var id: String { key }
}

/// A labeled, ordered group of items (ACCOUNT / HELP / ADMIN TOOLS).
public struct ChromeMenuGroup: Equatable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let adminOnly: Bool
    public let items: [ChromeMenuItem]
    public var id: String { key }
}

/// The always-last, visually-distinct (red) sign-out entry.
public struct SignOutItem: Equatable, Sendable {
    public let key: String
    public let label: String
    public let style: String
    public let action: String
    public init(
        key: String = "signout", label: String = "Sign out",
        style: String = "danger", action: String = "logout"
    ) {
        self.key = key
        self.label = label
        self.style = style
        self.action = action
    }
}

/// The complete chrome description a client renders.
public struct ChromeMenuModel: Equatable, Sendable {
    public let version: Int
    public let topbar: [TopBarControl]
    public let menu: [ChromeMenuGroup]
    public let signout: SignOutItem

    /// Interactive top-bar controls (pulse/timeline) in order.
    public var topbarActions: [TopBarControl] { topbar.filter { $0.kind == "action" } }
    /// The Settings gear control, if present.
    public var settingsControl: TopBarControl? { topbar.first { $0.kind == "menu" } }
    /// Every menu item flattened, in order.
    public var allItems: [ChromeMenuItem] { menu.flatMap(\.items) }

    /// Decode from the `model` object of a `chrome_menu` frame (or the REST body).
    public static func fromJSON(_ root: JSONValue?) -> ChromeMenuModel? {
        guard let root else { return nil }
        let topbar: [TopBarControl] = (root["topbar"]?.arrayValue ?? []).compactMap { el in
            guard let key = el["key"]?.stringValue else { return nil }
            var action: SurfaceRef?
            if let a = el["action"], a.objectValue != nil {
                action = SurfaceRef(
                    surface: a["surface"]?.stringValue ?? "",
                    params: a["params"] ?? .object([:]))
            }
            return TopBarControl(
                key: key, kind: el["kind"]?.stringValue ?? "action",
                label: el["label"]?.stringValue, icon: el["icon"]?.stringValue,
                action: action)
        }
        let menu: [ChromeMenuGroup] = (root["menu"]?.arrayValue ?? []).compactMap { g in
            guard let key = g["key"]?.stringValue else { return nil }
            let items: [ChromeMenuItem] = (g["items"]?.arrayValue ?? []).compactMap { i in
                guard let ik = i["key"]?.stringValue, let surface = i["surface"]?.stringValue else { return nil }
                return ChromeMenuItem(
                    key: ik, label: i["label"]?.stringValue ?? "",
                    surface: surface, params: i["params"] ?? .object([:]),
                    adminOnly: i["admin_only"]?.boolValue ?? false)
            }
            return ChromeMenuGroup(
                key: key, label: g["label"]?.stringValue ?? "",
                adminOnly: g["admin_only"]?.boolValue ?? false, items: items)
        }
        let so = root["signout"]
        let signout = SignOutItem(
            key: so?["key"]?.stringValue ?? "signout",
            label: so?["label"]?.stringValue ?? "Sign out",
            style: so?["style"]?.stringValue ?? "danger",
            action: so?["action"]?.stringValue ?? "logout")
        return ChromeMenuModel(
            version: Int(root["version"]?.numberValue ?? 1),
            topbar: topbar, menu: menu, signout: signout)
    }
}

extension ChromeMenuItem {
    /// The `chrome_open` payload ({surface, params}).
    public var chromeOpenPayload: [String: JSONValue] {
        ["surface": .string(surface), "params": params]
    }
}

extension TopBarControl {
    /// The `chrome_open` payload ({surface, params}) for an interactive control.
    public var chromeOpenPayload: [String: JSONValue] {
        ["surface": .string(action?.surface ?? ""), "params": action?.params ?? .object([:])]
    }
}
