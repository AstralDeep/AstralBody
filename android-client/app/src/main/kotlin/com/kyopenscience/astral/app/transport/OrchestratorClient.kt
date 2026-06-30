package com.kyopenscience.astral.app.transport

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

/**
 * The WebSocket transport: connects to the orchestrator's `/ws`, sends
 * `register_ui` on open, decodes inbound frames via [Wire] into [Inbound], and
 * exposes them as a cold [Flow]. [stream] reconnects automatically; [state]
 * reflects the live connection state. Outbound `ui_event`/`chat_message` go
 * through [sendChat] / [sendEvent].
 *
 * The reconnect here is a simple fixed-delay loop; richer backoff + "no
 * duplicate sends / no lost input" hardening lands in Polish (T049).
 */
class OrchestratorClient(
    private val url: String,
    private val client: OkHttpClient = defaultClient(),
) {
    @Volatile private var socket: WebSocket? = null
    private val _state = MutableStateFlow(ConnectionState.Disconnected)
    val state: StateFlow<ConnectionState> = _state.asStateFlow()

    /** Reconnecting inbound stream. Collect this for the life of the session. */
    fun stream(token: String, device: DeviceCapabilities, sessionId: String? = null): Flow<Inbound> =
        flow {
            while (true) {
                emitAll(connectOnce(token, device, sessionId))
                // connectOnce completes when the socket closes/fails; back off and retry.
                _state.value = ConnectionState.Disconnected
                delay(RECONNECT_DELAY_MS)
            }
        }

    private fun connectOnce(token: String, device: DeviceCapabilities, sessionId: String?): Flow<Inbound> =
        callbackFlow {
            _state.value = ConnectionState.Connecting
            val request = Request.Builder().url(url).build()
            val listener =
                object : WebSocketListener() {
                    override fun onOpen(webSocket: WebSocket, response: Response) {
                        _state.value = ConnectionState.Connected
                        webSocket.send(Wire.encodeRegisterUi(token, sessionId, device))
                    }

                    override fun onMessage(webSocket: WebSocket, text: String) {
                        val msg = Wire.decode(text)
                        if (msg is Inbound.AuthRequired) _state.value = ConnectionState.AuthRequired
                        trySend(msg)
                    }

                    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                        webSocket.close(NORMAL_CLOSE, null)
                        close()
                    }

                    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                        close()
                    }
                }
            socket = client.newWebSocket(request, listener)
            awaitClose { socket?.cancel() }
        }

    fun sendChat(message: String, chatId: String?) {
        socket?.send(Wire.encodeChatMessage(message, chatId))
    }

    fun sendEvent(action: String, sessionId: String?, payload: JsonObject = JsonObject(emptyMap())) {
        socket?.send(Wire.encodeUiEvent(action, sessionId, payload))
    }

    companion object {
        private const val NORMAL_CLOSE = 1000
        private const val RECONNECT_DELAY_MS = 2_000L

        private fun defaultClient(): OkHttpClient =
            OkHttpClient.Builder()
                .pingInterval(20, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.MILLISECONDS) // streaming socket
                .build()
    }
}
