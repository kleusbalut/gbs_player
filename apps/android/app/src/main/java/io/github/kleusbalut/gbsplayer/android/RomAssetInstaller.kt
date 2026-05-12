package io.github.kleusbalut.gbsplayer.android

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileNotFoundException

data class TrackInfo(
    val index: Int,
    val number: Int,
    val name: String,
)

data class RomMetadata(
    val title: String,
    val author: String,
    val songs: List<TrackInfo>,
)

data class BundledRom(
    val id: String,
    val title: String,
    val author: String,
    val romAssetPath: String,
    val metadataAssetPath: String,
    val seedAssetPath: String?,
)

data class RegisteredRom(
    val id: String,
    val title: String,
    val author: String,
    val songCount: Int,
    val displayName: String,
    val romFile: File,
    val saveFile: File,
    val metadataFile: File,
    val sourceUri: String?,
    val sourceDirectoryUri: String?,
)

data class InstalledRom(
    val id: String,
    val romFile: File,
    val saveFile: File,
    val metadata: RomMetadata,
)

object RomAssetInstaller {
    private val libraryRootName = "rom/library"
    private val libraryIndexName = "library.json"

    fun listBundledRoms(context: Context): List<BundledRom> {
        val manifestText = runCatching {
            context.assets.open("game/manifest.json").bufferedReader(Charsets.UTF_8).use { it.readText() }
        }.getOrNull()
        if (manifestText != null) {
            val root = JSONObject(manifestText)
            val romsJson = root.optJSONArray("roms") ?: JSONArray()
            return buildList {
                for (i in 0 until romsJson.length()) {
                    val rom = romsJson.getJSONObject(i)
                    val id = rom.optString("id")
                    if (id.isBlank()) continue
                    add(
                        BundledRom(
                            id = id,
                            title = rom.optString("title", id),
                            author = rom.optString("author", "Unknown Author"),
                            romAssetPath = "game/${rom.getString("rom")}",
                            metadataAssetPath = "game/${rom.optString("metadata", "roms/$id/metadata.json")}",
                            seedAssetPath = rom.optString("seed").takeIf { it.isNotBlank() }?.let { "game/$it" },
                        )
                    )
                }
            }
        }

        if (!assetExists(context, "game", "rom.gbc")) return emptyList()
        val metadata = readMetadataAsset(context, "game/metadata.json", "gbs_player")
        return listOf(
            BundledRom(
                id = "legacy",
                title = metadata.title,
                author = metadata.author,
                romAssetPath = "game/rom.gbc",
                metadataAssetPath = "game/metadata.json",
                seedAssetPath = "game/seed.sav",
            )
        )
    }

    fun install(context: Context, bundledId: String? = null): InstalledRom? {
        if (bundledId?.startsWith(REGISTERED_ROM_PREFIX) == true) {
            installRegistered(context, bundledId.removePrefix(REGISTERED_ROM_PREFIX))?.let { return it }
        }
        if (bundledId == EXTERNAL_ROM_ID) {
            installExistingExternal(context)?.let { return it }
        }
        val bundled = listBundledRoms(context).let { roms ->
            roms.firstOrNull { it.id == bundledId } ?: roms.firstOrNull()
        } ?: return installExistingExternal(context)
        return installBundled(context, bundled)
    }

    fun installBundled(context: Context, bundled: BundledRom): InstalledRom {
        val filesDir = File(context.filesDir, "rom/bundled_v5/${bundled.id}").apply { mkdirs() }
        val romFile = File(filesDir, "gbs_player.gbc")
        val saveFile = File(filesDir, "gbs_player.sav")
        val metadataFile = File(filesDir, "metadata.json")

        copyAsset(context, bundled.romAssetPath, romFile)
        copyAsset(context, bundled.metadataAssetPath, metadataFile)
        if (!saveFile.exists() && bundled.seedAssetPath != null && assetExists(context, bundled.seedAssetPath)) {
            copyAsset(context, bundled.seedAssetPath, saveFile)
        }

        return InstalledRom(
            id = bundled.id,
            romFile = romFile,
            saveFile = saveFile,
            metadata = readMetadata(metadataFile, bundled.title),
        )
    }

