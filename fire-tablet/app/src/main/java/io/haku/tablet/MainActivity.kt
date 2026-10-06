package io.haku.tablet

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import io.haku.tablet.data.DemoSource
import io.haku.tablet.data.HubSource
import io.haku.tablet.data.SidecarClient
import io.haku.tablet.ui.Dashboard
import io.haku.tablet.ui.DashboardViewModel
import io.haku.tablet.ui.logEvent
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val vm: DashboardViewModel by viewModels {
        viewModelFactory { initializer { DashboardViewModel(pickSource()) } }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        // Draw over the Fire OS swipe lockscreen instead of sitting behind it after the screen sleeps.
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        hideSystemBars()
        setContent {
            val ui by vm.ui.collectAsStateWithLifecycle()
            Dashboard(
                ui, vm.freshness, vm.lastOkAt, vm.photo, vm.night,
                vm.peek, vm::startPeek, vm::endPeek, vm::stepPhoto,
                vm.detail, vm::openDetail, vm::closeDetail,
            )
        }
        // Dim the whole window during the config's night window; follow the system brightness otherwise.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                vm.night.collect { night ->
                    window.attributes = window.attributes.apply {
                        screenBrightness =
                            if (night) vm.nightBrightness else WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE
                    }
                }
            }
        }
    }

    /**
     * The sidecar, or in debug builds the canned demo states when launched with `--es demo <scenario>`
     * (quiet, busy, alert, cycle, degraded or offline). Backgrounds stay real either way. `--es demo_detail <name>`
     * picks the `detail_<id>_<name>.json` variant of a panel where there is one (weather: `tonight`, `nofc`).
     */
    private fun pickSource(): HubSource {
        val real = SidecarClient(BuildConfig.SIDECAR_BASE, BuildConfig.LAYOUT)
        val demo = if (BuildConfig.DEBUG) intent.getStringExtra("demo") else null
        logEvent("source", "demo=${demo ?: "none"}")
        val detailVariant = if (BuildConfig.DEBUG) intent.getStringExtra("demo_detail") else null
        return if (demo != null) {
            DemoSource({ assets.open(it).bufferedReader().use { r -> r.readText() } }, demo, real, detailVariant = detailVariant)
        } else {
            real
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemBars()   // re-hide after a transient swipe
    }

    private fun hideSystemBars() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }
}
