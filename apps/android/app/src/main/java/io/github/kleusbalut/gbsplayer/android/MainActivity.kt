package io.github.kleusbalut.gbsplayer.android

import android.Manifest
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.ColorMatrixColorFilter
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.drawable.ColorDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.PopupWindow
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts.OpenDocument
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.window.layout.FoldingFeature
import androidx.window.layout.WindowInfoTracker
import io.github.kleusbalut.gbsplayer.android.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private enum class ScreenMode {
        FULL,
        INSET,
    }

    private data class MenuEntry(
        val id: Int,
        val title: String,
    )

    private data class PlayerModeButton(
        val action: Int,
        val bounds: Rect,
    )

    private enum class LibraryEntryKind {
        BUNDLED,
        REGISTERED,
        REGISTER,
    }

    private data class LibraryEntry(
        val kind: LibraryEntryKind,
        val title: String,
        val subtitle: String,
        val bundled: BundledRom? = null,
        val registered: RegisteredRom? = null,
        val active: Boolean = false,
    )

    private lateinit var binding: ActivityMainBinding
    private lateinit var bitmap: Bitmap
    private var session: EmulatorSession? = null
    private var screenMode = ScreenMode.FULL
    private var menuOpen = false
    private var libraryActionPopup: PopupWindow? = null
    private var menuEntries: List<MenuEntry> = emptyList()
    private var menuLabels: List<TextView> = emptyList()
    private var libraryEntries: List<LibraryEntry> = emptyList()
    private var libraryRowViews: List<View> = emptyList()
    private var selectedLibraryIndex = 0
    private var libraryEllipsisFocused = false
    private var selectedMenuIndex = 0
    private var lastMenuAnchor = RectF()
    private var flexModeActive = false
    private var coverModeActive = false
    private var importedSkinActive = false
    private var playerModeActive = false
    private val defaultPressedKeys = mutableSetOf<Int>()
    private val defaultPointerKeys = mutableMapOf<Int, Set<Int>>()
    private val playerPointerActions = mutableMapOf<Int, Int>()

    private val skinPicker = registerForActivityResult(OpenDocument()) { uri ->
        if (uri == null) return@registerForActivityResult
        contentResolver.takePersistableUriPermission(
            uri,
            Intent.FLAG_GRANT_READ_URI_PERMISSION,
        )
        saveSkinUri(uri)
        loadSkin(uri)
    }

    private val romPicker = registerForActivityResult(OpenDocument()) { uri ->
        if (uri == null) return@registerForActivityResult
        lifecycleScope.launch {
            val loadedSession = withContext(Dispatchers.IO) {
                runCatching { EmulatorRepository.registerAndStart(this@MainActivity, uri) }.getOrNull()
            }
            if (loadedSession != null) {
                bindSession(loadedSession)
                loadedSession.setUiVisible(true)
                PlaybackService.start(this@MainActivity)
                showLibraryOverlay()
            } else {
                Toast.makeText(this@MainActivity, R.string.rom_load_failed, Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(AppLocale.apply(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        requestNotificationPermissionIfNeeded()
        window.statusBarColor = Color.parseColor("#101217")
        window.navigationBarColor = Color.parseColor("#101217")
        WindowCompat.setDecorFitsSystemWindows(window, true)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
        }

        session = EmulatorRepository.getOrCreate(this)
        session?.let { PlaybackService.start(this) }
        bitmap = Bitmap.createBitmap(
            EmulatorSession.SCREEN_WIDTH,
            EmulatorSession.SCREEN_HEIGHT,
            Bitmap.Config.ARGB_8888,
        )
        binding.screenView.setImageBitmap(bitmap)
        applyScreenColorFilter()
        binding.screenView.isClickable = true
        binding.screenView.setOnTouchListener { _, event ->
            handleScreenTouch(event)
        }
        binding.libraryOverlay.setOnClickListener {
            hideLibraryOverlay()
        }
        binding.libraryPanel.setOnClickListener {
            // Consume touches so taps inside the panel do not dismiss the overlay.
        }
        binding.menuOverlay.setOnClickListener {
            dismissMenu()
        }
        binding.menuPanel.setOnClickListener {
            // Consume touches so taps inside the panel do not dismiss the overlay.
        }
        screenMode = loadScreenMode()
        coverModeActive = isCoverDisplay()

        binding.skinView.setOnButtonStateChangedListener { key, pressed ->
            if (handleMenuKeyInput(key, pressed)) return@setOnButtonStateChangedListener
            session?.setKeyPressed(key, pressed)
        }
        binding.skinView.setOnActionListener { action, bounds ->
            if (action == SkinAction.MENU) {
                lastMenuAnchor = viewBoundsInRoot(binding.skinView, bounds)
                showSkinMenu(lastMenuAnchor)
            }
        }
        binding.skinView.setOnUnhandledTouchListener {
            dismissMenu()
        }
        binding.coverGamepad.setOnButtonStateChangedListener { key, pressed ->
            if (handleMenuKeyInput(key, pressed)) return@setOnButtonStateChangedListener
            session?.setKeyPressed(key, pressed)
        }
        binding.coverGamepad.setOnActionListener { action, bounds ->
            if (action == SkinAction.MENU) {
                lastMenuAnchor = viewBoundsInRoot(binding.coverGamepad, bounds)
                showSkinMenu(lastMenuAnchor)
            }
        }
        binding.coverGamepad.setOnUnhandledTouchListener {
            dismissMenu()
        }
        binding.coverGamepad.setOnConfigDoneListener {
            Toast.makeText(this, R.string.cover_gamepad_config_saved, Toast.LENGTH_SHORT).show()
        }
        configureDefaultControls()
        observeFoldState()

        session?.let(::bindSession) ?: showNoRomState()

        val savedSkinUri = loadSavedSkinUri()
        if (savedSkinUri != null) {
            loadSkin(savedSkinUri)
        } else {
            showDefaultControls()
            updateScreenLayout()
        }
    }

    override fun onStart() {
        super.onStart()
        session?.setUiVisible(true)
        if (refreshCoverMode()) {
            updateScreenLayout()
        }
    }

    override fun onStop() {
        dismissMenu()
        hideLibraryOverlay()
        releasePlayerModeTouches()
        releaseDefaultControlKeys()
        binding.coverGamepad.releaseKeys()
        session?.setUiVisible(false)
        super.onStop()
    }

    private fun bindSession(newSession: EmulatorSession) {
        session = newSession
        lifecycleScope.launch {
            newSession.snapshot.collect { snapshot ->
                if (session !== newSession) return@collect
                if (!snapshot.playerMode && playerModeActive) {
                    releasePlayerModeTouches()
                }
                playerModeActive = snapshot.playerMode
                binding.trackText.text = "${snapshot.trackNumber}. ${snapshot.trackName}"
            }
        }

        lifecycleScope.launch {
            newSession.framePixels.collect { pixels ->
                if (session !== newSession) return@collect
                bitmap.setPixels(
                    pixels,
                    0,
                    EmulatorSession.SCREEN_WIDTH,
                    0,
                    0,
                    EmulatorSession.SCREEN_WIDTH,
                    EmulatorSession.SCREEN_HEIGHT,
                )
                binding.screenView.invalidate()
            }
        }
    }

    private fun showNoRomState() {
        binding.trackText.text = getString(R.string.no_rom_loaded)
    }

    private fun loadSkin(uri: Uri) {
        lifecycleScope.launch {
            val skin = withContext(Dispatchers.IO) {
                runCatching { DeltaSkinLoader.load(this@MainActivity, uri) }.getOrNull()
            }
            if (skin != null) {
                binding.skinView.applySkin(skin)
                showImportedSkinControls()
            } else {
                showDefaultControls()
                Toast.makeText(this@MainActivity, R.string.skin_load_failed, Toast.LENGTH_SHORT).show()
            }
            updateScreenLayout()
        }
    }

    private fun clearSkin() {
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            .edit()
            .remove(PREF_SKIN_URI)
            .apply()
        showDefaultControls()
        updateScreenLayout()
    }

    private fun configureDefaultControls() {
        binding.defaultControls.isClickable = true
        binding.defaultControls.setOnTouchListener { _, event ->
            handleDefaultControlsTouch(event)
            true
        }
        binding.defaultMenu.isClickable = true
        binding.defaultMenu.setOnTouchListener { view, event ->
            handleDefaultMenuTouch(view, event)
            true
        }
        listOf(binding.defaultControls, binding.skinView, binding.coverGamepad).forEach(::excludeGamepadFromSystemGestures)
    }

    private fun handleScreenTouch(event: MotionEvent): Boolean {
        if (playerModeActive && binding.libraryOverlay.visibility != View.VISIBLE && binding.menuOverlay.visibility != View.VISIBLE) {
            handlePlayerModeScreenTouch(event)
            return true
        }

        if (event.actionMasked == MotionEvent.ACTION_UP) {
            if (binding.libraryOverlay.visibility == View.VISIBLE) {
                hideLibraryOverlay()
            } else {
                dismissMenu()
            }
        }
        return true
    }

    private fun handlePlayerModeScreenTouch(event: MotionEvent) {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN,
            MotionEvent.ACTION_POINTER_DOWN,
            -> {
                val pointerId = event.getPointerId(event.actionIndex)
                val action = resolvePlayerModeAction(event.getX(event.actionIndex), event.getY(event.actionIndex))
                if (action != null) {
                    playerPointerActions[pointerId] = action
                    session?.sendCommand(EmulatorSession.CMD_PLAYER_DOWN, action)
                }
                binding.screenView.parent?.requestDisallowInterceptTouchEvent(true)
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_POINTER_UP,
            -> {
                val pointerId = event.getPointerId(event.actionIndex)
                playerPointerActions.remove(pointerId)?.let { action ->
                    session?.sendCommand(EmulatorSession.CMD_PLAYER_UP, action)
                }
                if (event.actionMasked == MotionEvent.ACTION_UP || playerPointerActions.isEmpty()) {
                    binding.screenView.parent?.requestDisallowInterceptTouchEvent(false)
                }
            }

            MotionEvent.ACTION_CANCEL -> {
                releasePlayerModeTouches()
                binding.screenView.parent?.requestDisallowInterceptTouchEvent(false)
            }
        }
    }

    private fun releasePlayerModeTouches() {
        playerPointerActions.values.toList().forEach { action ->
            session?.sendCommand(EmulatorSession.CMD_PLAYER_UP, action)
        }
        playerPointerActions.clear()
    }

    private fun resolvePlayerModeAction(viewX: Float, viewY: Float): Int? {
        val game = gameScreenRect(binding.screenView.width.toFloat(), binding.screenView.height.toFloat())
        if (!game.contains(viewX, viewY)) return null
        val gbX = ((viewX - game.left) * EmulatorSession.SCREEN_WIDTH / game.width()).toInt()
        val gbY = ((viewY - game.top) * EmulatorSession.SCREEN_HEIGHT / game.height()).toInt()
        return playerModeButtons.firstOrNull { it.bounds.contains(gbX, gbY) }?.action
    }

    private fun observeFoldState() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                WindowInfoTracker.getOrCreate(this@MainActivity)
                    .windowLayoutInfo(this@MainActivity)
                    .collect { layoutInfo ->
                        val flexFeature = layoutInfo.displayFeatures
                            .filterIsInstance<FoldingFeature>()
                            .firstOrNull { feature ->
                                feature.state == FoldingFeature.State.HALF_OPENED &&
                                    feature.orientation == FoldingFeature.Orientation.HORIZONTAL
                            }
                        val active = flexFeature != null
                        if (flexModeActive != active) {
                            flexModeActive = active
                            updateScreenLayout()
                        }
                    }
            }
        }
    }

    private fun handleDefaultMenuTouch(view: View, event: MotionEvent) {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                binding.defaultControls.parent?.requestDisallowInterceptTouchEvent(true)
                view.isPressed = true
                lastMenuAnchor = viewBoundsInRoot(view)
                showSkinMenu(lastMenuAnchor)
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_CANCEL,
            -> {
                view.isPressed = false
                binding.defaultControls.parent?.requestDisallowInterceptTouchEvent(false)
            }
        }
    }

    private fun handleDefaultControlsTouch(event: MotionEvent) {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN,
            MotionEvent.ACTION_POINTER_DOWN,
            -> binding.defaultControls.parent?.requestDisallowInterceptTouchEvent(true)

            MotionEvent.ACTION_CANCEL -> {
                binding.defaultControls.parent?.requestDisallowInterceptTouchEvent(false)
                clearDefaultTouches()
                return
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_POINTER_UP,
            -> {
                val pointerId = event.getPointerId(event.actionIndex)
                defaultPointerKeys.remove(pointerId)
                if (event.actionMasked == MotionEvent.ACTION_UP || defaultPointerKeys.isEmpty()) {
                    binding.defaultControls.parent?.requestDisallowInterceptTouchEvent(false)
                }
            }
        }

        if (event.actionMasked != MotionEvent.ACTION_UP && event.actionMasked != MotionEvent.ACTION_POINTER_UP) {
            for (index in 0 until event.pointerCount) {
                val pointerId = event.getPointerId(index)
                val x = event.getX(index)
                val y = event.getY(index)
                defaultPointerKeys[pointerId] = resolveDefaultKeys(x, y)
            }
            binding.defaultControls.parent?.requestDisallowInterceptTouchEvent(true)
        }
        syncDefaultPressedKeys()
        syncDefaultPressedViews()
    }

    private fun resolveDefaultKeys(x: Float, y: Float): Set<Int> {
        val keys = linkedSetOf<Int>()
        if (viewBoundsInDefaultControls(binding.defaultDpad).contains(x, y)) {
            keys += resolveDefaultDpad(x, y)
        }
        if (viewBoundsInDefaultControls(binding.defaultA).contains(x, y)) {
            keys += EmulatorSession.GB_KEY_A
        }
        if (viewBoundsInDefaultControls(binding.defaultB).contains(x, y)) {
            keys += EmulatorSession.GB_KEY_B
        }
        if (viewBoundsInDefaultControls(binding.defaultSelect).contains(x, y)) {
            keys += EmulatorSession.GB_KEY_SELECT
        }
        if (viewBoundsInDefaultControls(binding.defaultStart).contains(x, y)) {
            keys += EmulatorSession.GB_KEY_START
        }
        return keys
    }

    private fun resolveDefaultDpad(x: Float, y: Float): Set<Int> {
        val dpad = viewBoundsInDefaultControls(binding.defaultDpad)
        val result = linkedSetOf<Int>()
        val nx = ((x - dpad.centerX()) / (dpad.width() / 2f)).coerceIn(-1f, 1f)
        val ny = ((y - dpad.centerY()) / (dpad.height() / 2f)).coerceIn(-1f, 1f)

        if (kotlin.math.abs(nx) > 0.24f) {
            result += if (nx < 0f) EmulatorSession.GB_KEY_LEFT else EmulatorSession.GB_KEY_RIGHT
        }
        if (kotlin.math.abs(ny) > 0.24f) {
            result += if (ny < 0f) EmulatorSession.GB_KEY_UP else EmulatorSession.GB_KEY_DOWN
        }
        if (result.isEmpty()) {
            result += if (kotlin.math.abs(nx) >= kotlin.math.abs(ny)) {
                if (nx < 0f) EmulatorSession.GB_KEY_LEFT else EmulatorSession.GB_KEY_RIGHT
            } else {
                if (ny < 0f) EmulatorSession.GB_KEY_UP else EmulatorSession.GB_KEY_DOWN
            }
        }
        return result
    }

    private fun syncDefaultPressedKeys() {
        val nextKeys = defaultPointerKeys.values.flatten().toSet()
        val toRelease = defaultPressedKeys - nextKeys
        val toPress = nextKeys - defaultPressedKeys
        toRelease.forEach { key ->
            if (!handleMenuKeyInput(key, false)) {
                session?.setKeyPressed(key, false)
            }
        }
        toPress.forEach { key ->
            if (!handleMenuKeyInput(key, true)) {
                session?.setKeyPressed(key, true)
            }
        }
        defaultPressedKeys.clear()
        defaultPressedKeys += nextKeys
    }

    private fun releaseDefaultControlKeys() {
        val keys = defaultPressedKeys.toList()
        defaultPressedKeys.clear()
        defaultPointerKeys.clear()
        keys.forEach { session?.setKeyPressed(it, false) }
        syncDefaultPressedViews()
    }

    private fun clearDefaultTouches() {
        releaseDefaultControlKeys()
        binding.defaultControls.parent?.requestDisallowInterceptTouchEvent(false)
    }

    private fun syncDefaultPressedViews() {
        binding.defaultUp.isPressed = EmulatorSession.GB_KEY_UP in defaultPressedKeys
        binding.defaultDown.isPressed = EmulatorSession.GB_KEY_DOWN in defaultPressedKeys
        binding.defaultLeft.isPressed = EmulatorSession.GB_KEY_LEFT in defaultPressedKeys
        binding.defaultRight.isPressed = EmulatorSession.GB_KEY_RIGHT in defaultPressedKeys
        binding.defaultA.isPressed = EmulatorSession.GB_KEY_A in defaultPressedKeys
        binding.defaultB.isPressed = EmulatorSession.GB_KEY_B in defaultPressedKeys
        binding.defaultSelect.isPressed = EmulatorSession.GB_KEY_SELECT in defaultPressedKeys
        binding.defaultStart.isPressed = EmulatorSession.GB_KEY_START in defaultPressedKeys
    }

    private fun showDefaultControls() {
        importedSkinActive = false
        releaseDefaultControlKeys()
        binding.skinView.visibility = View.GONE
        binding.defaultControls.visibility = if (coverModeActive) View.GONE else View.VISIBLE
        binding.coverGamepad.visibility = if (coverModeActive) View.VISIBLE else View.GONE
    }

    private fun showImportedSkinControls() {
        importedSkinActive = true
        releaseDefaultControlKeys()
        binding.defaultControls.visibility = View.GONE
        binding.skinView.visibility = if (coverModeActive) View.GONE else View.VISIBLE
        binding.coverGamepad.visibility = if (coverModeActive) View.VISIBLE else View.GONE
    }

    private fun viewBoundsInRoot(view: View): RectF {
        return viewBoundsInRoot(view, RectF(0f, 0f, view.width.toFloat(), view.height.toFloat()))
    }

    private fun viewBoundsInRoot(view: View, localBounds: RectF): RectF {
        val rootLocation = IntArray(2)
        val viewLocation = IntArray(2)
        binding.root.getLocationOnScreen(rootLocation)
        view.getLocationOnScreen(viewLocation)
        val left = (viewLocation[0] - rootLocation[0]) + localBounds.left
        val top = (viewLocation[1] - rootLocation[1]) + localBounds.top
        return RectF(left, top, left + localBounds.width(), top + localBounds.height())
    }

    private fun viewBoundsInDefaultControls(view: View): RectF {
        val controlsLocation = IntArray(2)
        val viewLocation = IntArray(2)
        binding.defaultControls.getLocationOnScreen(controlsLocation)
        view.getLocationOnScreen(viewLocation)
        val left = (viewLocation[0] - controlsLocation[0]).toFloat()
        val top = (viewLocation[1] - controlsLocation[1]).toFloat()
        return RectF(left, top, left + view.width, top + view.height)
    }

    private fun excludeGamepadFromSystemGestures(view: View) {
        if (Build.VERSION.SDK_INT < 29) return
        val update = {
            view.systemGestureExclusionRects = listOf(Rect(0, 0, view.width, view.height))
        }
        view.addOnLayoutChangeListener { changedView, _, _, _, _, _, _, _, _ ->
            changedView.systemGestureExclusionRects = listOf(Rect(0, 0, changedView.width, changedView.height))
        }
        view.post(update)
    }

    private fun updateScreenLayout() {
        refreshCoverMode()
        moveTrackTextForLayout()
        configureMainColumnLayout()

        val flexLayout = flexModeActive && !coverModeActive
        val mainParams = binding.mainColumn.layoutParams
        mainParams.height = if (flexLayout || coverModeActive) {
            ViewGroup.LayoutParams.MATCH_PARENT
        } else {
            ViewGroup.LayoutParams.WRAP_CONTENT
        }
        binding.mainColumn.layoutParams = mainParams

        val screenParams = binding.screenFrame.layoutParams as LinearLayout.LayoutParams
        val horizontalMargin = if (screenMode == ScreenMode.FULL) {
            0
        } else if (coverModeActive) {
            0
        } else {
            (24f * resources.displayMetrics.density).toInt()
        }
        screenParams.marginStart = horizontalMargin
        screenParams.marginEnd = horizontalMargin
        screenParams.width = ViewGroup.LayoutParams.MATCH_PARENT
        screenParams.height = screenFrameContentHeight(horizontalMargin, flexLayout)
        screenParams.weight = 0f
        binding.screenFrame.layoutParams = screenParams
        binding.screenFrame.setPadding(0, 0, 0, if (flexLayout) dp(56) else 0)

        val screenViewParams = binding.screenView.layoutParams
        screenViewParams.width = ViewGroup.LayoutParams.MATCH_PARENT
        screenViewParams.height = ViewGroup.LayoutParams.MATCH_PARENT
        binding.screenView.layoutParams = screenViewParams

        configureControlsLayout(binding.defaultControls)
        configureControlsLayout(binding.skinView)
        configureCoverGamepadLayout()
        configureFlexBottomSpacer()
        configureTrackTextLayout()
        applyControlVisibility()
        binding.trackText.visibility = if (coverModeActive) View.GONE else View.VISIBLE
        binding.hintText.visibility = if (flexLayout || coverModeActive) View.GONE else View.VISIBLE
    }

    private fun screenFrameContentHeight(horizontalMargin: Int, flexLayout: Boolean): Int {
        val rootWidth = binding.rootScroll.width.takeIf { it > 0 } ?: resources.displayMetrics.widthPixels
        val contentWidth = (
            rootWidth -
                binding.mainColumn.paddingLeft -
                binding.mainColumn.paddingRight -
                horizontalMargin * 2
            ).coerceAtLeast(1)
        val screenHeight = contentWidth * EmulatorSession.SCREEN_HEIGHT / EmulatorSession.SCREEN_WIDTH
        return screenHeight + if (flexLayout) dp(56) else 0
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

    private fun configureMainColumnLayout() {
        val flexLayout = flexModeActive && !coverModeActive
        binding.mainColumn.setPadding(
            if (coverModeActive) 0 else dp(20),
            if (flexLayout || coverModeActive) 0 else dp(12),
            if (coverModeActive) 0 else dp(20),
            if (flexLayout || coverModeActive) 0 else dp(20),
        )
    }

    private fun configureControlsLayout(view: View) {
        val flexLayout = flexModeActive && !coverModeActive
        val params = view.layoutParams as LinearLayout.LayoutParams
        params.width = ViewGroup.LayoutParams.MATCH_PARENT
        params.height = ViewGroup.LayoutParams.WRAP_CONTENT
        params.weight = 0f
        params.topMargin = if (flexLayout) 0 else dp(48)
        view.layoutParams = params
        if (view === binding.defaultControls) {
            binding.defaultControls.gravity = if (flexLayout) {
                Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            } else {
                Gravity.CENTER_VERTICAL
            }
            binding.defaultControls.setPadding(
                binding.defaultControls.paddingLeft,
                if (flexLayout) 0 else dp(8),
                binding.defaultControls.paddingRight,
                if (flexLayout) dp(56) else dp(8),
            )
        } else if (view === binding.skinView) {
            binding.skinView.setPadding(
                binding.skinView.paddingLeft,
                if (flexLayout) dp(72) else 0,
                binding.skinView.paddingRight,
                0,
            )
        }
    }

    private fun configureCoverGamepadLayout() {
        val params = binding.coverGamepad.layoutParams as FrameLayout.LayoutParams
        params.width = ViewGroup.LayoutParams.MATCH_PARENT
        params.height = ViewGroup.LayoutParams.MATCH_PARENT
        params.gravity = Gravity.BOTTOM
        binding.coverGamepad.layoutParams = params
    }

    private fun configureFlexBottomSpacer() {
        val flexLayout = flexModeActive && !coverModeActive
        val params = binding.flexBottomSpacer.layoutParams as LinearLayout.LayoutParams
        params.width = ViewGroup.LayoutParams.MATCH_PARENT
        params.height = if (flexLayout) 0 else 0
        params.weight = if (flexLayout) 1f else 0f
        binding.flexBottomSpacer.layoutParams = params
        binding.flexBottomSpacer.visibility = if (flexLayout) View.VISIBLE else View.GONE
    }

    private fun configureTrackTextLayout() {
        val flexLayout = flexModeActive && !coverModeActive
        val params = binding.trackText.layoutParams as LinearLayout.LayoutParams
        params.topMargin = if (flexLayout) 0 else dp(16)
        params.bottomMargin = if (flexLayout) dp(12) else 0
        binding.trackText.layoutParams = params
        binding.trackText.gravity = if (flexLayout) Gravity.CENTER else Gravity.NO_GRAVITY
        binding.trackText.maxLines = if (flexLayout) 1 else Int.MAX_VALUE
    }

    private fun moveTrackTextForLayout() {
        val column = binding.mainColumn
        val currentIndex = column.indexOfChild(binding.trackText)
        val desiredIndex = trackTextLayoutIndex()
        if (currentIndex == desiredIndex) return

        column.removeView(binding.trackText)
        val insertIndex = trackTextLayoutIndex().coerceIn(0, column.childCount)
        column.addView(binding.trackText, insertIndex)
    }

    private fun trackTextLayoutIndex(): Int {
        val column = binding.mainColumn
        return if (flexModeActive && !coverModeActive) {
            column.indexOfChild(binding.defaultControls).coerceAtLeast(0)
        } else {
            column.indexOfChild(binding.hintText).coerceAtLeast(0)
        }
    }

    private fun applyControlVisibility() {
        if (coverModeActive) {
            releaseDefaultControlKeys()
            binding.skinView.visibility = View.GONE
            binding.defaultControls.visibility = View.GONE
            binding.coverGamepad.visibility = View.VISIBLE
            return
        }
        binding.coverGamepad.visibility = View.GONE
        if (importedSkinActive) {
            binding.defaultControls.visibility = View.GONE
            binding.skinView.visibility = View.VISIBLE
        } else {
            binding.skinView.visibility = View.GONE
            binding.defaultControls.visibility = View.VISIBLE
        }
    }

    private fun refreshCoverMode(): Boolean {
        val next = isCoverDisplay()
        if (coverModeActive == next) return false
        coverModeActive = next
        if (coverModeActive) {
            releaseDefaultControlKeys()
        } else {
            binding.coverGamepad.releaseKeys()
        }
        return true
    }

    private fun isCoverDisplay(): Boolean {
        val configuration = resources.configuration
        return maxOf(configuration.screenWidthDp, configuration.screenHeightDp) < COVER_DISPLAY_LONG_SIDE_DP
    }

    private fun showSkinMenu(anchorBounds: RectF) {
        dismissMenu()
        menuEntries = buildMenuEntries()
        selectedMenuIndex = 0

        binding.menuPanel.removeAllViews()
        menuLabels = menuEntries.map { entry ->
            TextView(this).apply {
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
                setPadding(dp(16), dp(12), dp(16), dp(12))
                text = entry.title
                textSize = 16f
                isClickable = true
                isFocusable = true
                setOnClickListener {
                    selectedMenuIndex = menuEntries.indexOfFirst { it.id == entry.id }.coerceAtLeast(0)
                    updateMenuSelection()
                    activateMenuSelection()
                }
            }.also(binding.menuPanel::addView)
        }
        updateMenuSelection()
        positionMenuPanel(anchorBounds)
        binding.menuOverlay.visibility = View.VISIBLE
        menuOpen = true
    }

    private fun positionMenuPanel(anchorBounds: RectF) {
        val frameBounds = viewBoundsInRoot(binding.screenFrame)
        val params = binding.menuScroll.layoutParams as FrameLayout.LayoutParams
        params.gravity = if (coverModeActive) {
            Gravity.CENTER
        } else if (anchorBounds.centerX() < frameBounds.centerX()) {
            Gravity.START or Gravity.BOTTOM
        } else {
            Gravity.END or Gravity.BOTTOM
        }
        binding.menuScroll.layoutParams = params
        binding.menuScroll.scrollTo(0, 0)
    }

    private fun buildMenuEntries(): List<MenuEntry> {
        val modeLabel = if (screenMode == ScreenMode.FULL) {
            getString(R.string.screen_mode_full)
        } else {
            getString(R.string.screen_mode_inset)
        }
        return buildList {
            add(MenuEntry(MENU_LIBRARY, getString(R.string.menu_library)))
            add(MenuEntry(MENU_SCREEN_MODE, "${getString(R.string.menu_screen_mode)}: $modeLabel"))
            add(MenuEntry(MENU_INVERT_SCREEN, "${getString(R.string.menu_invert_screen)}: ${onOffLabel(PlaybackSettings.isScreenInverted(this@MainActivity))}"))
            add(MenuEntry(MENU_SETTINGS, getString(R.string.menu_settings)))
            if (coverModeActive) {
                add(MenuEntry(MENU_COVER_GAMEPAD_CONFIG, getString(R.string.menu_cover_gamepad_config)))
            }
        }
    }

    private fun updateMenuSelection() {
        menuLabels.forEachIndexed { index, label ->
            val selected = index == selectedMenuIndex
            label.setBackgroundColor(if (selected) Color.parseColor("#3B82F6") else Color.TRANSPARENT)
            label.setTextColor(if (selected) Color.WHITE else Color.parseColor("#F2F4F8"))
        }
    }

    private fun activateMenuSelection() {
        val selectedId = menuEntries.getOrNull(selectedMenuIndex)?.id
        when (selectedId) {
            MENU_LIBRARY -> {
                dismissMenu()
                showLibraryOverlay()
            }

            MENU_SCREEN_MODE -> {
                screenMode = if (screenMode == ScreenMode.FULL) ScreenMode.INSET else ScreenMode.FULL
                saveScreenMode(screenMode)
                dismissMenu()
                updateScreenLayout()
            }

            MENU_INVERT_SCREEN -> {
                val inverted = !PlaybackSettings.isScreenInverted(this)
                PlaybackSettings.setScreenInverted(this, inverted)
                applyScreenColorFilter()
                dismissMenu()
            }

            MENU_COVER_GAMEPAD_CONFIG -> {
                dismissMenu()
                if (coverModeActive) {
                    binding.coverGamepad.setConfigMode(true)
                    Toast.makeText(this, R.string.cover_gamepad_config_hint, Toast.LENGTH_LONG).show()
                }
            }

            MENU_SETTINGS -> {
                dismissMenu()
                showSettingsDialog()
            }
        }
    }

    private fun applyScreenColorFilter() {
        binding.screenView.colorFilter = if (PlaybackSettings.isScreenInverted(this)) {
            ColorMatrixColorFilter(INVERT_COLOR_MATRIX)
        } else {
            null
        }
    }

    private fun onOffLabel(enabled: Boolean): String {
        return getString(if (enabled) R.string.setting_on else R.string.setting_off)
    }

    private fun showSettingsDialog() {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), dp(4))
        }
        val scrollView = object : ScrollView(this) {
            override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
                val cappedHeightSpec = if (coverModeActive) {
                    val availableHeight = MeasureSpec.getSize(heightMeasureSpec)
                    val maxHeight = (resources.displayMetrics.heightPixels * 0.72f).toInt()
                    MeasureSpec.makeMeasureSpec(minOf(availableHeight, maxHeight), MeasureSpec.AT_MOST)
                } else {
                    heightMeasureSpec
                }
                super.onMeasure(widthMeasureSpec, cappedHeightSpec)
            }
        }.apply {
            isFillViewport = false
            overScrollMode = View.OVER_SCROLL_IF_CONTENT_SCROLLS
            addView(
                container,
                ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ),
            )
        }
        var dialog: AlertDialog? = null

        fun settingsSection(titleText: String): View {
            return TextView(this).apply {
                text = titleText
                textSize = 13f
                setTextColor(Color.parseColor("#5B6B82"))
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setPadding(0, dp(18), 0, dp(4))
            }
        }

        fun settingsActionRow(
            titleText: String,
            summaryText: String? = null,
            enabled: Boolean = true,
            action: () -> Unit,
        ): View {
            return LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(0, dp(12), 0, dp(10))
                isEnabled = enabled
                isClickable = enabled
                alpha = if (enabled) 1f else 0.45f
                addView(TextView(this@MainActivity).apply {
                    text = titleText
                    textSize = 16f
                    setTextColor(Color.parseColor("#1F2937"))
                    setTypeface(typeface, android.graphics.Typeface.BOLD)
                })
                if (summaryText != null) {
                    addView(TextView(this@MainActivity).apply {
                        text = summaryText
                        textSize = 13f
                        setTextColor(Color.parseColor("#596275"))
                    })
                }
                if (enabled) {
                    setOnClickListener { action() }
                }
            }
        }

        val guardTitle = TextView(this).apply {
            text = getString(R.string.settings_media_resume_guard_title)
            textSize = 16f
            setTextColor(Color.parseColor("#1F2937"))
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        val guardSummary = TextView(this).apply {
            text = getString(R.string.settings_media_resume_guard_summary)
            textSize = 13f
            setTextColor(Color.parseColor("#596275"))
        }
        val guardTextColumn = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            addView(guardTitle)
            addView(guardSummary)
        }
        val guardSwitch = Switch(this).apply {
            isChecked = PlaybackSettings.isMediaResumeGuardEnabled(this@MainActivity)
        }
        val guardRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(10), 0, dp(10))
            isClickable = true
            addView(guardTextColumn)
            addView(guardSwitch)
        }

        val timeoutTitle = TextView(this).apply {
            text = getString(R.string.settings_media_resume_timeout_title)
            textSize = 16f
            setTextColor(Color.parseColor("#1F2937"))
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        val timeoutValue = TextView(this).apply {
            textSize = 13f
            setTextColor(Color.parseColor("#596275"))
        }
        val timeoutRow = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(12), 0, dp(10))
            isClickable = true
            addView(timeoutTitle)
            addView(timeoutValue)
        }

        fun currentTimeoutLabel(): String {
            val currentValue = PlaybackSettings.mediaResumeTimeoutMs(this)
            val option = PlaybackSettings.MEDIA_RESUME_TIMEOUT_OPTIONS
                .firstOrNull { it.valueMs == currentValue }
                ?: PlaybackSettings.MEDIA_RESUME_TIMEOUT_OPTIONS
                    .first { it.valueMs == PlaybackSettings.DEFAULT_MEDIA_RESUME_TIMEOUT_MS }
            return getString(option.labelResId)
        }

        fun updateSettingsRows() {
            val enabled = guardSwitch.isChecked
            timeoutValue.text = currentTimeoutLabel()
            timeoutRow.isEnabled = enabled
            timeoutRow.alpha = if (enabled) 1f else 0.45f
        }

        guardRow.setOnClickListener {
            guardSwitch.isChecked = !guardSwitch.isChecked
        }
        guardSwitch.setOnCheckedChangeListener { _, isChecked ->
            PlaybackSettings.setMediaResumeGuardEnabled(this, isChecked)
            updateSettingsRows()
        }
        timeoutRow.setOnClickListener {
            if (guardSwitch.isChecked) {
                showMediaResumeTimeoutDialog { updateSettingsRows() }
            }
        }

        container.addView(settingsSection(getString(R.string.settings_section_general)))
        container.addView(settingsActionRow(getString(R.string.settings_language_title), currentLanguageLabel()) {
            showLanguageDialog {
                dialog?.dismiss()
                recreate()
            }
        })
        container.addView(settingsSection(getString(R.string.settings_section_skin)))
        container.addView(settingsActionRow(
            getString(R.string.menu_choose_skin),
            getString(R.string.settings_choose_skin_summary),
        ) {
            dialog?.dismiss()
            skinPicker.launch(arrayOf("*/*"))
        })
        container.addView(settingsActionRow(
            getString(R.string.menu_clear_skin),
            enabled = importedSkinActive,
        ) {
            clearSkin()
            Toast.makeText(this, R.string.settings_default_controls_applied, Toast.LENGTH_SHORT).show()
        })
        container.addView(settingsSection(getString(R.string.settings_section_media)))
        container.addView(guardRow)
        container.addView(timeoutRow)
        updateSettingsRows()

        dialog = AlertDialog.Builder(this)
            .setTitle(R.string.menu_settings)
            .setView(scrollView)
            .setPositiveButton(R.string.settings_close, null)
            .show()
    }

    private fun currentLanguageLabel(): String {
        val current = PlaybackSettings.appLanguageCode(this)
        val option = PlaybackSettings.APP_LANGUAGE_OPTIONS
            .firstOrNull { it.code == current }
            ?: PlaybackSettings.APP_LANGUAGE_OPTIONS.first()
        return getString(option.labelResId)
    }

    private fun showLanguageDialog(onSaved: () -> Unit) {
        val options = PlaybackSettings.APP_LANGUAGE_OPTIONS
        val current = PlaybackSettings.appLanguageCode(this)
        val currentIndex = options.indexOfFirst { it.code == current }.coerceAtLeast(0)
        val labels = options.map { getString(it.labelResId) }.toTypedArray()

        AlertDialog.Builder(this)
            .setTitle(R.string.settings_language_title)
            .setSingleChoiceItems(labels, currentIndex) { dialog, which ->
                PlaybackSettings.setAppLanguageCode(this, options[which].code)
                dialog.dismiss()
                onSaved()
            }
            .setNegativeButton(R.string.settings_cancel, null)
            .show()
    }

    private fun showMediaResumeTimeoutDialog(onSaved: () -> Unit) {
        val options = PlaybackSettings.MEDIA_RESUME_TIMEOUT_OPTIONS
        val currentValue = PlaybackSettings.mediaResumeTimeoutMs(this)
        val currentIndex = options.indexOfFirst { it.valueMs == currentValue }
            .takeIf { it >= 0 }
            ?: options.indexOfFirst { it.valueMs == PlaybackSettings.DEFAULT_MEDIA_RESUME_TIMEOUT_MS }
        val labels = options.map { getString(it.labelResId) }.toTypedArray()

        AlertDialog.Builder(this)
            .setTitle(R.string.settings_media_resume_timeout_title)
            .setSingleChoiceItems(labels, currentIndex) { dialog, which ->
                val option = options[which]
                PlaybackSettings.setMediaResumeTimeoutMs(this, option.valueMs)
                Toast.makeText(
                    this,
                    getString(R.string.settings_media_resume_timeout_saved, getString(option.labelResId)),
                    Toast.LENGTH_SHORT,
                ).show()
                dialog.dismiss()
                onSaved()
            }
            .setNegativeButton(R.string.settings_cancel, null)
            .show()
    }

    private fun showLibraryOverlay() {
        dismissMenu()
        dismissLibraryActionPopup()
        libraryEntries = buildLibraryEntries()
        val activeIndex = libraryEntries.indexOfFirst { it.active }
        selectedLibraryIndex = if (activeIndex >= 0) {
            activeIndex
        } else {
            selectedLibraryIndex.coerceIn(0, libraryEntries.lastIndex.coerceAtLeast(0))
        }
        libraryEllipsisFocused = false
        rebuildLibraryRows()
        binding.libraryOverlay.visibility = View.VISIBLE
    }

    private fun hideLibraryOverlay() {
        dismissLibraryActionPopup()
        binding.libraryOverlay.visibility = View.GONE
    }

    private fun buildLibraryEntries(): List<LibraryEntry> {
        val activeId = EmulatorRepository.activeRomId(this)
        val bundledEntries = EmulatorRepository.bundledRoms(this).map { rom ->
            val songCount = runCatching {
                RomAssetInstaller.installBundled(this, rom).metadata.songs.size
            }.getOrDefault(0)
            val state = if (activeId == rom.id) getString(R.string.library_active) else getString(R.string.library_built_in)
            LibraryEntry(
                kind = LibraryEntryKind.BUNDLED,
                title = rom.title,
                subtitle = "$state - ${getString(R.string.library_songs, songCount)}",
                bundled = rom,
                active = activeId == rom.id,
            )
        }
        val registeredEntries = EmulatorRepository.registeredRoms(this).map { rom ->
            val fullId = "${RomAssetInstaller.REGISTERED_ROM_PREFIX}${rom.id}"
            val state = if (activeId == fullId) getString(R.string.library_active) else getString(R.string.library_registered)
            LibraryEntry(
                kind = LibraryEntryKind.REGISTERED,
                title = rom.title,
                subtitle = "$state - ${getString(R.string.library_songs, rom.songCount)}",
                registered = rom,
                active = activeId == fullId,
            )
        }
        return bundledEntries + registeredEntries + LibraryEntry(
            kind = LibraryEntryKind.REGISTER,
            title = getString(R.string.library_register_rom),
            subtitle = "",
        )
    }

    private fun rebuildLibraryRows() {
        binding.libraryRows.removeAllViews()
        libraryRowViews = libraryEntries.mapIndexed { index, entry ->
            createLibraryRow(index, entry).also(binding.libraryRows::addView)
        }
        updateLibrarySelection()
    }

    private fun createLibraryRow(index: Int, entry: LibraryEntry): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(10), dp(8), dp(8), dp(8))
            isClickable = true
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                topMargin = dp(6)
            }
            setOnClickListener {
                selectedLibraryIndex = index
                libraryEllipsisFocused = false
                updateLibrarySelection()
                activateLibrarySelection()
            }
        }

        if (entry.kind == LibraryEntryKind.REGISTER) {
            row.minimumHeight = dp(52)
            val plus = TextView(this).apply {
                text = "+"
                textSize = 24f
                setTextColor(Color.parseColor("#F2F4F8"))
                gravity = Gravity.CENTER
                layoutParams = LinearLayout.LayoutParams(dp(38), dp(38))
            }
            val title = TextView(this).apply {
                text = entry.title
                textSize = 16f
                setTextColor(Color.parseColor("#F2F4F8"))
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            }
            row.addView(plus)
            row.addView(title)
            return row
        }

        val swatch = TextView(this).apply {
            text = if (entry.kind == LibraryEntryKind.BUNDLED) "B" else "R"
            textSize = 14f
            gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#111720"))
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setBackgroundColor(if (entry.kind == LibraryEntryKind.BUNDLED) Color.parseColor("#8BD3A7") else Color.parseColor("#F2C56B"))
            layoutParams = LinearLayout.LayoutParams(dp(38), dp(38))
        }
        val textColumn = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginStart = dp(12)
            }
        }
        textColumn.addView(TextView(this).apply {
            text = entry.title
            textSize = 15f
            maxLines = 1
            setTextColor(Color.parseColor("#F2F4F8"))
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        textColumn.addView(TextView(this).apply {
            text = entry.subtitle
            textSize = 12f
            maxLines = 1
            setTextColor(Color.parseColor("#A8B2C1"))
        })
        val ellipsis = TextView(this).apply {
            text = "..."
            textSize = 20f
            gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#F2F4F8"))
            isClickable = true
            layoutParams = LinearLayout.LayoutParams(dp(44), dp(44))
            setOnClickListener {
                selectedLibraryIndex = index
                libraryEllipsisFocused = true
                updateLibrarySelection()
                showLibraryActions(entry, this)
            }
        }
        row.addView(swatch)
        row.addView(textColumn)
        row.addView(ellipsis)
        return row
    }

    private fun updateLibrarySelection() {
        libraryRowViews.forEachIndexed { index, row ->
            val entry = libraryEntries.getOrNull(index)
            val selected = index == selectedLibraryIndex
            val color = when {
                selected && libraryEllipsisFocused && entry?.kind != LibraryEntryKind.REGISTER -> "#34465C"
                selected -> "#29394C"
                entry?.kind == LibraryEntryKind.REGISTER -> "#172233"
                else -> "#202632"
            }
            row.setBackgroundColor(Color.parseColor(color))
        }
        scrollSelectedLibraryRowIntoView()
    }

    private fun scrollSelectedLibraryRowIntoView() {
        val row = libraryRowViews.getOrNull(selectedLibraryIndex) ?: return
        binding.libraryScroll.post {
            val rowTop = row.top
            val rowBottom = row.bottom
            val visibleTop = binding.libraryScroll.scrollY
            val visibleBottom = visibleTop + binding.libraryScroll.height
            val targetY = when {
                rowTop < visibleTop -> rowTop
                rowBottom > visibleBottom -> rowBottom - binding.libraryScroll.height
                else -> return@post
            }.coerceAtLeast(0)
            binding.libraryScroll.smoothScrollTo(0, targetY)
        }
    }

    private fun activateLibrarySelection() {
        val entry = libraryEntries.getOrNull(selectedLibraryIndex) ?: return
        if (libraryEllipsisFocused && entry.kind != LibraryEntryKind.REGISTER) {
            showLibraryActions(entry, libraryRowViews[selectedLibraryIndex])
            return
        }
        when (entry.kind) {
            LibraryEntryKind.BUNDLED -> entry.bundled?.let {
                hideLibraryOverlay()
                loadBundledRom(it)
            }

            LibraryEntryKind.REGISTERED -> entry.registered?.let {
                hideLibraryOverlay()
                loadRegisteredRom(it)
            }

            LibraryEntryKind.REGISTER -> {
                hideLibraryOverlay()
                romPicker.launch(arrayOf("application/octet-stream", "*/*"))
            }
        }
    }

    private fun showLibraryActions(entry: LibraryEntry, anchor: View) {
        dismissLibraryActionPopup()
        val registered = entry.registered
        val actionRows = buildList {
            add(getString(R.string.library_play_load) to { activateLibraryRow(entry) })
            if (registered != null) {
                add(getString(R.string.library_open_directory) to { openRegisteredRomDirectory(registered) })
                add(getString(R.string.library_unregister) to { confirmUnregisterRom(registered) })
            }
        }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#151A22"))
            setPadding(dp(8), dp(8), dp(8), dp(8))
        }
        actionRows.forEach { (title, action) ->
            TextView(this).apply {
                text = title
                textSize = 15f
                setTextColor(Color.parseColor("#F2F4F8"))
                setPadding(dp(14), dp(10), dp(14), dp(10))
                isClickable = true
                setOnClickListener {
                    dismissLibraryActionPopup()
                    action()
                }
            }.also(container::addView)
        }
        libraryActionPopup = PopupWindow(
            container,
            ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
            true,
        ).apply {
            isTouchable = true
            isOutsideTouchable = true
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            showAsDropDown(anchor, -dp(8), 0)
        }
    }

    private fun activateLibraryRow(entry: LibraryEntry) {
        when (entry.kind) {
            LibraryEntryKind.BUNDLED -> entry.bundled?.let {
                hideLibraryOverlay()
                loadBundledRom(it)
            }

            LibraryEntryKind.REGISTERED -> entry.registered?.let {
                hideLibraryOverlay()
                loadRegisteredRom(it)
            }

            LibraryEntryKind.REGISTER -> Unit
        }
    }

    private fun dismissLibraryActionPopup() {
        libraryActionPopup?.dismiss()
        libraryActionPopup = null
    }

    private fun openRegisteredRomDirectory(registered: RegisteredRom?) {
        val uriText = registered?.sourceDirectoryUri ?: registered?.sourceUri
        val uri = uriText?.let(Uri::parse)
        if (uri == null) {
            Toast.makeText(this, R.string.library_directory_unavailable, Toast.LENGTH_SHORT).show()
            return
        }
        val intent = Intent(Intent.ACTION_VIEW).apply {
            data = uri
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        try {
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(this, R.string.library_directory_unavailable, Toast.LENGTH_SHORT).show()
        } catch (_: SecurityException) {
            Toast.makeText(this, R.string.library_directory_unavailable, Toast.LENGTH_SHORT).show()
        }
    }

    private fun confirmUnregisterRom(registered: RegisteredRom) {
        AlertDialog.Builder(this)
            .setTitle(R.string.library_unregister_title)
            .setMessage(getString(R.string.library_unregister_message, registered.title))
            .setNegativeButton(R.string.library_unregister_cancel, null)
            .setPositiveButton(R.string.library_unregister_confirm) { _, _ ->
                unregisterRom(registered)
            }
            .show()
    }

    private fun unregisterRom(registered: RegisteredRom) {
        val wasActive = EmulatorRepository.activeRomId(this) == "${RomAssetInstaller.REGISTERED_ROM_PREFIX}${registered.id}"
        val removed = EmulatorRepository.unregisterRegistered(this, registered)
        if (!removed) return
        if (wasActive) {
            session = EmulatorRepository.getOrCreate(this)
            session?.let {
                bindSession(it)
                it.setUiVisible(true)
                PlaybackService.start(this)
            } ?: showNoRomState()
        }
        showLibraryOverlay()
    }

    private fun loadBundledRom(bundled: BundledRom) {
        lifecycleScope.launch {
            val loadedSession = withContext(Dispatchers.IO) {
                runCatching { EmulatorRepository.installBundledAndStart(this@MainActivity, bundled) }.getOrNull()
            }
            if (loadedSession != null) {
                bindSession(loadedSession)
                loadedSession.setUiVisible(true)
                PlaybackService.start(this@MainActivity)
            } else {
                Toast.makeText(this@MainActivity, R.string.rom_load_failed, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun loadRegisteredRom(registered: RegisteredRom) {
        lifecycleScope.launch {
            val loadedSession = withContext(Dispatchers.IO) {
                runCatching { EmulatorRepository.installRegisteredAndStart(this@MainActivity, registered) }.getOrNull()
            }
            if (loadedSession != null) {
                bindSession(loadedSession)
                loadedSession.setUiVisible(true)
                PlaybackService.start(this@MainActivity)
            } else {
                Toast.makeText(this@MainActivity, R.string.rom_load_failed, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun dismissMenu() {
        binding.menuOverlay.visibility = View.GONE
        binding.menuPanel.removeAllViews()
        menuOpen = false
        menuLabels = emptyList()
        menuEntries = emptyList()
    }

    private fun handleMenuKeyInput(key: Int, pressed: Boolean): Boolean {
        if (!pressed) return false
        if (binding.libraryOverlay.visibility == View.VISIBLE) {
            return handleLibraryKeyInput(key)
        }
        if (!menuOpen) return false
        when (key) {
            EmulatorSession.GB_KEY_UP,
            EmulatorSession.GB_KEY_LEFT -> {
                selectedMenuIndex = if (selectedMenuIndex <= 0) menuEntries.lastIndex else selectedMenuIndex - 1
                updateMenuSelection()
                return true
            }

            EmulatorSession.GB_KEY_DOWN,
            EmulatorSession.GB_KEY_RIGHT -> {
                selectedMenuIndex = (selectedMenuIndex + 1) % menuEntries.size.coerceAtLeast(1)
                updateMenuSelection()
                return true
            }

            EmulatorSession.GB_KEY_A -> {
                activateMenuSelection()
                return true
            }

            EmulatorSession.GB_KEY_B -> {
                dismissMenu()
                return true
            }
        }
        return false
    }

    private fun handleLibraryKeyInput(key: Int): Boolean {
        if (libraryEntries.isEmpty()) return true
        when (key) {
            EmulatorSession.GB_KEY_UP -> {
                selectedLibraryIndex = if (selectedLibraryIndex <= 0) libraryEntries.lastIndex else selectedLibraryIndex - 1
                libraryEllipsisFocused = false
                dismissLibraryActionPopup()
                updateLibrarySelection()
                return true
            }

            EmulatorSession.GB_KEY_DOWN -> {
                selectedLibraryIndex = (selectedLibraryIndex + 1) % libraryEntries.size
                libraryEllipsisFocused = false
                dismissLibraryActionPopup()
                updateLibrarySelection()
                return true
            }

            EmulatorSession.GB_KEY_LEFT,
            EmulatorSession.GB_KEY_RIGHT -> {
                if (libraryEntries[selectedLibraryIndex].kind != LibraryEntryKind.REGISTER) {
                    libraryEllipsisFocused = !libraryEllipsisFocused
                    dismissLibraryActionPopup()
                    updateLibrarySelection()
                }
                return true
            }

            EmulatorSession.GB_KEY_A -> {
                activateLibrarySelection()
                return true
            }

            EmulatorSession.GB_KEY_B -> {
                hideLibraryOverlay()
                return true
            }
        }
        return true
    }

    private fun loadSavedSkinUri(): Uri? {
        val value = getSharedPreferences(PREFS_NAME, MODE_PRIVATE).getString(PREF_SKIN_URI, null)
        return value?.let(Uri::parse)
    }

    private fun saveSkinUri(uri: Uri) {
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            .edit()
            .putString(PREF_SKIN_URI, uri.toString())
            .apply()
    }

    private fun loadScreenMode(): ScreenMode {
        val value = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            .getString(PREF_SCREEN_MODE, ScreenMode.FULL.name)
        return runCatching { ScreenMode.valueOf(value ?: ScreenMode.FULL.name) }
            .getOrDefault(ScreenMode.FULL)
    }

    private fun saveScreenMode(mode: ScreenMode) {
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            .edit()
            .putString(PREF_SCREEN_MODE, mode.name)
            .apply()
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < 33) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) {
            return
        }
        ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        private const val PREFS_NAME = PlaybackSettings.PREFS_NAME
        private const val PREF_SKIN_URI = "delta_skin_uri"
        private const val PREF_SCREEN_MODE = "screen_mode"
        private const val MENU_LIBRARY = 1
        private const val MENU_SCREEN_MODE = 4
        private const val MENU_COVER_GAMEPAD_CONFIG = 5
        private const val MENU_SETTINGS = 6
        private const val MENU_INVERT_SCREEN = 7
        private const val COVER_DISPLAY_LONG_SIDE_DP = 600
        private val playerModeButtons = listOf(
            PlayerModeButton(EmulatorSession.PLAYER_ACTION_PREV, Rect(0, 56, 56, 80)),
            PlayerModeButton(EmulatorSession.PLAYER_ACTION_TOGGLE, Rect(56, 56, 104, 80)),
            PlayerModeButton(EmulatorSession.PLAYER_ACTION_NEXT, Rect(104, 56, 160, 80)),
            PlayerModeButton(EmulatorSession.PLAYER_ACTION_BACK, Rect(0, 96, 48, 120)),
            PlayerModeButton(EmulatorSession.PLAYER_ACTION_STOP, Rect(56, 96, 104, 120)),
            PlayerModeButton(EmulatorSession.PLAYER_ACTION_RPT, Rect(112, 96, 160, 120)),
        )
        private val INVERT_COLOR_MATRIX = floatArrayOf(
            -1f, 0f, 0f, 0f, 255f,
            0f, -1f, 0f, 0f, 255f,
            0f, 0f, -1f, 0f, 255f,
            0f, 0f, 0f, 1f, 0f,
        )
    }
}