    fun listRegisteredRoms(context: Context): List<RegisteredRom> {
        val indexFile = libraryIndexFile(context)
        if (!indexFile.exists()) return emptyList()
        return runCatching {
            val root = JSONObject(indexFile.readText(Charsets.UTF_8))
            val romsJson = root.optJSONArray("roms") ?: JSONArray()
            buildList {
                for (i in 0 until romsJson.length()) {
                    val rom = romsJson.getJSONObject(i)
                    val id = rom.optString("id")
                    if (id.isBlank()) continue
                    val dir = libraryRomDir(context, id)
                    val romFile = File(dir, "rom.gbc")
                    val metadataFile = File(dir, "metadata.json")
                    if (!romFile.exists()) continue
                    add(
                        RegisteredRom(
                            id = id,
                            title = rom.optString("title", id),
                            author = rom.optString("author", "Unknown Author"),
                            songCount = rom.optInt("songCount", 0),
                            displayName = rom.optString("displayName", "$id.gbc"),
                            romFile = romFile,
                            saveFile = File(dir, "gbs_player.sav"),
                            metadataFile = metadataFile,
                            sourceUri = rom.optString("sourceUri").takeIf { it.isNotBlank() },
                            sourceDirectoryUri = rom.optString("sourceDirectoryUri").takeIf { it.isNotBlank() },
                        )
                    )
                }
            }
        }.getOrDefault(emptyList())
    }

    fun registerRom(context: Context, romUri: Uri): RegisteredRom {
        val resolver = context.contentResolver
        val displayName = queryDisplayName(context, romUri) ?: "gbs_player.gbc"
        val baseName = displayName.substringBeforeLast('.', displayName)
        val id = makeLibraryId(baseName)
        val dir = libraryRomDir(context, id).apply { mkdirs() }
        val romFile = File(dir, "rom.gbc")
        val saveFile = File(dir, "gbs_player.sav")
        val metadataFile = File(dir, "metadata.json")

        runCatching {
            resolver.takePersistableUriPermission(
                romUri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION,
            )
        }
        resolver.openInputStream(romUri)?.use { input ->
            romFile.outputStream().use { output -> input.copyTo(output) }
        } ?: throw FileNotFoundException(displayName)

        if (!copyFirstSibling(context, romUri, metadataFile, siblingMetadataNames(baseName))) {
            metadataFile.writeText(defaultMetadataJson(baseName), Charsets.UTF_8)
        }
        if (!copyFirstSibling(context, romUri, saveFile, listOf("$baseName.sav"))) {
            saveFile.writeBytes(ByteArray(0))
        }

        val metadata = readMetadata(metadataFile, baseName)
        val registered = RegisteredRom(
            id = id,
            title = metadata.title,
            author = metadata.author,
            songCount = metadata.songs.size,
            displayName = displayName,
            romFile = romFile,
            saveFile = saveFile,
            metadataFile = metadataFile,
            sourceUri = romUri.toString(),
            sourceDirectoryUri = parentDocumentUri(romUri)?.toString(),
        )
        writeRegisteredRoms(context, listRegisteredRoms(context).filterNot { it.id == id } + registered)
        return registered
    }

    fun installRegistered(context: Context, registeredId: String): InstalledRom? {
        val registered = listRegisteredRoms(context).firstOrNull { it.id == registeredId } ?: return null
        if (!registered.romFile.exists()) return null
        return InstalledRom(
            id = "$REGISTERED_ROM_PREFIX${registered.id}",
            romFile = registered.romFile,
            saveFile = registered.saveFile,
            metadata = readMetadata(registered.metadataFile, registered.title),
        )
    }

    fun unregisterRom(context: Context, registeredId: String): Boolean {
        val existing = listRegisteredRoms(context)
        val target = existing.firstOrNull { it.id == registeredId } ?: return false
        val kept = existing.filterNot { it.id == registeredId }
        writeRegisteredRoms(context, kept)
        target.romFile.parentFile?.deleteRecursively()
        return true
    }

