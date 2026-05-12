package io.github.kleusbalut.gbsplayer.android

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.RectF
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipInputStream

data class SkinInsets(
    val top: Float = 0f,
    val bottom: Float = 0f,
    val left: Float = 0f,
    val right: Float = 0f,
)

sealed interface SkinInputMapping

enum class SkinAction {
    MENU,
}

data class SkinButtonMapping(
    val keys: Set<Int>,
) : SkinInputMapping

data class SkinDpadMapping(
    val upKey: Int?,
    val downKey: Int?,
    val leftKey: Int?,
    val rightKey: Int?,
) : SkinInputMapping

data class SkinActionMapping(
    val action: SkinAction,
) : SkinInputMapping

data class SkinItem(
    val frame: RectF,
    val hitInsets: SkinInsets,
    val mapping: SkinInputMapping,
    val label: String? = null,
)

data class SkinSpec(
    val name: String,
    val mappingWidth: Float,
    val mappingHeight: Float,
    val screenFrame: RectF,
    val items: List<SkinItem>,
    val backgroundBitmap: Bitmap? = null,
    val controlsCropTop: Float = 0f,
)

fun SkinSpec.visibleControlsRect(): RectF {
    val top = controlsCropTop.coerceIn(0f, mappingHeight)
    return RectF(0f, top, mappingWidth, mappingHeight)
}

object DeltaSkinLoader {
    private const val GBC_IDENTIFIER = "com.rileytestut.delta.game.gbc"

    fun load(context: Context, uri: Uri): SkinSpec {
        val entries = readZipEntries(context, uri)
        val infoBytes = entries["info.json"] ?: error("Missing info.json")
        val info = JSONObject(String(infoBytes, Charsets.UTF_8))
        val gameType = info.optString("gameTypeIdentifier")
        require(gameType == GBC_IDENTIFIER) { "Unsupported skin type: $gameType" }

        val portrait = selectPortraitRepresentation(info)
        val mappingSize = portrait.optJSONObject("mappingSize") ?: error("Missing mappingSize")
        val mappingWidth = mappingSize.optDouble("width", 0.0).toFloat()
        val mappingHeight = mappingSize.optDouble("height", 0.0).toFloat()
        require(mappingWidth > 0f && mappingHeight > 0f) { "Invalid mappingSize" }

        val globalInsets = parseInsets(portrait.optJSONObject("extendedEdges"))
        val screenFrame = parseScreenFrame(portrait.optJSONArray("screens"))
        val items = parseItems(portrait.optJSONArray("items"), globalInsets)
        val backgroundBitmap = loadBackgroundBitmap(context, portrait.optJSONObject("assets"), entries)
        val controlsCropTop = computeControlsCropTop(items, mappingHeight)

        return SkinSpec(
            name = info.optString("name", "Delta Skin"),
            mappingWidth = mappingWidth,
            mappingHeight = mappingHeight,
            screenFrame = screenFrame,
            items = items,
            backgroundBitmap = backgroundBitmap,
            controlsCropTop = controlsCropTop,
        )
    }

    fun defaultSkin(): SkinSpec {
        val items = listOf(
            SkinItem(
                frame = RectF(92f, 1088f, 372f, 1368f),
                hitInsets = SkinInsets(18f, 18f, 18f, 18f),
                mapping = SkinDpadMapping(
                    upKey = EmulatorSession.GB_KEY_UP,
                    downKey = EmulatorSession.GB_KEY_DOWN,
                    leftKey = EmulatorSession.GB_KEY_LEFT,
                    rightKey = EmulatorSession.GB_KEY_RIGHT,
                ),
                label = "D-PAD",
            ),
            SkinItem(
                frame = RectF(720f, 1044f, 900f, 1224f),
                hitInsets = SkinInsets(18f, 18f, 18f, 18f),
                mapping = SkinButtonMapping(setOf(EmulatorSession.GB_KEY_A)),
                label = "A",
            ),
            SkinItem(
                frame = RectF(548f, 1130f, 728f, 1310f),
                hitInsets = SkinInsets(18f, 18f, 18f, 18f),
                mapping = SkinButtonMapping(setOf(EmulatorSession.GB_KEY_B)),
                label = "B",
            ),
            SkinItem(
                frame = RectF(270f, 1438f, 450f, 1514f),
                hitInsets = SkinInsets(10f, 10f, 10f, 10f),
                mapping = SkinButtonMapping(setOf(EmulatorSession.GB_KEY_SELECT)),
                label = "SELECT",
            ),
            SkinItem(
                frame = RectF(554f, 1438f, 734f, 1514f),
                hitInsets = SkinInsets(10f, 10f, 10f, 10f),
                mapping = SkinButtonMapping(setOf(EmulatorSession.GB_KEY_START)),
                label = "START",
            ),
            SkinItem(
                frame = RectF(760f, 1438f, 940f, 1514f),
                hitInsets = SkinInsets(10f, 10f, 10f, 10f),
                mapping = SkinActionMapping(SkinAction.MENU),
                label = "MENU",
            ),
        )

        return SkinSpec(
            name = "Built-in",
            mappingWidth = 1000f,
            mappingHeight = 1800f,
            screenFrame = RectF(108f, 244f, 892f, 950f),
            items = items,
            backgroundBitmap = null,
            controlsCropTop = 980f,
        )
    }

