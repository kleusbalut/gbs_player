package io.github.kleusbalut.gbsplayer.android

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PointF
import android.graphics.Rect
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs
import kotlin.math.max

class SkinControllerView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    private val bitmapPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#0E1014") }
    private val panelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#131721") }
    private val dpadPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#49515F") }
    private val activeDpadPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#6C7688") }
    private val abPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#7A475C") }
    private val activeAbPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#A45D7C") }
    private val pillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#A8AEB8") }
    private val activePillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#C2C8D1") }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#E5E7EB")
        textAlign = Paint.Align.CENTER
        textSize = 18f * resources.displayMetrics.density
        letterSpacing = 0.08f
        isFakeBoldText = true
    }
    private val innerLabelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#F3F4F6")
        textAlign = Paint.Align.CENTER
        textSize = 26f * resources.displayMetrics.density
        isFakeBoldText = true
    }

    private var skin = DeltaSkinLoader.defaultSkin()
    private var contentRect = RectF()
    private var visibleSkinRect = RectF()
    private val pointerKeys = mutableMapOf<Int, Set<Int>>()
    private val pointerActions = mutableMapOf<Int, SkinAction?>()
    private var activeKeys = emptySet<Int>()
    private var buttonListener: ((Int, Boolean) -> Unit)? = null
    private var actionListener: ((SkinAction, RectF) -> Unit)? = null
    private var unhandledTouchListener: (() -> Unit)? = null

    init {
        isClickable = true
    }

    fun applySkin(spec: SkinSpec) {
        clearTouches()
        skin = spec
        requestLayout()
        invalidate()
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

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val width = MeasureSpec.getSize(widthMeasureSpec)
        val availableWidth = max(0, width - paddingLeft - paddingRight)
        val visibleRect = skin.visibleControlsRect()
        val aspectHeight = if (visibleRect.width() > 0f && visibleRect.height() > 0f) {
            (availableWidth * (visibleRect.height() / visibleRect.width())).toInt()
        } else {
            0
        }
        val desiredHeight = paddingTop + aspectHeight + paddingBottom
        setMeasuredDimension(width, resolveSize(desiredHeight, heightMeasureSpec))
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        updateRects()
        canvas.drawRoundRect(contentRect, 36f, 36f, bgPaint)

        val background = skin.backgroundBitmap
        if (background != null) {
            canvas.drawBitmap(
                background,
                Rect(
                    visibleSkinRect.left.toInt(),
                    visibleSkinRect.top.toInt(),
                    visibleSkinRect.right.toInt(),
                    visibleSkinRect.bottom.toInt(),
                ),
                contentRect,
                bitmapPaint,
            )
        } else {
            drawFallbackSkin(canvas)
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
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                parent?.requestDisallowInterceptTouchEvent(true)
                val action = resolveAction(event.getX(event.actionIndex), event.getY(event.actionIndex))
                if (action != null) {
                    pointerActions[event.getPointerId(event.actionIndex)] = action
                    actionListener?.invoke(action, actionBounds(action))
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
                    resolveInputs(event.getX(index), event.getY(index))
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

    private fun resolveInputs(viewX: Float, viewY: Float): Set<Int> {
        val skinPoint = toSkinPoint(viewX, viewY) ?: return emptySet()
        val pressed = linkedSetOf<Int>()
        skin.items.forEach { item ->
            if (!expandedFrame(item).contains(skinPoint.x, skinPoint.y)) return@forEach
            when (val mapping = item.mapping) {
                is SkinButtonMapping -> pressed += mapping.keys
                is SkinDpadMapping -> pressed += resolveDpad(mapping, item.frame, skinPoint.x, skinPoint.y)
                is SkinActionMapping -> Unit
            }
        }
        return pressed
    }

    private fun resolveAction(viewX: Float, viewY: Float): SkinAction? {
        val skinPoint = toSkinPoint(viewX, viewY) ?: return null
        skin.items.forEach { item ->
            if (!expandedFrame(item).contains(skinPoint.x, skinPoint.y)) return@forEach
            if (item.mapping is SkinActionMapping) {
                return item.mapping.action
            }
        }
        return null
    }

    private fun actionBounds(action: SkinAction): RectF {
        val item = skin.items.firstOrNull { (it.mapping as? SkinActionMapping)?.action == action }
        return item?.let { mapFrame(it.frame) } ?: RectF(contentRect)
    }

    private fun resolveDpad(mapping: SkinDpadMapping, frame: RectF, x: Float, y: Float): Set<Int> {
        val result = linkedSetOf<Int>()
        val centerX = frame.centerX()
        val centerY = frame.centerY()
        val nx = ((x - centerX) / (frame.width() / 2f)).coerceIn(-1f, 1f)
        val ny = ((y - centerY) / (frame.height() / 2f)).coerceIn(-1f, 1f)

        if (abs(nx) > 0.24f) {
            if (nx < 0f) mapping.leftKey?.let(result::add) else mapping.rightKey?.let(result::add)
        }
        if (abs(ny) > 0.24f) {
            if (ny < 0f) mapping.upKey?.let(result::add) else mapping.downKey?.let(result::add)
        }
        if (result.isEmpty()) {
            if (abs(nx) >= abs(ny)) {
                if (nx < 0f) mapping.leftKey?.let(result::add) else mapping.rightKey?.let(result::add)
            } else {
                if (ny < 0f) mapping.upKey?.let(result::add) else mapping.downKey?.let(result::add)
            }
        }
        return result
    }

    private fun toSkinPoint(viewX: Float, viewY: Float): PointF? {
        if (!contentRect.contains(viewX, viewY)) return null
        val scaleX = visibleSkinRect.width() / contentRect.width()
        val scaleY = visibleSkinRect.height() / contentRect.height()
        return PointF(
            visibleSkinRect.left + (viewX - contentRect.left) * scaleX,
            visibleSkinRect.top + (viewY - contentRect.top) * scaleY,
        )
    }

    private fun expandedFrame(item: SkinItem): RectF {
        return RectF(
            item.frame.left - item.hitInsets.left,
            item.frame.top - item.hitInsets.top,
            item.frame.right + item.hitInsets.right,
            item.frame.bottom + item.hitInsets.bottom,
        )
    }

    private fun updateRects() {
        val left = paddingLeft.toFloat()
        val top = paddingTop.toFloat()
        val width = (measuredWidth - paddingLeft - paddingRight).toFloat()
        visibleSkinRect = skin.visibleControlsRect()
        val height = if (visibleSkinRect.width() > 0f && visibleSkinRect.height() > 0f) {
            width * (visibleSkinRect.height() / visibleSkinRect.width())
        } else {
            0f
        }
        contentRect = RectF(left, top, left + width, top + height)
    }

    private fun mapFrame(frame: RectF): RectF {
        val scaleX = contentRect.width() / visibleSkinRect.width()
        val scaleY = contentRect.height() / visibleSkinRect.height()
        return RectF(
            contentRect.left + (frame.left - visibleSkinRect.left) * scaleX,
            contentRect.top + (frame.top - visibleSkinRect.top) * scaleY,
            contentRect.left + (frame.right - visibleSkinRect.left) * scaleX,
            contentRect.top + (frame.bottom - visibleSkinRect.top) * scaleY,
        )
    }

    private fun drawFallbackSkin(canvas: Canvas) {
        canvas.drawRoundRect(contentRect, 36f, 36f, panelPaint)
        skin.items.forEach { item ->
            val mapped = mapFrame(item.frame)
            val isPressed = when (val mapping = item.mapping) {
                is SkinButtonMapping -> mapping.keys.any(activeKeys::contains)
                is SkinDpadMapping -> listOf(
                    mapping.upKey,
                    mapping.downKey,
                    mapping.leftKey,
                    mapping.rightKey,
                ).filterNotNull().any(activeKeys::contains)
                is SkinActionMapping -> false
            }
            when (item.mapping) {
                is SkinDpadMapping -> {
                    drawDpad(canvas, mapped, if (isPressed) activeDpadPaint else dpadPaint)
                    drawCenteredLabel(canvas, item.label ?: "D-PAD", mapped, innerLabelPaint)
                }

                is SkinButtonMapping -> {
                    val label = item.label.orEmpty()
                    if (label == "A" || label == "B") {
                        canvas.drawOval(mapped, if (isPressed) activeAbPaint else abPaint)
                        drawCenteredLabel(canvas, label, mapped, innerLabelPaint)
                    } else {
                        drawPillButton(
                            canvas,
                            mapped,
                            label,
                            if (isPressed) activePillPaint else pillPaint,
                        )
                    }
                }

                is SkinActionMapping -> {
                    drawPillButton(
                        canvas,
                        mapped,
                        item.label ?: "MENU",
                        if (isPressed) activePillPaint else pillPaint,
                    )
                }
            }
        }
    }

    private fun drawDpad(canvas: Canvas, frame: RectF, paint: Paint) {
        val thickness = minOf(frame.width(), frame.height()) * 0.32f
        val horizontal = RectF(frame.left, frame.centerY() - thickness / 2f, frame.right, frame.centerY() + thickness / 2f)
        val vertical = RectF(frame.centerX() - thickness / 2f, frame.top, frame.centerX() + thickness / 2f, frame.bottom)
        canvas.drawRoundRect(horizontal, 18f, 18f, paint)
        canvas.drawRoundRect(vertical, 18f, 18f, paint)
    }

    private fun drawPillButton(canvas: Canvas, frame: RectF, label: String, paint: Paint) {
        val pillHeight = frame.height() * 0.42f
        val pill = RectF(
            frame.left,
            frame.centerY() - pillHeight / 2f,
            frame.right,
            frame.centerY() + pillHeight / 2f,
        )
        canvas.save()
        canvas.rotate(-18f, pill.centerX(), pill.centerY())
        canvas.drawRoundRect(pill, pillHeight / 2f, pillHeight / 2f, paint)
        canvas.restore()

        val labelY = frame.bottom + labelPaint.textSize * 1.05f
        canvas.drawText(label, frame.centerX(), labelY, labelPaint)
    }

    private fun drawCenteredLabel(canvas: Canvas, label: String, frame: RectF, paint: Paint) {
        val baseline = frame.centerY() - ((paint.descent() + paint.ascent()) / 2f)
        canvas.drawText(label, frame.centerX(), baseline, paint)
    }
}