    fun installFromUri(context: Context, romUri: Uri): InstalledRom {
        val resolver = context.contentResolver
        val filesDir = File(context.filesDir, "rom/external").apply { mkdirs() }
        val displayName = queryDisplayName(context, romUri) ?: "gbs_player.gbc"
        val baseName = displayName.substringBeforeLast('.', displayName)
        val romFile = File(filesDir, "gbs_player.gbc")
        val saveFile = File(filesDir, "gbs_player.sav")
        val metadataFile = File(filesDir, "metadata.json")

        runCatching {
            resolver.takePersistableUriPermission(
                romUri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION,
            )
        }
        resolver.openInputStream(romUri)?.use { input ->
            romFile.outputStream().use { output -> input.copyTo(output) }
        } ?: throw FileNotFoundException(displayName)

        if (!copyFirstSibling(context, romUri, metadataFile, siblingMetadataNames(baseName))) {
            metadataFile.writeText(defaultMetadataJson(baseName), Charsets.UTF_8)
        }
        if (!copyFirstSibling(context, romUri, saveFile, listOf("$baseName.sav"))) {
            saveFile.writeBytes(ByteArray(0))
        }

        return InstalledRom(
            id = EXTERNAL_ROM_ID,
            romFile = romFile,
            saveFile = saveFile,
            metadata = readMetadata(metadataFile, baseName),
        )
    }

    fun installExistingExternal(context: Context): InstalledRom? {
        val filesDir = File(context.filesDir, "rom/external")
        val romFile = File(filesDir, "gbs_player.gbc")
        if (!romFile.exists()) return null
        val metadataFile = File(filesDir, "metadata.json")
        return InstalledRom(
            id = EXTERNAL_ROM_ID,
            romFile = romFile,
            saveFile = File(filesDir, "gbs_player.sav"),
            metadata = readMetadata(metadataFile, romFile.nameWithoutExtension),
        )
    }

    private fun writeRegisteredRoms(context: Context, roms: List<RegisteredRom>) {
        val root = JSONObject()
        val romsJson = JSONArray()
        roms.forEach { rom ->
            romsJson.put(
                JSONObject()
                    .put("id", rom.id)
                    .put("title", rom.title)
                    .put("author", rom.author)
                    .put("songCount", rom.songCount)
                    .put("displayName", rom.displayName)
                    .put("sourceUri", rom.sourceUri ?: "")
                    .put("sourceDirectoryUri", rom.sourceDirectoryUri ?: "")
            )
        }
        root.put("roms", romsJson)
        val indexFile = libraryIndexFile(context)
        indexFile.parentFile?.mkdirs()
        indexFile.writeText(root.toString(2), Charsets.UTF_8)
    }

    private fun libraryIndexFile(context: Context): File {
        return File(context.filesDir, "$libraryRootName/$libraryIndexName")
    }

    private fun libraryRomDir(context: Context, id: String): File {
        return File(context.filesDir, "$libraryRootName/$id")
    }

    private fun makeLibraryId(baseName: String): String {
        val safeName = baseName
            .lowercase()
            .map { char -> if (char.isLetterOrDigit()) char else '-' }
            .joinToString("")
            .trim('-')
            .ifBlank { "rom" }
            .take(32)
        return "${safeName}-${System.currentTimeMillis().toString(36)}"
    }

    private fun siblingMetadataNames(baseName: String): List<String> {
        return listOf(
            "$baseName.metadata.json",
            "$baseName.json",
            "metadata.json",
        )
    }

    private fun copyFirstSibling(context: Context, sourceUri: Uri, outFile: File, names: List<String>): Boolean {
        val copied = names.asSequence()
            .mapNotNull { siblingUri(sourceUri, it) }
            .firstOrNull { copyUriIfExists(context, it, outFile) }
        return copied != null
    }

