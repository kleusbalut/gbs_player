package io.github.kleusbalut.gbsplayer.android

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.SystemClock
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class PlaybackSnapshot(
    val title: String,
    val author: String,
    val trackNumber: Int,
    val trackName: String,
    val playing: Boolean,
    val paused: Boolean,
    val elapsedSeconds: Int,
    val durationSeconds: Int,
    val repeatMode: Int,
    val debugText: String = "",
) {
    val statusLabel: String
        get() = when {
            playing -> "Playing"
            paused -> "Paused"
            else -> "Stopped"
        }
}

class EmulatorSession(private val installedRom: InstalledRom) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _snapshot = MutableStateFlow(initialSnapshot())
    private val _framePixels = MutableStateFlow(IntArray(FRAME_PIXELS))
    private var handle: Long = 0L
    private var audioTrack: AudioTrack? = null
    private var audioJob: Job? = null
    private var statusJob: Job? = null
    private var frameJob: Job? = null
    private var lastFrameToken = -1
    @Volatile
    private var uiVisible = false
    @Volatile
    private var lastKnownPlaying = false
    @Volatile
    private var lastKnownPaused = false
    @Volatile
    private var lastInteractionMs = SystemClock.elapsedRealtime()
    @Volatile
    private var lastAudioBatchFrames = 0
    @Volatile
    private var audioUnderrunCount = 0
    @Volatile
    private var maxAudioFillMs = 0L
    @Volatile
    private var maxAudioWriteMs = 0L

    val snapshot: StateFlow<PlaybackSnapshot> = _snapshot
    val framePixels: StateFlow<IntArray> = _framePixels

    fun start() {
        if (handle != 0L) return

        handle = NativeBridge.nativeCreate(
            installedRom.romFile.absolutePath,
            installedRom.saveFile.absolutePath,
        )
        NativeBridge.nativeSetRenderingEnabled(handle, false)

        val minBuffer = AudioTrack.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_OUT_STEREO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        audioTrack = AudioTrack(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build(),
            AudioFormat.Builder()
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                .setSampleRate(SAMPLE_RATE)
                .build(),
            maxOf(minBuffer, BACKGROUND_AUDIO_BATCH * CHANNELS * 2 * 2),
            AudioTrack.MODE_STREAM,
            AudioManager.AUDIO_SESSION_ID_GENERATE,
        ).apply {
            play()
        }

        audioJob = scope.launch {
            val pcm = ShortArray(BACKGROUND_AUDIO_BATCH * CHANNELS)
            var audioSuspended = false
            while (isActive) {
                if (shouldHibernateInBackground()) {
                    if (!audioSuspended) {
                        audioTrack?.pause()
                        audioTrack?.flush()
                        audioSuspended = true
                    }
                    delay(BACKGROUND_IDLE_SLEEP_MS)
                    continue
                }
                if (audioSuspended) {
                    audioTrack?.play()
                    audioSuspended = false
                }
                val localHandle = handle
                if (localHandle == 0L) break
                val batchFrames = if (uiVisible) FOREGROUND_AUDIO_BATCH else BACKGROUND_AUDIO_BATCH
                lastAudioBatchFrames = batchFrames
                val fillStart = SystemClock.elapsedRealtimeNanos()
                val frames = NativeBridge.nativeFillAudio(localHandle, pcm, batchFrames)
                val fillMs = (SystemClock.elapsedRealtimeNanos() - fillStart) / 1_000_000L
                if (fillMs > maxAudioFillMs) {
                    maxAudioFillMs = fillMs
                }
                if (frames <= 0) {
                    delay(2)
                    continue
                }
                val writeStart = SystemClock.elapsedRealtimeNanos()
                audioTrack?.write(pcm, 0, frames * CHANNELS, AudioTrack.WRITE_BLOCKING)
                val writeMs = (SystemClock.elapsedRealtimeNanos() - writeStart) / 1_000_000L
                if (writeMs > maxAudioWriteMs) {
                    maxAudioWriteMs = writeMs
                }
                audioUnderrunCount = audioTrack?.underrunCount ?: audioUnderrunCount
            }
        }

        statusJob = scope.launch {
            while (isActive) {
                refreshSnapshot(includeDebug = uiVisible)
                delay(if (uiVisible) FOREGROUND_STATUS_DELAY_MS else BACKGROUND_STATUS_DELAY_MS)
            }
        }
    }

    fun tapKey(key: Int) {
        val localHandle = handle
        if (localHandle == 0L) return
        noteInteraction()
        NativeBridge.nativeTapButton(localHandle, key)
        refreshSnapshot(includeDebug = uiVisible)
    }

    fun setKeyPressed(key: Int, pressed: Boolean) {
        val localHandle = handle
        if (localHandle == 0L) return
        if (pressed) {
            noteInteraction()
        }
        NativeBridge.nativeSetButton(localHandle, key, pressed)
    }

    fun sendCommand(command: Int, argument: Int = 0) {
        val localHandle = handle
        if (localHandle == 0L) return
        noteInteraction()
        NativeBridge.nativeSendCommand(localHandle, command, argument)
    }

    fun setUiVisible(visible: Boolean) {
        if (uiVisible == visible) return
        uiVisible = visible
        if (visible) {
            noteInteraction()
        }
        val localHandle = handle
        if (localHandle == 0L) return
        NativeBridge.nativeSetRenderingEnabled(localHandle, visible)
        if (visible) {
            startFrameLoop()
            refreshSnapshot(includeDebug = true)
        } else {
            stopFrameLoop()
        }
    }

    fun close() {
        audioJob?.cancel()
        statusJob?.cancel()
        stopFrameLoop()
        audioTrack?.pause()
        audioTrack?.flush()
        audioTrack?.release()
        audioTrack = null
        val localHandle = handle
        if (localHandle != 0L) {
            NativeBridge.nativeDestroy(localHandle)
            handle = 0L
        }
    }

    fun flushSave() {
        val localHandle = handle
        if (localHandle != 0L) {
            NativeBridge.nativeFlushSave(localHandle)
        }
    }

    private fun refreshSnapshot(includeDebug: Boolean) {
        val localHandle = handle
        if (localHandle == 0L) return
        val status = NativeBridge.nativeGetStatus(localHandle)
        if (status.size < 6) return
        val songIndex = status[0].coerceAtLeast(0)
        val track = installedRom.metadata.songs.getOrNull(songIndex)
        lastKnownPlaying = status[1] != 0
        lastKnownPaused = status[2] != 0
        val debugText = if (includeDebug) buildDebugText(localHandle) else ""
        _snapshot.value = PlaybackSnapshot(
            title = installedRom.metadata.title,
            author = installedRom.metadata.author,
            trackNumber = track?.number ?: songIndex + 1,
            trackName = track?.name ?: "Track ${songIndex + 1}",
            playing = lastKnownPlaying,
            paused = lastKnownPaused,
            elapsedSeconds = status[3].coerceAtLeast(0),
            durationSeconds = status[4].coerceAtLeast(0),
            repeatMode = status[5].coerceIn(0, 2),
            debugText = debugText,
        )
    }

    private fun buildDebugText(localHandle: Long): String {
        val debug = NativeBridge.nativeGetDebugState(localHandle)
        if (debug.size < 11) return ""
        return "magic=%02X frame=%d song=%d flags=%02X px=%08X pc=%04X sp=%04X af=%04X boot=%d lcdc=%02X aud=%d under=%d fillMax=%dms writeMax=%dms".format(
            debug[0] and 0xFF,
            debug[4],
            debug[1],
            debug[2] and 0xFF,
            debug[5],
            debug[6] and 0xFFFF,
            debug[7] and 0xFFFF,
            debug[8] and 0xFFFF,
            debug[9],
            debug[10] and 0xFF,
            lastAudioBatchFrames,
            audioUnderrunCount,
            maxAudioFillMs,
            maxAudioWriteMs,
        )
    }

    private fun startFrameLoop() {
        if (frameJob != null) return
        lastFrameToken = -1
        frameJob = scope.launch {
            while (isActive) {
                val localHandle = handle
                if (localHandle == 0L) break
                val token = NativeBridge.nativeGetFrameToken(localHandle)
                if (token != lastFrameToken) {
                    val pixels = IntArray(FRAME_PIXELS)
                    NativeBridge.nativeCopyFrame(localHandle, pixels)
                    _framePixels.value = pixels
                    lastFrameToken = token
                }
                delay(FRAME_POLL_DELAY_MS)
            }
        }
    }

    private fun stopFrameLoop() {
        frameJob?.cancel()
        frameJob = null
    }

    private fun shouldHibernateInBackground(): Boolean {
        if (uiVisible) return false
        if (lastKnownPlaying) {
            noteInteraction()
            return false
        }
        if (SystemClock.elapsedRealtime() - lastInteractionMs < BACKGROUND_IDLE_TIMEOUT_MS) {
            return false
        }
        return !refreshCachedPlaybackState()
    }

    private fun refreshCachedPlaybackState(): Boolean {
        val localHandle = handle
        if (localHandle == 0L) return false
        val status = NativeBridge.nativeGetStatus(localHandle)
        if (status.size < 3) return lastKnownPlaying
        lastKnownPlaying = status[1] != 0
        lastKnownPaused = status[2] != 0
        if (lastKnownPlaying) {
            noteInteraction()
        }
        return lastKnownPlaying
    }

    private fun noteInteraction() {
        lastInteractionMs = SystemClock.elapsedRealtime()
    }

    private fun initialSnapshot(): PlaybackSnapshot {
        val firstTrack = installedRom.metadata.songs.firstOrNull()
        return PlaybackSnapshot(
            title = installedRom.metadata.title,
            author = installedRom.metadata.author,
            trackNumber = firstTrack?.number ?: 1,
            trackName = firstTrack?.name ?: "Track 1",
            playing = false,
            paused = false,
            elapsedSeconds = 0,
            durationSeconds = 0,
            repeatMode = 0,
            debugText = "",
        )
    }

    companion object {
        const val GB_KEY_RIGHT = 0
        const val GB_KEY_LEFT = 1
        const val GB_KEY_UP = 2
        const val GB_KEY_DOWN = 3
        const val GB_KEY_A = 4
        const val GB_KEY_B = 5
        const val GB_KEY_SELECT = 6
        const val GB_KEY_START = 7

        const val CMD_TOGGLE = 1
        const val CMD_STOP = 2
        const val CMD_NEXT = 3
        const val CMD_PREV = 4
        const val CMD_REPEAT = 6

        const val SCREEN_WIDTH = 160
        const val SCREEN_HEIGHT = 144

        private const val SAMPLE_RATE = 48_000
        private const val CHANNELS = 2
        private const val FOREGROUND_AUDIO_BATCH = 1024
        private const val BACKGROUND_AUDIO_BATCH = 2048
        private const val FRAME_PIXELS = SCREEN_WIDTH * SCREEN_HEIGHT
        private const val FRAME_POLL_DELAY_MS = 16L
        private const val FOREGROUND_STATUS_DELAY_MS = 200L
        private const val BACKGROUND_STATUS_DELAY_MS = 1000L
        private const val BACKGROUND_IDLE_TIMEOUT_MS = 300_000L
        private const val BACKGROUND_IDLE_SLEEP_MS = 500L
    }
}
