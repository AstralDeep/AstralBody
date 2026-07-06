// Feature 051 — orchestrator WebSocket transport.
// Shared reconnect contract with Windows/Android (FR-005): backoff 1 s base,
// ×2 per attempt, 30 s cap, reset on success; bounded 64-frame outbound FIFO
// queue while disconnected with drop-oldest + a user-visible drop signal.
// The pure pieces (BackoffPolicy, BoundedQueue) are separated for testing.
import Foundation

public struct BackoffPolicy: Sendable {
    public let base: TimeInterval
    public let factor: Double
    public let cap: TimeInterval
    private(set) var attempt: Int = 0

    public init(base: TimeInterval = 1.0, factor: Double = 2.0, cap: TimeInterval = 30.0) {
        self.base = base
        self.factor = factor
        self.cap = cap
    }

    /// Delay for the NEXT reconnect attempt (1, 2, 4, … capped at 30).
    public mutating func next() -> TimeInterval {
        let delay = min(base * pow(factor, Double(attempt)), cap)
        attempt += 1
        return delay
    }

    public mutating func reset() { attempt = 0 }
}

public struct BoundedQueue<Element>: Sendable where Element: Sendable {
    public let limit: Int
    private(set) var elements: [Element] = []
    public private(set) var droppedCount: Int = 0

    public init(limit: Int = 64) {
        self.limit = limit
    }

    /// Append; drops the OLDEST element when full. Returns true if a drop
    /// occurred (surface it to the user — never drop silently).
    @discardableResult
    public mutating func append(_ element: Element) -> Bool {
        var dropped = false
        if elements.count >= limit {
            elements.removeFirst()
            droppedCount += 1
            dropped = true
        }
        elements.append(element)
        return dropped
    }

    public mutating func drainAll() -> [Element] {
        let out = elements
        elements = []
        return out
    }

    public var count: Int { elements.count }
}

public enum WSEvent: Sendable {
    case connected
    case disconnected(reason: String)
    case frame(InboundFrame)
    case sendDropped(total: Int)
}

/// URLSession-backed client. The app layer supplies the register_ui frame on
/// every (re)connect via `onConnect` and consumes `events`.
public actor WSClient {
    public let url: URL
    private var task: URLSessionWebSocketTask?
    private var backoff = BackoffPolicy()
    private var queue = BoundedQueue<String>(limit: 64)
    private var running = false
    private var continuation: AsyncStream<WSEvent>.Continuation?
    private var onConnect: (@Sendable () async -> String?)?

    public init(url: URL) {
        self.url = url
    }

    /// Event stream (single consumer). Call before `start()`.
    public func events() -> AsyncStream<WSEvent> {
        AsyncStream { continuation in
            self.continuation = continuation
        }
    }

    /// `onConnect` returns the register_ui frame to send first on every
    /// (re)connect (silent resume: `resumed: true` after the first).
    public func start(onConnect: @escaping @Sendable () async -> String?) {
        guard !running else { return }
        running = true
        self.onConnect = onConnect
        Task { await self.runLoop() }
    }

    public func stop() {
        running = false
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        continuation?.finish()
    }

    /// Send or queue (bounded) while disconnected.
    public func send(_ text: String) {
        if let task, task.state == .running {
            task.send(.string(text)) { _ in }
        } else {
            if queue.append(text) {
                continuation?.yield(.sendDropped(total: queue.droppedCount))
            }
        }
    }

    private func runLoop() async {
        while running {
            let session = URLSession(configuration: .default)
            let task = session.webSocketTask(with: url)
            self.task = task
            task.resume()

            if let register = await onConnect?() {
                task.send(.string(register)) { _ in }
            }
            backoff.reset()
            continuation?.yield(.connected)
            for frame in queue.drainAll() {
                task.send(.string(frame)) { _ in }
            }

            // Receive until failure/close.
            receive: while running {
                do {
                    let message = try await task.receive()
                    switch message {
                    case .string(let text):
                        if let frame = InboundFrame.parse(text) {
                            continuation?.yield(.frame(frame))
                        }
                    case .data(let data):
                        if let text = String(data: data, encoding: .utf8),
                           let frame = InboundFrame.parse(text) {
                            continuation?.yield(.frame(frame))
                        }
                    @unknown default:
                        break
                    }
                } catch {
                    continuation?.yield(.disconnected(reason: error.localizedDescription))
                    break receive
                }
            }
            self.task = nil
            guard running else { break }
            let delay = backoffNext()
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
        }
    }

    private func backoffNext() -> TimeInterval {
        backoff.next()
    }
}
