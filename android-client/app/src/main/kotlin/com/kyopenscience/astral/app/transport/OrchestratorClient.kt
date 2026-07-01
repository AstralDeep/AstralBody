package com.kyopenscience.astral.app.transport

import android.util.Log
import com.kyopenscience.astral.core.protocol.ChatAttachment
import com.kyopenscience.astral.core.protocol.DeviceCapabilities
import com.kyopenscience.astral.core.protocol.Inbound
import com.kyopenscience.astral.core.protocol.Wire
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
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
fun backoffDelayMs(attempt: Int, baseMs: Long = 1_000L, maxMs: Long = 30_000L): Long {
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
    @Volatile private var socket: WebSocket? = null
    @Volatile private var open = false
    private val pending = ArrayDeque<String>()
    private val _state = MutableStateFlow(ConnectionState.Disconnected)
    val state: StateFlow<ConnectionState> = _state.asStateFlow()

    /** Reconnecting inbound stream. Collect this for the life of the session. */
    fun stream(token: String, device: DeviceCapabilities, sessionId: String? = null): Flow<Inbound> =
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
        sessionId: String?,
        onOpen: () -> Unit,
    ): Flow<Inbound> =
        callbackFlow {
            _state.value = ConnectionState.Connecting
            val request = Request.Builder().url(url).build()
            val listener =
                object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) {
                        _state.value = ConnectionState.Connected
                        open = true
                        onOpen()
                        webSocket.send(Wire.encodeRegisterUi(token, sessionId, device))
                        flushPending(webSocket)
                    }

                    override fun onMessage(webSocket: WebSocket, text: String) {
                        val msg = Wire.decode(text)
                        if (msg is Inbound.AuthRequired) _state.value = ConnectionState.AuthRequired
                        trySend(msg)
                    }

                    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                        open = false
                        webSocket.close(NORMAL_CLOSE, null)
                        close()
                    }

                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
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
            while (pending.isNotEmpty()) webSocket.send(pending.removeFirst())
        }
    }

    private fun enqueueOrSend(frame: String) {
        val s = socket
        if (open && s != null) {
            s.send(frame)
        } else {
            synchronized(pending) {
                pending.addLast(frame)
                while (pending.size > MAX_QUEUE) pending.removeFirst()
            }
        }
    }

    fun sendChat(message: String, chatId: String?, attachments: List<ChatAttachment> = emptyList()) {
        enqueueOrSend(Wire.encodeChatMessage(message, chatId, attachments))
    }

    fun sendEvent(action: String, sessionId: String?, payload: JsonObject = JsonObject(emptyMap())) {
        enqueueOrSend(Wire.encodeUiEvent(action, sessionId, payload))
    }

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
