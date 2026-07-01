package com.kyopenscience.astral.app.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// Shared shimmering skeleton placeholders — the loading state for the canvas
// (while a query is answered) and for the list surfaces (while their data loads).

/** Base tone for the placeholder blocks (clearly above the near-black bg). */
private val SkeletonShade = Color(0xFF313A5C)

/** The pulsing alpha every skeleton placeholder shares. */
@Composable
internal fun shimmerAlpha(): Float {
    val transition = rememberInfiniteTransition(label = "skeleton")
    val alpha by transition.animateFloat(
        initialValue = 0.5f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(850), RepeatMode.Reverse),
        label = "alpha",
    )
    return alpha
}

@Composable
internal fun SkeletonBlock(
    alpha: Float,
    heightDp: Int,
    widthFraction: Float = 1f,
) {
    Box(
        modifier =
            Modifier
                .fillMaxWidth(widthFraction)
                .heightIn(min = heightDp.dp, max = heightDp.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(SkeletonShade.copy(alpha = alpha)),
    )
}

/** Canvas placeholder: a heading over a few large cards, until the first SDUI commits. */
@Composable
internal fun SkeletonCanvas(modifier: Modifier = Modifier) {
    val alpha = shimmerAlpha()
    Column(modifier = modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        SkeletonBlock(alpha, 28, 0.55f)
        SkeletonBlock(alpha, 120, 1f)
        SkeletonBlock(alpha, 92, 1f)
        SkeletonBlock(alpha, 150, 1f)
        SkeletonBlock(alpha, 40, 0.4f)
    }
}

/** Row placeholders for the list surfaces (agents / history / audit) while they load. */
@Composable
internal fun SkeletonList(
    modifier: Modifier = Modifier,
    rows: Int = 6,
    rowHeightDp: Int = 74,
) {
    val alpha = shimmerAlpha()
    Column(
        modifier = modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        repeat(rows) { SkeletonBlock(alpha, rowHeightDp, 1f) }
    }
}
