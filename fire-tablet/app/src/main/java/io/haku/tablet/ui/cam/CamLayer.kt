package io.haku.tablet.ui.cam

import android.media.AudioManager
import android.media.MediaPlayer
import android.net.Uri
import android.widget.VideoView
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import io.haku.tablet.ui.logEvent
import io.haku.tablet.ui.theme.Haku
import io.haku.tablet.ui.theme.HakuType

/** The door camera on screen: the stream's HLS URL and what to call it (the sidecar's label). */
data class CamUi(val hls: String, val label: String)

/**
 * The door camera takeover, full screen over everything: the stream fitted 16:9 on black, muted, with the
 * label top left and "Connecting…" until the first frame. Any tap closes it ([onClose]); a player error
 * closes it too ([onFail]) rather than leave a black screen.
 *
 * A framework [VideoView], so no player library: it plays the stream server's H.264 HLS on API 30, and its
 * SurfaceView keeps video frames out of the app's own rendering. Muted with no audio focus, so it never
 * ducks anything else, and its error listener returns true so the system never shows a dialog.
 */
@Composable
fun CamLayer(cam: CamUi, onClose: () -> Unit, onFail: () -> Unit) {
    var playing by remember(cam) { mutableStateOf(false) }
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        key(cam.hls) {
            AndroidView(
                factory = { ctx ->
                    VideoView(ctx).apply {
                        setAudioFocusRequest(AudioManager.AUDIOFOCUS_NONE)
                        setOnPreparedListener { mp ->
                            mp.setVolume(0f, 0f)
                            mp.setOnInfoListener { _, what, _ ->
                                if (what == MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START) playing = true
                                false
                            }
                        }
                        setOnErrorListener { _, what, extra ->
                            logEvent("cam_error", "what=$what extra=$extra")
                            onFail()
                            true
                        }
                        setVideoURI(Uri.parse(cam.hls))
                        start()
                    }
                },
                onRelease = { it.stopPlayback() },
                modifier = Modifier.align(Alignment.Center).fillMaxWidth().aspectRatio(16f / 9f),
            )
        }
        Text(
            cam.label,
            style = HakuType.sub,
            color = Haku.ink,
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(16.dp)
                .background(Haku.night.copy(alpha = 0.6f), RoundedCornerShape(12.dp))
                .padding(horizontal = 14.dp, vertical = 8.dp),
        )
        if (!playing) {
            Text("Connecting…", style = HakuType.sub, color = Haku.inkMuted, modifier = Modifier.align(Alignment.Center))
        }
        // Last, so it takes every tap before the video sees it.
        Spacer(Modifier.fillMaxSize().clickable(interactionSource = null, indication = null, onClick = onClose))
    }
}
