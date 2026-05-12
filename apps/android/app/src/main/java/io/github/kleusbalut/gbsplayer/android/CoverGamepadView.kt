package io.github.kleusbalut.gbsplayer.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.min

class CoverGamepadView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    private data class ButtonConfig(
        var dx: Float = 0f,
        var dy: Float = 0f,
        var scale: Float = 1f,
    )

    private data class HitTarget(
        val label: String,
        val frame: RectF,
        val keys: Set<Int> = emptySet(),
        val action: SkinAction? = null,
        val round: Boolean = true,
    )

    private val scale = resources.displayMetrics.density
    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * scale
        color = Color.argb(190, 82, 88, 98)
    }
    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = Color.argb(38, 245, 248, 255)
    }
    private val activeFillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = Color.argb(86, 245, 248, 255)
    }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.argb(230, 70, 76, 86)
        textAlign = Paint.Align.CENTER
        textSize = 16f * scale
        isFakeBoldText = true
    }
    private val smallLabelPaint = Paint(labelPaint).apply {
        textSize = 11f * scale
        isFakeBoldText = true
    }
    private val configPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3.5f * scale
        color = Color.argb(230, 58, 122, 255)
    }

    private val pointerKeys = mutableMapOf<Int, Set<Int>>()
    private val pointerActions = mutableMapOf<Int, SkinAction?>()
    private var activeKeys = emptySet<Int>()
    private var targets = emptyList<HitTarget>()
    private val configs = linkedMapOf(
        "D" to ButtonConfig(),
        "A" to ButtonConfig(),
        "B" to ButtonConfig(),
        "SELECT" to ButtonConfig(),
        "START" to ButtonConfig(),
        "MENU" to ButtonConfig(),
    )
    private var configMode = false
    private var gamepadVisible = true
    private var selectedLabel: String? = null
    private var dragPointerId: Int? = null
    private var lastDragX = 0f
    private var lastDragY = 0f
    private var pinchStartDistance = 0f
    private var pinchStartScale = 1f
    private var lastEmptyTapTime = 0L
    private var lastEmptyTapX = 0f
    private var lastEmptyTapY = 0f
    private var doneFrame = RectF()
    private var buttonListener: ((Int, Boolean) -> Unit)? = null
    private var actionListener: ((SkinAction, RectF) -> Unit)? = null
    private var unhandledTouchListener: (() -> Unit)? = null
    private var configDoneListener: (() -> Unit)? = null

    init {
        isClickable = true
        loadConfigs()
    }

    fun setOnButtonStateChangedListener(listener: (Int, Boolean) -> Unit) {
        buttonListener = listener
    }

    fun setOnActionListener(listener: (SkinAction, RectF) -> Unit) {
        actionListener = listener
    }

    fun setOnUnhandledTouchListener(listener: () -> Unit) {
        unhandledTouchListener = listener
    }

    fun setOnConfigDoneListener(listener: () -> Unit) {
        configDoneListener = listener
    }

    fun setConfigMode(enabled: Boolean) {
        if (configMode == enabled) return
        configMode = enabled
        if (enabled) {
            gamepadVisible = true
        }
        clearTouches()
        if (enabled && selectedLabel == null) selectedLabel = "D"
        if (!enabled) {
            dragPointerId = null
            pinchStartDistance = 0f
            saveConfigs()
        }
        invalidate()
    }

    fun isConfigMode(): Boolean = configMode

    fun releaseKeys() {
        clearTouches()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        updateTargets()
        if (!gamepadVisible && !configMode) return
        targets.forEach { target ->
            val pressed = target.keys.any(activeKeys::contains)
            val fill = if (pressed) activeFillPaint else fillPaint
            if (target.label == "D") {
                drawDpad(canvas, target.frame, fill)
            } else if (target.round) {
                val radius = min(target.frame.width(), target.frame.height()) / 2f
                canvas.drawRoundRect(target.frame, radius, radius, fill)
                canvas.drawRoundRect(target.frame, radius, radius, linePaint)
            } else {
                canvas.drawOval(target.frame, fill)
                canvas.drawOval(target.frame, linePaint)
            }
            if (target.label != "D") {
                drawCenteredText(canvas, target.label, target.frame, if (target.label.length > 2) smallLabelPaint else labelPaint)
            }
            if (configMode && target.label == selectedLabel) {
                canvas.drawRoundRect(target.frame, 10f * scale, 10f * scale, configPaint)
            }
        }
        if (configMode) {
            drawDoneButton(canvas)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN,
            MotionEvent.ACTION_POINTER_DOWN,
            MotionEvent.ACTION_MOVE,
            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_POINTER_UP,
            MotionEvent.ACTION_CANCEL,
            -> handleTouch(event)
        }
        return true
    }

    override fun onDetachedFromWindow() {
        clearTouches()
        super.onDetachedFromWindow()
    }

    private fun handleTouch(event: MotionEvent) {
        updateTargets()
        if (configMode) {
            handleConfigTouch(event)
            return
        }
        if (handleVisibilityToggleTouch(event)) return
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                val action = resolveAction(event.getX(event.actionIndex), event.getY(event.actionIndex))
                if (action != null) {
                    pointerActions[event.getPointerId(event.actionIndex)] = action
                    actionListener?.invoke(action, actionFrame(action))
                }
            }

            MotionEvent.ACTION_CANCEL -> {
                parent?.requestDisallowInterceptTouchEvent(false)
                clearTouches()
                return
            }

            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> {
                val pointerId = event.getPointerId(event.actionIndex)
                pointerKeys.remove(pointerId)
                pointerActions.remove(pointerId)
                if (event.actionMasked == MotionEvent.ACTION_UP || pointerKeys.isEmpty()) {
                    parent?.requestDisallowInterceptTouchEvent(false)
                }
            }
        }

        if (event.actionMasked != MotionEvent.ACTION_UP && event.actionMasked != MotionEvent.ACTION_POINTER_UP) {
            for (index in 0 until event.pointerCount) {
                val pointerId = event.getPointerId(index)
                val keys = if (pointerActions[pointerId] == null) {
                    resolveKeys(event.getX(index), event.getY(index))
                } else {
                    emptySet()
                }
                if ((event.actionMasked == MotionEvent.ACTION_DOWN ||
                        event.actionMasked == MotionEvent.ACTION_POINTER_DOWN) &&
                    index == event.actionIndex &&
                    keys.isEmpty() &&
                    pointerActions[pointerId] == null) {
                    unhandledTouchListener?.invoke()
                }
                pointerKeys[pointerId] = keys
            }
            parent?.requestDisallowInterceptTouchEvent(true)
        }
        syncPressedKeys()
    }

    private fun handleVisibilityToggleTouch(event: MotionEvent): Boolean {
        if (event.actionMasked != MotionEvent.ACTION_DOWN) {
            return !gamepadVisible
        }

        if (!gamepadVisible) {
            resetEmptyTap()
            setGamepadVisible(true)
            return true
        }

        val x = event.getX(event.actionIndex)
        val y = event.getY(event.actionIndex)
        if (targetAt(x, y) != null) return false

        if (isEmptyAreaDoubleTap(event.eventTime, x, y)) {
            resetEmptyTap()
            setGamepadVisible(false)
        } else {
            lastEmptyTapTime = event.eventTime
            lastEmptyTapX = x
            lastEmptyTapY = y
            unhandledTouchListener?.invoke()
        }
        return true
    }

    private fun isEmptyAreaDoubleTap(eventTime: Long, x: Float, y: Float): Boolean {
        if (lastEmptyTapTime == 0L) return false
        if (eventTime - lastEmptyTapTime > ViewConfiguration.getDoubleTapTimeout()) return false
        val slop = ViewConfiguration.get(context).scaledDoubleTapSlop.toFloat()
        return hypot(x - lastEmptyTapX, y - lastEmptyTapY) <= slop
    }

    private fun resetEmptyTap() {
        lastEmptyTapTime = 0L
        lastEmptyTapX = 0f
        lastEmptyTapY = 0f
    }

    private fun setGamepadVisible(visible: Boolean) {
        if (gamepadVisible == visible) return
        gamepadVisible = visible
        clearTouches()
        parent?.requestDisallowInterceptTouchEvent(false)
        invalidate()
    }

    private fun syncPressedKeys() {
        val nextKeys = pointerKeys.values.flatten().toSet()
        val toRelease = activeKeys - nextKeys
        val toPress = nextKeys - activeKeys
        toRelease.forEach { buttonListener?.invoke(it, false) }
        toPress.forEach { buttonListener?.invoke(it, true) }
        activeKeys = nextKeys
        invalidate()
    }

    private fun clearTouches() {
        pointerKeys.clear()
        pointerActions.clear()
        if (activeKeys.isNotEmpty()) {
            activeKeys.forEach { buttonListener?.invoke(it, false) }
            activeKeys = emptySet()
        }
        invalidate()
    }

    private fun resolveKeys(x: Float, y: Float): Set<Int> {
        val dpad = targets.firstOrNull { it.label == "D" }?.frame
        if (dpad != null && dpad.contains(x, y)) return resolveDpad(dpad, x, y)
        return targets.firstOrNull { it.keys.isNotEmpty() && it.frame.contains(x, y) }?.keys.orEmpty()
    }

    private fun resolveAction(x: Float, y: Float): SkinAction? {
        return targets.firstOrNull { it.action != null && it.frame.contains(x, y) }?.action
    }

    private fun targetAt(x: Float, y: Float): HitTarget? {
        return targets.lastOrNull { it.frame.contains(x, y) }
    }

    private fun actionFrame(action: SkinAction): RectF {
        return targets.firstOrNull { it.action == action }?.frame ?: RectF(0f, 0f, width.toFloat(), height.toFloat())
    }

    private fun resolveDpad(frame: RectF, x: Float, y: Float): Set<Int> {
        val result = linkedSetOf<Int>()
        val nx = ((x - frame.centerX()) / (frame.width() / 2f)).coerceIn(-1f, 1f)
        val ny = ((y - frame.centerY()) / (frame.height() / 2f)).coerceIn(-1f, 1f)
        if (abs(nx) > 0.24f) {
            result += if (nx < 0f) EmulatorSession.GB_KEY_LEFT else EmulatorSession.GB_KEY_RIGHT
        }
        if (abs(ny) > 0.24f) {
            result += if (ny < 0f) EmulatorSession.GB_KEY_UP else EmulatorSession.GB_KEY_DOWN
        }
        if (result.isEmpty()) {
            result += if (abs(nx) >= abs(ny)) {
                if (nx < 0f) EmulatorSession.GB_KEY_LEFT else EmulatorSession.GB_KEY_RIGHT
            } else {
                if (ny < 0f) EmulatorSession.GB_KEY_UP else EmulatorSession.GB_KEY_DOWN
            }
        }
        return result
    }

    private fun updateTargets() {
        val w = width.toFloat()
        val h = height.toFloat()
        if (w <= 0f || h <= 0f) {
            targets = emptyList()
            return
        }

        val game = gameScreenRect(w, h)
        game.inset(18f * scale, 18f * scale)
        val edge = 10f * scale
        val bottom = game.bottom - 8f * scale
        val overlayHeight = min(game.height() * 0.32f, 148f * scale)
        val top = bottom - overlayHeight
        val dpadSize = min(game.width() * 0.26f, overlayHeight * 0.86f).coerceAtLeast(78f * scale)
        val dpadTop = top + overlayHeight * 0.10f
        val buttonSize = min(dpadSize * 0.78f, 70f * scale)
        val rightLimit = game.right - edge - game.width() * 0.015f
        val pillGap = 8f * scale
        val pillW = min(min(game.width() * 0.19f, 88f * scale), (rightLimit - game.left - edge - (2f * pillGap)) / 3f)
        val pillH = min(40f * scale, overlayHeight * 0.34f)
        val pillTop = bottom - pillH

        val baseA = RectF(rightLimit - buttonSize, top + 4f * scale, rightLimit, top + 4f * scale + buttonSize)
        val dpad = applyConfig("D", RectF(game.left + edge, dpadTop, game.left + edge + dpadSize, dpadTop + dpadSize), game)
        val a = applyConfig("A", baseA, game)
        val b = applyConfig("B", RectF(baseA.left - buttonSize - 14f * scale, baseA.top + buttonSize * 0.42f, baseA.left - 14f * scale, baseA.top + buttonSize * 1.42f), game)
        val menuTop = top + 4f * scale
        val menu = applyConfig("MENU", RectF(game.centerX() - pillW / 2f, menuTop, game.centerX() + pillW / 2f, menuTop + pillH), game)
        val start = applyConfig("START", RectF(game.centerX() + pillGap / 2f, pillTop, game.centerX() + pillGap / 2f + pillW, pillTop + pillH), game)
        val select = applyConfig("SELECT", RectF(game.centerX() - pillGap / 2f - pillW, pillTop, game.centerX() - pillGap / 2f, pillTop + pillH), game)
        doneFrame = RectF(game.right - 70f * scale, game.top + 8f * scale, game.right - 10f * scale, game.top + 36f * scale)

        targets = listOf(
            HitTarget("D", dpad),
            HitTarget("A", a, setOf(EmulatorSession.GB_KEY_A), round = false),
            HitTarget("B", b, setOf(EmulatorSession.GB_KEY_B), round = false),
            HitTarget("SELECT", select, setOf(EmulatorSession.GB_KEY_SELECT)),
            HitTarget("START", start, setOf(EmulatorSession.GB_KEY_START)),
            HitTarget("MENU", menu, action = SkinAction.MENU),
        )
    }

    private fun applyConfig(label: String, base: RectF, game: RectF): RectF {
        val config = configs[label] ?: return base
        val cx = base.centerX() + config.dx * game.width()
        val cy = base.centerY() + config.dy * game.height()
        val halfW = base.width() * config.scale / 2f
        val halfH = base.height() * config.scale / 2f
        return RectF(cx - halfW, cy - halfH, cx + halfW, cy + halfH)
    }

    private fun gameScreenRect(viewWidth: Float, viewHeight: Float): RectF {
        val gameAspect = EmulatorSession.SCREEN_WIDTH.toFloat() / EmulatorSession.SCREEN_HEIGHT.toFloat()
        val viewAspect = viewWidth / viewHeight
        return if (viewAspect > gameAspect) {
            val gameHeight = viewHeight
            val gameWidth = gameHeight * gameAspect
            val left = (viewWidth - gameWidth) / 2f
            RectF(left, 0f, left + gameWidth, gameHeight)
        } else {
            val gameWidth = viewWidth
            val gameHeight = gameWidth / gameAspect
            val top = (viewHeight - gameHeight) / 2f
            RectF(0f, top, gameWidth, top + gameHeight)
        }
    }

    private fun drawDpad(canvas: Canvas, frame: RectF, fill: Paint) {
        val thickness = frame.width() * 0.34f
        val radius = 8f * scale
        val horizontal = RectF(
            frame.left,
            frame.centerY() - thickness / 2f,
            frame.right,
            frame.centerY() + thickness / 2f,
        )
        val vertical = RectF(
            frame.centerX() - thickness / 2f,
            frame.top,
            frame.centerX() + thickness / 2f,
            frame.bottom,
        )
        canvas.drawRoundRect(horizontal, radius, radius, fill)
        canvas.drawRoundRect(vertical, radius, radius, fill)
        canvas.drawRoundRect(horizontal, radius, radius, linePaint)
        canvas.drawRoundRect(vertical, radius, radius, linePaint)
    }

    private fun handleConfigTouch(event: MotionEvent) {
        parent?.requestDisallowInterceptTouchEvent(true)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (doneFrame.contains(event.x, event.y)) {
                    setConfigMode(false)
                    configDoneListener?.invoke()
                    parent?.requestDisallowInterceptTouchEvent(false)
                    return
                }
                val target = findConfigTarget(event.x, event.y)
                selectedLabel = target?.label ?: selectedLabel
                dragPointerId = if (target != null) event.getPointerId(0) else null
                lastDragX = event.x
                lastDragY = event.y
                pinchStartDistance = 0f
                invalidate()
            }

            MotionEvent.ACTION_POINTER_DOWN -> {
                if (event.pointerCount >= 2) {
                    pinchStartDistance = pointerDistance(event)
                    pinchStartScale = configs[selectedLabel]?.scale ?: 1f
                }
            }

            MotionEvent.ACTION_MOVE -> {
                val selected = selectedLabel
                val config = selected?.let(configs::get)
                val game = gameScreenRect(width.toFloat(), height.toFloat()).apply {
                    inset(18f * scale, 18f * scale)
                }
                if (config != null && event.pointerCount >= 2 && pinchStartDistance > 0f) {
                    val nextScale = (pinchStartScale * (pointerDistance(event) / pinchStartDistance)).coerceIn(0.6f, 1.8f)
                    config.scale = nextScale
                    invalidate()
                } else if (config != null) {
                    val pointerIndex = dragPointerId?.let { event.findPointerIndex(it) } ?: -1
                    if (pointerIndex >= 0) {
                        val x = event.getX(pointerIndex)
                        val y = event.getY(pointerIndex)
                        config.dx += (x - lastDragX) / game.width()
                        config.dy += (y - lastDragY) / game.height()
                        lastDragX = x
                        lastDragY = y
                        invalidate()
                    }
                }
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_CANCEL,
            -> {
                saveConfigs()
                dragPointerId = null
                pinchStartDistance = 0f
                parent?.requestDisallowInterceptTouchEvent(false)
            }
        }
    }

    private fun findConfigTarget(x: Float, y: Float): HitTarget? {
        targetAt(x, y)?.let { return it }
        return targets
            .minByOrNull { distanceToFrame(it.frame, x, y) }
            ?.takeIf { target ->
                val tolerance = maxOf(44f * scale, min(target.frame.width(), target.frame.height()) * 0.75f)
                distanceToFrame(target.frame, x, y) <= tolerance
            }
    }

    private fun distanceToFrame(frame: RectF, x: Float, y: Float): Float {
        val dx = when {
            x < frame.left -> frame.left - x
            x > frame.right -> x - frame.right
            else -> 0f
        }
        val dy = when {
            y < frame.top -> frame.top - y
            y > frame.bottom -> y - frame.bottom
            else -> 0f
        }
        return hypot(dx, dy)
    }

    private fun pointerDistance(event: MotionEvent): Float {
        if (event.pointerCount < 2) return 0f
        return hypot(event.getX(0) - event.getX(1), event.getY(0) - event.getY(1))
    }

    private fun drawDoneButton(canvas: Canvas) {
        val radius = min(doneFrame.width(), doneFrame.height()) / 2f
        canvas.drawRoundRect(doneFrame, radius, radius, fillPaint)
        canvas.drawRoundRect(doneFrame, radius, radius, configPaint)
        drawCenteredText(canvas, "DONE", doneFrame, smallLabelPaint)
    }

    private fun loadConfigs() {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        configs.forEach { (label, config) ->
            config.dx = prefs.getFloat("${label}_dx", 0f)
            config.dy = prefs.getFloat("${label}_dy", 0f)
            config.scale = prefs.getFloat("${label}_scale", 1f)
        }
    }

    private fun saveConfigs() {
        val edit = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit()
        configs.forEach { (label, config) ->
            edit.putFloat("${label}_dx", config.dx)
            edit.putFloat("${label}_dy", config.dy)
            edit.putFloat("${label}_scale", config.scale)
        }
        edit.apply()
    }

    private fun drawCenteredText(canvas: Canvas, text: String, frame: RectF, paint: Paint) {
        val baseline = frame.centerY() - ((paint.descent() + paint.ascent()) / 2f)
        canvas.drawText(text, frame.centerX(), baseline, paint)
    }

    companion object {
        private const val PREFS_NAME = "cover_gamepad_config"
    }
}
