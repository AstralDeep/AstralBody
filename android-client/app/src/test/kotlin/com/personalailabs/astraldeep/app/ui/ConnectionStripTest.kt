package com.personalailabs.astraldeep.app.ui

import com.personalailabs.astraldeep.app.transport.ConnectionState
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** Feature 044 T014 — the visible-reconnect strip's pure show/label rule. */
class ConnectionStripTest {
    @Test
    fun hidden_before_the_first_connect() {
        assertNull(connectionStripLabel(ConnectionState.Connecting, everConnected = false))
        assertNull(connectionStripLabel(ConnectionState.Disconnected, everConnected = false))
    }

    @Test
    fun hidden_while_connected() {
        assertNull(connectionStripLabel(ConnectionState.Connected, everConnected = true))
    }

    @Test
    fun reconnecting_after_a_drop() {
        assertEquals("Reconnecting…", connectionStripLabel(ConnectionState.Disconnected, everConnected = true))
        assertEquals("Reconnecting…", connectionStripLabel(ConnectionState.Connecting, everConnected = true))
    }

    @Test
    fun reauth_label_on_auth_required() {
        assertEquals("Re-authenticating…", connectionStripLabel(ConnectionState.AuthRequired, everConnected = true))
    }
}
