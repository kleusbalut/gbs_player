package io.github.kleusbalut.gbsplayer.android

import android.content.Context
import android.os.LocaleList

data class MediaResumeTimeoutOption(
    val valueMs: Long,
    val labelResId: Int,
)

data class AppLanguageOption(
    val code: String,
    val labelResId: Int,
)

object PlaybackSettings {
    const val PREFS_NAME = "gbs_player_prefs"
    private const val PREF_APP_LANGUAGE = "app_language"
    private const val PREF_INVERT_SCREEN = "invert_screen"
    private const val PREF_MEDIA_RESUME_GUARD_ENABLED = "media_resume_guard_enabled"
    private const val PREF_MEDIA_RESUME_TIMEOUT_MS = "media_resume_timeout_ms"

    const val LANGUAGE_EN = "en"
    const val LANGUAGE_JA = "ja"
    const val DEFAULT_MEDIA_RESUME_TIMEOUT_MS = 30 * 60 * 1000L

    val APP_LANGUAGE_OPTIONS = listOf(
        AppLanguageOption(LANGUAGE_EN, R.string.language_english),
        AppLanguageOption(LANGUAGE_JA, R.string.language_japanese),
    )

    val MEDIA_RESUME_TIMEOUT_OPTIONS = listOf(
        MediaResumeTimeoutOption(5 * 60 * 1000L, R.string.media_resume_timeout_5m),
        MediaResumeTimeoutOption(15 * 60 * 1000L, R.string.media_resume_timeout_15m),
        MediaResumeTimeoutOption(DEFAULT_MEDIA_RESUME_TIMEOUT_MS, R.string.media_resume_timeout_30m),
        MediaResumeTimeoutOption(60 * 60 * 1000L, R.string.media_resume_timeout_1h),
    )

    fun appLanguageCode(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val saved = prefs.getString(PREF_APP_LANGUAGE, null)
        if (saved == LANGUAGE_EN || saved == LANGUAGE_JA) return saved
        val initial = if (LocaleList.getDefault().get(0).language == LANGUAGE_JA) {
            LANGUAGE_JA
        } else {
            LANGUAGE_EN
        }
        prefs.edit().putString(PREF_APP_LANGUAGE, initial).apply()
        return initial
    }

    fun setAppLanguageCode(context: Context, languageCode: String) {
        val normalized = if (languageCode == LANGUAGE_JA) LANGUAGE_JA else LANGUAGE_EN
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(PREF_APP_LANGUAGE, normalized)
            .apply()
    }

    fun isScreenInverted(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(PREF_INVERT_SCREEN, false)
    }

    fun setScreenInverted(context: Context, inverted: Boolean) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(PREF_INVERT_SCREEN, inverted)
            .apply()
    }

    fun isMediaResumeGuardEnabled(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getBoolean(PREF_MEDIA_RESUME_GUARD_ENABLED, true)
    }

    fun setMediaResumeGuardEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(PREF_MEDIA_RESUME_GUARD_ENABLED, enabled)
            .apply()
    }

    fun mediaResumeTimeoutMs(context: Context): Long {
        val saved = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getLong(PREF_MEDIA_RESUME_TIMEOUT_MS, DEFAULT_MEDIA_RESUME_TIMEOUT_MS)
        return MEDIA_RESUME_TIMEOUT_OPTIONS
            .firstOrNull { it.valueMs == saved }
            ?.valueMs
            ?: DEFAULT_MEDIA_RESUME_TIMEOUT_MS
    }

    fun setMediaResumeTimeoutMs(context: Context, timeoutMs: Long) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putLong(PREF_MEDIA_RESUME_TIMEOUT_MS, timeoutMs)
            .apply()
    }
}
