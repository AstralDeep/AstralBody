package com.personalailabs.astraldeep.app.transport

import android.util.Log
import com.personalailabs.astraldeep.core.protocol.ChatAttachment
import com.personalailabs.astraldeep.core.protocol.DeviceCapabilities
import com.personalailabs.astraldeep.core.protocol.Inbound
import com.personalailabs.astraldeep.core.protocol.Wire
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.emitAll
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.json.JsonObject
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

enum class ConnectionState { Connecting, Connected, Disconnected, AuthRequired }

/** Pure exponential backoff schedule (base·2^(attempt-1), capped). Unit-tested. */
fun backoffDelayMs(
    attempt: Int,
    baseMs: Long = 1_000L,
    maxMs: Long = 30_000L,
): Long {
    if (attempt <= 1) return baseMs
    val shift = (attempt - 1).coerceIn(0, 20)
    val raw = baseMs shl shift
    return if (raw <= 0L || raw > maxMs) maxMs else raw
}

/**
 * The WebSocket transport: connects to the orchestrator's `/ws`, sends
 * `register_ui` on open, decodes inbound frames via [Wire] into [Inbound], and
 * exposes them as a reconnecting cold [Flow]. [state] reflects the live
 * connection; reconnect uses [backoffDelayMs] (reset on each successful open).
 *
 * Outbound resilience (FR-012): frames sent while disconnected are queued (bounded)
 * and flushed on the next open, so user input is not lost across a blip; an
 * already-sent frame leaves the queue, so a reconnect does not resend it.
 */
class OrchestratorClient(
    private val url: String,
    private val client: OkHttpClient = defaultClient(),
) {
    /** An outbound frame queued while offline (its `action` kept for the drop notice). */
    private data class Queued(val action: String, val frame: String)

    @Volatile private var socket: WebSocket? = null

    @Volatile private var open = false
    private val pending = ArrayDeque<Queued>()
    private val _state = MutableStateFlow(ConnectionState.Disconnected)
    val state: StateFlow<ConnectionState> = _state.asStateFlow()

    private val _dropped = MutableSharedFlow<String>(extraBufferCapacity = 8, onBufferOverflow = BufferOverflow.DROP_OLDEST)

    /** The `action` of each frame dropped from the full offline queue — overflow is never silent (T014). */
    val dropped: SharedFlow<String> = _dropped.asSharedFlow()

    /**
     * Reconnecting inbound stream. Collect this for the life of the session.
     * [sessionId] is a provider, read at each (re)connect, so `register_ui`
     * always carries the chat active NOW — not the one open when the session
     * started (cross-device continuity, audit item 12).
     */
    fun stream(
        token: String,
        device: DeviceCapabilities,
        sessionId: () -> String? = { null },
    ): Flow<Inbound> =
        flow {
            var attempt = 0
            while (true) {
                emitAll(connectOnce(token, device, sessionId) { attempt = 0 })
                _state.value = ConnectionState.Disconnected
                attempt += 1
                delay(backoffDelayMs(attempt))
            }
        }

    private fun connectOnce(
        token: String,
        device: DeviceCapabilities,
        sessionId: () -> String?,
        onOpen: () -> Unit,
    ): Flow<Inbound> =
        callbackFlow {
            _state.value = ConnectionState.Connecting
            val request = Request.Builder().url(url).build()
            val listener =
                object : WebSocketListener() {
                    override fun onOpen(
                        webSocket: WebSocket,
                        response: Response,
                    ) {
                        // register_ui MUST be the first frame on the socket:
                        // only after it is enqueued may the offline queue flush
                        // and Connected-reactive sends (the reconnect load_chat
                        // refresh) flow, or the server would refuse them as
                        // unregistered.
                        webSocket.send(Wire.encodeRegisterUi(token, sessionId(), device))
                        open = true
                        onOpen()
                        flushPending(webSocket)
                        _state.value = ConnectionState.Connected
                    }

                    override fun onMessage(
                        webSocket: WebSocket,
                        text: String,
                    ) {
                        val msg = Wire.decode(text)
                        if (msg is Inbound.AuthRequired) _state.value = ConnectionState.AuthRequired
                        trySend(msg)
                    }

                    override fun onClosing(
                        webSocket: WebSocket,
                        code: Int,
                        reason: String,
                    ) {
                        open = false
                        webSocket.close(NORMAL_CLOSE, null)
                        close()
                    }

                    override fun onFailure(
                        webSocket: WebSocket,
                        t: Throwable,
                        response: Response?,
                    ) {
                        open = false
                        Log.w(TAG, "WebSocket failure: ${t.message}")
                        close()
                    }
                }
            socket = client.newWebSocket(request, listener)
            awaitClose {
                open = false
                socket?.cancel()
            }
        }

    private fun flushPending(webSocket: WebSocket) {
        synchronized(pending) {
            while (pending.isNotEmpty()) webSocket.send(pending.removeFirst().frame)
        }
    }

    private fun enqueueOrSend(
        action: String,
        frame: String,
    ) {
        val s = socket
        if (open && s != null) {
            s.send(frame)
        } else {
            val droppedActions = mutableListOf<String>()
            synchronized(pending) {
                pending.addLast(Queued(action, frame))
                while (pending.size > MAX_QUEUE) droppedActions.add(pending.removeFirst().action)
            }
            droppedActions.forEach { _dropped.tryEmit(it) }
        }
    }

    fun sendChat(
        message: String,
        chatId: String?,
        attachments: List<ChatAttachment> = emptyList(),
    ) {
        enqueueOrSend("chat_message", Wire.encodeChatMessage(message, chatId, attachments))
    }

    fun sendEvent(
        action: String,
        sessionId: String?,
        payload: JsonObject = JsonObject(emptyMap()),
    ) {
        enqueueOrSend(action, Wire.encodeUiEvent(action, sessionId, payload))
    }

    /** The actions currently queued offline — a test seam to assert what was (not) sent. */
    internal fun pendingActions(): List<String> = synchronized(pending) { pending.map { it.action } }

    companion object {
        private const val TAG = "OrchestratorClient"
        private const val NORMAL_CLOSE = 1000
        private const val MAX_QUEUE = 64

        private fun defaultClient(): OkHttpClient =
            OkHttpClient.Builder()
                .pingInterval(20, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.MILLISECONDS) // streaming socket
                .build()
    }
}
