package io.github.kleusbalut.gbsplayer.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import androidx.core.app.NotificationCompat
import androidx.media.app.NotificationCompat.MediaStyle
import androidx.media.session.MediaButtonReceiver.handleIntent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class PlaybackService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var mediaSession: MediaSessionCompat
    private lateinit var session: EmulatorSession
    private var observerJob: Job? = null
    private var lastNotificationSignature: String? = null
    private var lastPlaybackState: Int? = null
    private var lastPlaybackPositionMs: Long = Long.MIN_VALUE
    private var lastRepeatMode: Int? = null
    private var lastObservedPlaying = false
    private var lastObservedPaused = false
    private var lastMediaPauseMs = Long.MIN_VALUE

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(AppLocale.apply(newBase))
    }

    override fun onCreate() {
        super.onCreate()
        createChannel()
        val createdSession = ensureCurrentSession()
        if (createdSession == null || !::mediaSession.isInitialized) {
            stopSelf()
            return
        }
        startForeground(NOTIFICATION_ID, buildNotification(createdSession.snapshot.value))
    }

    private fun ensureCurrentSession(): EmulatorSession? {
        val current = EmulatorRepository.currentSession() ?: EmulatorRepository.getOrCreate(this)
        if (current == null) return null
        if (::session.isInitialized && session === current && ::mediaSession.isInitialized) {
            return current
        }
        observerJob?.cancel()
        lastNotificationSignature = null
        lastPlaybackState = null
        lastPlaybackPositionMs = Long.MIN_VALUE
        lastRepeatMode = null
        lastObservedPlaying = false
        lastObservedPaused = false
        lastMediaPauseMs = Long.MIN_VALUE
        latestSnapshot.value = null
        session = current
        if (!::mediaSession.isInitialized) {
            createMediaSession()
        }
        startObserver(current)
        return current
    }

    private fun createMediaSession() {
        mediaSession = MediaSessionCompat(this, "gbs-player").apply {
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onPlay() = resumeFromMediaSession()
                override fun onPause() = pauseFromMediaSession()
                override fun onSkipToNext() = session.sendCommand(EmulatorSession.CMD_NEXT)
                override fun onSkipToPrevious() = session.sendCommand(EmulatorSession.CMD_PREV)
                override fun onSetRepeatMode(repeatMode: Int) {
                    session.sendCommand(EmulatorSession.CMD_REPEAT, mapAndroidRepeatToRom(repeatMode))
                }
                override fun onCustomAction(action: String?, extras: Bundle?) {
                    if (action == ACTION_REPEAT) {
                        cycleRepeatMode()
                    }
                }
                override fun onStop() {
                    session.sendCommand(EmulatorSession.CMD_STOP)
                    stopForeground(STOP_FOREGROUND_DETACH)
                    stopSelf()
                }
            })
            isActive = true
        }
    }

    private fun startObserver(observedSession: EmulatorSession) {
        observerJob = scope.launch {
            observedSession.snapshot.collectLatest { snapshot ->
                if (session !== observedSession) return@collectLatest
                updateMediaResumeEligibility(snapshot)
                val state = when {
                    snapshot.playing -> PlaybackStateCompat.STATE_PLAYING
                    snapshot.paused -> PlaybackStateCompat.STATE_PAUSED
                    else -> PlaybackStateCompat.STATE_STOPPED
                }
                val positionMs = snapshot.elapsedSeconds * 1000L
                val notificationSignature = listOf(
                    snapshot.trackNumber,
                    snapshot.trackName,
                    snapshot.author,
                    snapshot.title,
                    snapshot.statusLabel,
                    snapshot.repeatMode,
                ).joinToString("\u0001")

                if (notificationSignature != lastNotificationSignature) {
                    mediaSession.setMetadata(
                        MediaMetadataCompat.Builder()
                            .putString(MediaMetadataCompat.METADATA_KEY_TITLE, snapshot.trackName)
                            .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, snapshot.author)
                            .putString(MediaMetadataCompat.METADATA_KEY_ALBUM, snapshot.title)
                            .putLong(MediaMetadataCompat.METADATA_KEY_TRACK_NUMBER, snapshot.trackNumber.toLong())
                            .build()
                    )
                    (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                        .notify(NOTIFICATION_ID, buildNotification(snapshot))
                    lastNotificationSignature = notificationSignature
                }

                if (state != lastPlaybackState ||
                    snapshot.repeatMode != lastRepeatMode ||
                    kotlin.math.abs(positionMs - lastPlaybackPositionMs) >= 1000L) {
                    mediaSession.setPlaybackState(
                        PlaybackStateCompat.Builder()
                            .setActions(
                                mediaSessionActions(snapshot)
                            )
                            .setState(state, positionMs, 1f)
                            .addCustomAction(
                                PlaybackStateCompat.CustomAction.Builder(
                                    ACTION_REPEAT,
                                    repeatLabel(snapshot.repeatMode),
                                    repeatIcon(snapshot.repeatMode),
                                ).build()
                            )
                            .build()
                    )
                    lastPlaybackState = state
                    lastPlaybackPositionMs = positionMs
                }
                if (snapshot.repeatMode != lastRepeatMode) {
                    mediaSession.setRepeatMode(mapRomRepeatToAndroid(snapshot.repeatMode))
                    lastRepeatMode = snapshot.repeatMode
                }
                latestSnapshot.value = snapshot
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val current = ensureCurrentSession()
        if (current == null || !::mediaSession.isInitialized) {
            stopSelf()
            return START_NOT_STICKY
        }
        when (intent?.action) {
            ACTION_TOGGLE -> session.sendCommand(EmulatorSession.CMD_TOGGLE)
            ACTION_NEXT -> session.sendCommand(EmulatorSession.CMD_NEXT)
            ACTION_PREVIOUS -> session.sendCommand(EmulatorSession.CMD_PREV)
            ACTION_REPEAT -> cycleRepeatMode()
            ACTION_STOP -> {
                session.sendCommand(EmulatorSession.CMD_STOP)
                stopForeground(STOP_FOREGROUND_DETACH)
                stopSelf()
            }
            else -> if (intent != null) {
                handleIntent(mediaSession, intent)
            }
        }
        return START_STICKY
    }

    private fun resumeFromMediaSession() {
        val snapshot = latestSnapshot.value ?: session.snapshot.value
        if (!snapshot.playing && canResumeFromMediaSession(snapshot)) {
            session.sendCommand(EmulatorSession.CMD_TOGGLE)
        }
    }

    private fun pauseFromMediaSession() {
        val snapshot = latestSnapshot.value ?: session.snapshot.value
        if (snapshot.playing) {
            lastMediaPauseMs = SystemClock.elapsedRealtime()
            session.sendCommand(EmulatorSession.CMD_TOGGLE)
        }
    }

    private fun updateMediaResumeEligibility(snapshot: PlaybackSnapshot) {
        if (snapshot.paused && lastObservedPlaying && !lastObservedPaused) {
            lastMediaPauseMs = SystemClock.elapsedRealtime()
        } else if (!snapshot.paused) {
            lastMediaPauseMs = Long.MIN_VALUE
        }
        lastObservedPlaying = snapshot.playing
        lastObservedPaused = snapshot.paused
    }

    private fun canResumeFromMediaSession(snapshot: PlaybackSnapshot): Boolean {
        if (!PlaybackSettings.isMediaResumeGuardEnabled(this)) return true
        if (!snapshot.paused) return false
        val timeoutMs = PlaybackSettings.mediaResumeTimeoutMs(this)
        val pausedForMs = SystemClock.elapsedRealtime() - lastMediaPauseMs
        return pausedForMs in 0..timeoutMs
    }

    private fun mediaSessionActions(snapshot: PlaybackSnapshot): Long {
        var actions = PlaybackStateCompat.ACTION_SKIP_TO_NEXT or
            PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS or
            PlaybackStateCompat.ACTION_SET_REPEAT_MODE or
            PlaybackStateCompat.ACTION_STOP
        if (snapshot.playing) {
            actions = actions or PlaybackStateCompat.ACTION_PAUSE
        }
        if (!snapshot.playing && canResumeFromMediaSession(snapshot)) {
            actions = actions or PlaybackStateCompat.ACTION_PLAY
        }
        return actions
    }

    override fun onDestroy() {
        observerJob?.cancel()
        if (::session.isInitialized) {
            session.flushSave()
        }
        if (::mediaSession.isInitialized) {
            mediaSession.release()
        }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun buildNotification(snapshot: PlaybackSnapshot): Notification {
        val activityIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification_music)
            .setContentTitle(snapshot.trackName)
            .setContentText("${snapshot.title} • ${snapshot.statusLabel} • ${repeatLabel(snapshot.repeatMode)}")
            .setSubText(snapshot.author)
            .setContentIntent(activityIntent)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setOnlyAlertOnce(true)
            .setOngoing(snapshot.playing || snapshot.paused)
            .addAction(android.R.drawable.ic_media_previous, getString(R.string.prev), servicePendingIntent(ACTION_PREVIOUS, 1))
            .addAction(android.R.drawable.ic_media_play, getString(R.string.play_pause), servicePendingIntent(ACTION_TOGGLE, 2))
            .addAction(android.R.drawable.ic_media_next, getString(R.string.next), servicePendingIntent(ACTION_NEXT, 3))
            .addAction(repeatIcon(snapshot.repeatMode), repeatLabel(snapshot.repeatMode), servicePendingIntent(ACTION_REPEAT, 4))
            .addAction(android.R.drawable.ic_media_pause, getString(R.string.stop), servicePendingIntent(ACTION_STOP, 5))
            .setStyle(
                MediaStyle()
                    .setMediaSession(mediaSession.sessionToken)
                    .setShowActionsInCompactView(0, 1, 3)
            )
            .build()
    }

    private fun repeatLabel(mode: Int): String = when (mode) {
        1 -> "RPT ONE"
        2 -> "RPT ALL"
        else -> "RPT OFF"
    }

    private fun repeatIcon(mode: Int): Int = when (mode) {
        1 -> android.R.drawable.ic_menu_revert
        2 -> android.R.drawable.stat_notify_sync
        else -> R.drawable.ic_repeat_all
    }

    private fun cycleRepeatMode() {
        val current = latestSnapshot.value?.repeatMode ?: 0
        val next = (current + 1) % 3
        session.sendCommand(EmulatorSession.CMD_REPEAT, next)
    }

    private fun mapRomRepeatToAndroid(mode: Int): Int = when (mode) {
        1 -> PlaybackStateCompat.REPEAT_MODE_ONE
        2 -> PlaybackStateCompat.REPEAT_MODE_ALL
        else -> PlaybackStateCompat.REPEAT_MODE_NONE
    }

    private fun mapAndroidRepeatToRom(mode: Int): Int = when (mode) {
        PlaybackStateCompat.REPEAT_MODE_ONE -> 1
        PlaybackStateCompat.REPEAT_MODE_ALL, PlaybackStateCompat.REPEAT_MODE_GROUP -> 2
        else -> 0
    }

    private fun servicePendingIntent(action: String, requestCode: Int): PendingIntent {
        return PendingIntent.getService(
            this,
            requestCode,
            Intent(this, PlaybackService::class.java).setAction(action),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.notification_channel_desc)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    companion object {
        private const val CHANNEL_ID = "gbs-playback"
        private const val NOTIFICATION_ID = 1001
        const val ACTION_TOGGLE = "io.github.kleusbalut.gbsplayer.android.TOGGLE"
        const val ACTION_NEXT = "io.github.kleusbalut.gbsplayer.android.NEXT"
        const val ACTION_PREVIOUS = "io.github.kleusbalut.gbsplayer.android.PREVIOUS"
        const val ACTION_REPEAT = "io.github.kleusbalut.gbsplayer.android.REPEAT"
        const val ACTION_STOP = "io.github.kleusbalut.gbsplayer.android.STOP"

        val latestSnapshot = kotlinx.coroutines.flow.MutableStateFlow<PlaybackSnapshot?>(null)

        fun start(context: Context) {
            val intent = Intent(context, PlaybackService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
