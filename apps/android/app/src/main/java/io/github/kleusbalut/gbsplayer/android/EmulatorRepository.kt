package io.github.kleusbalut.gbsplayer.android

import android.content.Context
import android.net.Uri

object EmulatorRepository {
    @Volatile
    private var session: EmulatorSession? = null

    fun getOrCreate(context: Context): EmulatorSession? {
        val existing = session
        if (existing != null) return existing

        synchronized(this) {
            val again = session
            if (again != null) return again
            val appContext = context.applicationContext
            val installedRom = RomAssetInstaller.install(appContext, loadActiveRomId(appContext)) ?: return null
            val created = EmulatorSession(installedRom)
            created.start()
            session = created
            return created
        }
    }

    fun bundledRoms(context: Context): List<BundledRom> {
        return RomAssetInstaller.listBundledRoms(context.applicationContext)
    }

    fun registeredRoms(context: Context): List<RegisteredRom> {
        return RomAssetInstaller.listRegisteredRoms(context.applicationContext)
    }

    fun activeRomId(context: Context): String? {
        return loadActiveRomId(context.applicationContext)
    }

    fun currentSession(): EmulatorSession? = session

    fun installBundledAndStart(context: Context, bundled: BundledRom): EmulatorSession {
        synchronized(this) {
            session?.close()
            session = null
            val appContext = context.applicationContext
            val installedRom = RomAssetInstaller.installBundled(appContext, bundled)
            saveActiveRomId(appContext, bundled.id)
            val created = EmulatorSession(installedRom)
            created.start()
            session = created
            return created
        }
    }

    fun installRegisteredAndStart(context: Context, registered: RegisteredRom): EmulatorSession {
        synchronized(this) {
            session?.close()
            session = null
            val appContext = context.applicationContext
            val installedRom = RomAssetInstaller.installRegistered(appContext, registered.id)
                ?: error("Registered ROM not found: ${registered.id}")
            saveActiveRomId(appContext, "${RomAssetInstaller.REGISTERED_ROM_PREFIX}${registered.id}")
            val created = EmulatorSession(installedRom)
            created.start()
            session = created
            return created
        }
    }

    fun registerAndStart(context: Context, romUri: Uri): EmulatorSession {
        synchronized(this) {
            session?.close()
            session = null
            val appContext = context.applicationContext
            val registered = RomAssetInstaller.registerRom(appContext, romUri)
            val installedRom = RomAssetInstaller.installRegistered(appContext, registered.id)
                ?: error("Registered ROM not found: ${registered.id}")
            saveActiveRomId(appContext, "${RomAssetInstaller.REGISTERED_ROM_PREFIX}${registered.id}")
            val created = EmulatorSession(installedRom)
            created.start()
            session = created
            return created
        }
    }

    fun unregisterRegistered(context: Context, registered: RegisteredRom): Boolean {
        synchronized(this) {
            val appContext = context.applicationContext
            val activeId = loadActiveRomId(appContext)
            if (activeId == "${RomAssetInstaller.REGISTERED_ROM_PREFIX}${registered.id}") {
                session?.close()
                session = null
            }
            val removed = RomAssetInstaller.unregisterRom(appContext, registered.id)
            if (activeId == "${RomAssetInstaller.REGISTERED_ROM_PREFIX}${registered.id}") {
                appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                    .edit()
                    .remove(PREF_ACTIVE_ROM_ID)
                    .apply()
            }
            return removed
        }
    }

    fun installAndStart(context: Context, romUri: Uri): EmulatorSession {
        synchronized(this) {
            session?.close()
            session = null
            val appContext = context.applicationContext
            val installedRom = RomAssetInstaller.installFromUri(appContext, romUri)
            saveActiveRomId(appContext, RomAssetInstaller.EXTERNAL_ROM_ID)
            val created = EmulatorSession(installedRom)
            created.start()
            session = created
            return created
        }
    }

    fun shutdown() {
        synchronized(this) {
            session?.close()
            session = null
        }
    }

    private fun loadActiveRomId(context: Context): String? {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(PREF_ACTIVE_ROM_ID, null)
    }

    private fun saveActiveRomId(context: Context, romId: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(PREF_ACTIVE_ROM_ID, romId)
            .apply()
    }

    private const val PREFS_NAME = "gbs_player_prefs"
    private const val PREF_ACTIVE_ROM_ID = "active_rom_id"
}