    private fun copyUriIfExists(context: Context, uri: Uri, outFile: File): Boolean {
        return try {
            context.contentResolver.openInputStream(uri)?.use { input ->
                outFile.outputStream().use { output -> input.copyTo(output) }
            }
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun siblingUri(uri: Uri, fileName: String): Uri? {
        if (uri.scheme == "file") {
            val source = File(uri.path ?: return null)
            return Uri.fromFile(File(source.parentFile ?: return null, fileName))
        }
        return try {
            val documentId = DocumentsContract.getDocumentId(uri)
            if (documentId.startsWith("raw:")) {
                val source = File(documentId.removePrefix("raw:"))
                return Uri.fromFile(File(source.parentFile ?: return null, fileName))
            }
            val separator = documentId.lastIndexOf('/')
            val parentId = if (separator >= 0) documentId.substring(0, separator + 1) else ""
            DocumentsContract.buildDocumentUri(uri.authority, parentId + fileName)
        } catch (_: Exception) {
            null
        }
    }

    private fun parentDocumentUri(uri: Uri): Uri? {
        if (uri.scheme == "file") {
            val source = File(uri.path ?: return null)
            return Uri.fromFile(source.parentFile ?: return null)
        }
        return try {
            val documentId = DocumentsContract.getDocumentId(uri)
            if (documentId.startsWith("raw:")) {
                val source = File(documentId.removePrefix("raw:"))
                return Uri.fromFile(source.parentFile ?: return null)
            }
            val separator = documentId.lastIndexOf('/')
            if (separator < 0) return null
            val parentId = documentId.substring(0, separator)
            DocumentsContract.buildDocumentUri(uri.authority, parentId)
        } catch (_: Exception) {
            null
        }
    }

    private fun queryDisplayName(context: Context, uri: Uri): String? {
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) {
                val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (index >= 0) return cursor.getString(index)
            }
        }
        return uri.lastPathSegment?.substringAfterLast('/')
    }

    private fun assetExists(context: Context, assetDir: String, name: String): Boolean {
        return assetExists(context, "$assetDir/$name")
    }

    private fun assetExists(context: Context, assetPath: String): Boolean {
        return try {
            context.assets.open(assetPath).close()
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun copyAsset(context: Context, assetPath: String, outFile: File) {
        context.assets.open(assetPath).use { input ->
            outFile.outputStream().use { output ->
                input.copyTo(output)
            }
        }
    }

    private fun readMetadata(metadataFile: File, fallbackTitle: String): RomMetadata {
        if (!metadataFile.exists()) {
            return RomMetadata(
                title = fallbackTitle,
                author = "Unknown Author",
                songs = emptyList(),
            )
        }
        return parseMetadata(metadataFile.readText(Charsets.UTF_8))
    }

    private fun readMetadataAsset(context: Context, assetPath: String, fallbackTitle: String): RomMetadata {
        return runCatching {
            context.assets.open(assetPath).bufferedReader(Charsets.UTF_8).use { parseMetadata(it.readText()) }
        }.getOrElse {
            RomMetadata(
                title = fallbackTitle,
                author = "Unknown Author",
                songs = emptyList(),
            )
        }
    }

    private fun defaultMetadataJson(title: String): String {
        return JSONObject()
            .put("title", title)
            .put("author", "Unknown Author")
            .put("songs", JSONArray())
            .toString()
    }

    private fun parseMetadata(jsonText: String): RomMetadata {
        val root = JSONObject(jsonText)
        val songsJson = root.optJSONArray("songs") ?: JSONArray()
        val songs = buildList {
            for (i in 0 until songsJson.length()) {
                val song = songsJson.getJSONObject(i)
                add(
                    TrackInfo(
                        index = song.getInt("index"),
                        number = song.getInt("number"),
                        name = song.getString("name"),
                    )
                )
            }
        }
        return RomMetadata(
            title = root.optString("title", "Unknown Title"),
            author = root.optString("author", "Unknown Author"),
            songs = songs,
        )
    }

    const val EXTERNAL_ROM_ID = "external"
    const val REGISTERED_ROM_PREFIX = "library:"
}
