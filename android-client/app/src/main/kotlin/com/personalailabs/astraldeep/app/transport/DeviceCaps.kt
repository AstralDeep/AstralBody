package com.personalailabs.astraldeep.app.transport

import com.personalailabs.astraldeep.core.protocol.DeviceCapabilities

/**
 * Build the [DeviceCapabilities] reported in `register_ui`. Pure (takes raw
 * metrics) so it is JVM-unit-testable; the Activity supplies real screen metrics
 * and the renderer registry supplies [supportedTypes] (the natively-renderable
 * primitive set ROTE negotiates against). `device_type` is always "android".
 */
fun deviceCapabilities(
    widthPx: Int,
    heightPx: Int,
    pixelRatio: Double,
    supportedTypes: List<String>,
): DeviceCapabilities =
    DeviceCapabilities(
        screenWidth = widthPx,
        screenHeight = heightPx,
        viewportWidth = widthPx,
        viewportHeight = heightPx,
        pixelRatio = pixelRatio,
        hasTouch = true,
        supportedTypes = supportedTypes,
        deviceType = "android",
    )
