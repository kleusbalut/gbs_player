package io.github.kleusbalut.gbsplayer.android

import android.content.Context
import android.content.res.Configuration
import android.os.LocaleList
import java.util.Locale

object AppLocale {
    fun apply(context: Context): Context {
        val locale = Locale(PlaybackSettings.appLanguageCode(context))
        Locale.setDefault(locale)
        val config = Configuration(context.resources.configuration)
        config.setLocale(locale)
        config.setLocales(LocaleList(locale))
        return context.createConfigurationContext(config)
    }
}