    private fun readZipEntries(context: Context, uri: Uri): Map<String, ByteArray> {
        val entries = linkedMapOf<String, ByteArray>()
        context.contentResolver.openInputStream(uri)?.use { input ->
            ZipInputStream(input).use { zip ->
                while (true) {
                    val entry = zip.nextEntry ?: break
                    if (entry.isDirectory) continue
                    val name = entry.name.substringAfterLast('/')
                    entries[name] = zip.readBytes()
                    zip.closeEntry()
                }
            }
        } ?: error("Unable to open skin")
        return entries
    }

    private fun selectPortraitRepresentation(info: JSONObject): JSONObject {
        val representations = info.optJSONObject("representations") ?: error("Missing representations")
        val iphone = representations.optJSONObject("iphone")
        val ipad = representations.optJSONObject("ipad")
        val candidates = listOf(
            iphone?.optJSONObject("edgeToEdge")?.optJSONObject("portrait"),
            iphone?.optJSONObject("standard")?.optJSONObject("portrait"),
            ipad?.optJSONObject("standard")?.optJSONObject("portrait"),
            ipad?.optJSONObject("splitView")?.optJSONObject("portrait"),
        )
        return candidates.firstOrNull() ?: error("No portrait representation found")
    }

    private fun parseScreenFrame(screens: JSONArray?): RectF {
        val first = screens?.optJSONObject(0) ?: return defaultSkin().screenFrame
        val outputFrame = first.optJSONObject("outputFrame") ?: return defaultSkin().screenFrame
        return parseFrame(outputFrame)
    }

    private fun parseItems(items: JSONArray?, globalInsets: SkinInsets): List<SkinItem> {
        if (items == null) return defaultSkin().items
        val parsed = mutableListOf<SkinItem>()
        for (i in 0 until items.length()) {
            val item = items.optJSONObject(i) ?: continue
            val frameJson = item.optJSONObject("frame") ?: continue
            val frame = parseFrame(frameJson)
            val insets = if (item.has("extendedEdges")) {
                parseInsets(item.optJSONObject("extendedEdges"), globalInsets)
            } else {
                globalInsets
            }
            val inputs = item.opt("inputs") ?: continue
            val mapping = parseMapping(inputs) ?: continue
            parsed += SkinItem(
                frame = frame,
                hitInsets = insets,
                mapping = mapping,
                label = defaultLabel(mapping),
            )
        }
        return if (parsed.isNotEmpty()) parsed else defaultSkin().items
    }

    private fun parseMapping(value: Any): SkinInputMapping? {
        return when (value) {
            is JSONArray -> {
                val keys = mutableSetOf<Int>()
                var action: SkinAction? = null
                for (i in 0 until value.length()) {
                    val input = value.optString(i)
                    action = action ?: mapAction(input)
                    mapInput(input)?.let(keys::add)
                }
                when {
                    action != null -> SkinActionMapping(action)
                    keys.isNotEmpty() -> SkinButtonMapping(keys)
                    else -> null
                }
            }

            is JSONObject -> {
                val up = mapInput(value.optString("up"))
                val down = mapInput(value.optString("down"))
                val left = mapInput(value.optString("left"))
                val right = mapInput(value.optString("right"))
                if (up == null && down == null && left == null && right == null) {
                    null
                } else {
                    SkinDpadMapping(up, down, left, right)
                }
            }

            else -> null
        }
    }

