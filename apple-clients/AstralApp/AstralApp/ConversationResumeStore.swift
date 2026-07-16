import AstralCore
import Foundation

/// The only events allowed to erase a durable conversation locator.
enum ConversationResumeClearReason: Sendable {
    case newChat
    case signOut
    case accountRemoval
    case confirmedDeletion
}

/// Account-scoped, non-secret active-chat persistence for iOS and macOS.
///
/// The value is intentionally only a locator. Transcript, canvas, tokens, and
/// server URLs remain outside this store; the server re-authorizes and
/// hydrates the chat after every launch or reconnect.
final class ConversationResumeStore: @unchecked Sendable {
    private let defaults: UserDefaults
    private let now: @Sendable () -> Date

    init(
        defaults: UserDefaults = .standard,
        now: @escaping @Sendable () -> Date = Date.init
    ) {
        self.defaults = defaults
        self.now = now
    }

    @discardableResult
    func save(chatId: String, for account: ConversationAccount) -> Bool {
        guard conversationUUID4(chatId) else { return false }
        let locator = ConversationResumeLocator(
            chatId: chatId,
            updatedAt: Self.timestamp(now()))
        guard let data = try? JSONEncoder().encode(locator),
            let encoded = String(data: data, encoding: .utf8)
        else { return false }
        defaults.set(encoded, forKey: account.locatorStorageKey)
        return defaults.string(forKey: account.locatorStorageKey) == encoded
    }

    func load(for account: ConversationAccount) -> ConversationResumeLocator? {
        guard let encoded = defaults.string(forKey: account.locatorStorageKey),
            let data = encoded.data(using: .utf8),
            let value = try? JSONValue.parse(data),
            let object = value.objectValue,
            Set(object.keys) == ["schema_version", "chat_id", "updated_at"],
            object["schema_version"]?.numberValue == 1,
            let chatId = object["chat_id"]?.stringValue,
            conversationUUID4(chatId),
            let updatedAt = object["updated_at"]?.stringValue,
            Self.validTimestamp(updatedAt)
        else { return nil }
        return ConversationResumeLocator(chatId: chatId, updatedAt: updatedAt)
    }

    /// Unknown or malformed schemas are retained for forward compatibility.
    /// Confirmed deletion is additionally fenced to the stored chat id.
    @discardableResult
    func clear(
        _ reason: ConversationResumeClearReason,
        for account: ConversationAccount,
        chatId: String? = nil
    ) -> Bool {
        let key = account.locatorStorageKey
        guard defaults.object(forKey: key) != nil else { return false }
        if reason == .confirmedDeletion {
            guard let chatId, load(for: account)?.chatId == chatId else { return false }
        }
        defaults.removeObject(forKey: key)
        return defaults.object(forKey: key) == nil
    }

    private static func timestamp(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.string(from: date)
    }

    private static func validTimestamp(_ value: String) -> Bool {
        value.hasSuffix("Z") && ISO8601DateFormatter().date(from: value) != nil
    }
}

private func conversationUUID4(_ value: String) -> Bool {
    value.range(
        of: "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        options: .regularExpression) != nil && UUID(uuidString: value) != nil
}
