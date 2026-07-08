package com.personalailabs.astraldeep.app.transport

import kotlin.test.Test
import kotlin.test.assertEquals

class DeviceCapsTest {
    @Test
    fun builds_android_capabilities() {
        val caps = deviceCapabilities(widthPx = 1080, heightPx = 2340, pixelRatio = 2.75, supportedTypes = listOf("text", "card"))
        assertEquals("android", caps.deviceType)
        assertEquals(1080, caps.screenWidth)
        assertEquals(2340, caps.screenHeight)
        assertEquals(1080, caps.viewportWidth)
        assertEquals(2340, caps.viewportHeight)
        assertEquals(2.75, caps.pixelRatio)
        assertEquals(true, caps.hasTouch)
        assertEquals(listOf("text", "card"), caps.supportedTypes)
    }
}
