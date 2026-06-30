package com.kyopenscience.astral.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import com.kyopenscience.astral.app.ui.theme.AstralTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { AstralRoot() }
    }
}

@Composable
private fun AstralRoot() {
    AstralTheme {
        Scaffold(modifier = Modifier.fillMaxSize()) { padding ->
            // Placeholder shell. The adaptive chat rail + SDUI canvas, transport,
            // and auth land in the Foundational/US1 phases (T014–T016, T019–T025).
            Text(text = "AstralBody", modifier = Modifier.padding(padding))
        }
    }
}