    private fun defaultLabel(mapping: SkinInputMapping): String? {
        return when (mapping) {
            is SkinButtonMapping -> when {
                mapping.keys == setOf(EmulatorSession.GB_KEY_A) -> "A"
                mapping.keys == setOf(EmulatorSession.GB_KEY_B) -> "B"
                mapping.keys == setOf(EmulatorSession.GB_KEY_START) -> "START"
                mapping.keys == setOf(EmulatorSession.GB_KEY_SELECT) -> "SELECT"
                else -> null
            }

            is SkinDpadMapping -> "D-PAD"
            is SkinActionMapping -> if (mapping.action == SkinAction.MENU) "MENU" else null
        }
    }

    private fun mapInput(name: String?): Int? {
        return when (name?.trim()?.lowercase()) {
            "a" -> EmulatorSession.GB_KEY_A
            "b" -> EmulatorSession.GB_KEY_B
            "start" -> EmulatorSession.GB_KEY_START
            "select" -> EmulatorSession.GB_KEY_SELECT
            "up" -> EmulatorSession.GB_KEY_UP
            "down" -> EmulatorSession.GB_KEY_DOWN
            "left" -> EmulatorSession.GB_KEY_LEFT
            "right" -> EmulatorSession.GB_KEY_RIGHT
            else -> null
        }
    }

    private fun mapAction(name: String?): SkinAction? {
        return when (name?.trim()?.lowercase()) {
            "menu" -> SkinAction.MENU
            else -> null
        }
    }

    private fun loadBackgroundBitmap(
        context: Context,
        assets: JSONObject?,
        entries: Map<String, ByteArray>,
    ): Bitmap? {
        if (assets == null) return null
        val name = when {
            assets.has("resizable") -> assets.optString("resizable")
            assets.has("large") -> assets.optString("large")
            assets.has("medium") -> assets.optString("medium")
            else -> assets.optString("small")
        }
        if (name.isBlank()) return null
        val bytes = entries[name] ?: return null
        return when {
            name.endsWith(".pdf", ignoreCase = true) -> renderPdf(context, bytes, name)
            else -> BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
        }
    }

    private fun renderPdf(context: Context, bytes: ByteArray, name: String): Bitmap? {
        val file = File(context.cacheDir, "skin_${name.substringAfterLast('/').substringBeforeLast('.')}.pdf")
        FileOutputStream(file).use { it.write(bytes) }
        val descriptor = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
        descriptor.use {
            PdfRenderer(it).use { renderer ->
                if (renderer.pageCount <= 0) return null
                renderer.openPage(0).use { page ->
                    val bitmap = Bitmap.createBitmap(page.width, page.height, Bitmap.Config.ARGB_8888)
                    page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    return bitmap
                }
            }
        }
    }

    private fun parseFrame(frame: JSONObject): RectF {
        val x = frame.optDouble("x", 0.0).toFloat()
        val y = frame.optDouble("y", 0.0).toFloat()
        val width = frame.optDouble("width", 0.0).toFloat()
        val height = frame.optDouble("height", 0.0).toFloat()
        return RectF(x, y, x + width, y + height)
    }

    private fun parseInsets(insets: JSONObject?, fallback: SkinInsets = SkinInsets()): SkinInsets {
        if (insets == null) return fallback
        return SkinInsets(
            top = insets.optDouble("top", fallback.top.toDouble()).toFloat(),
            bottom = insets.optDouble("bottom", fallback.bottom.toDouble()).toFloat(),
            left = insets.optDouble("left", fallback.left.toDouble()).toFloat(),
            right = insets.optDouble("right", fallback.right.toDouble()).toFloat(),
        )
    }

    private fun computeControlsCropTop(items: List<SkinItem>, mappingHeight: Float): Float {
        val minTop = items.minOfOrNull { it.frame.top - it.hitInsets.top } ?: (mappingHeight * 0.55f)
        return (minTop - 32f).coerceAtLeast(0f)
    }
}
