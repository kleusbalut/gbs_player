package io.github.kleusbalut.gbsplayer.android

object NativeBridge {
    init {
        System.loadLibrary("gbsplayer")
    }

    external fun nativeCreate(romPath: String, savePath: String): Long
    external fun nativeDestroy(handle: Long)
    external fun nativeFillAudio(handle: Long, pcm: ShortArray, frames: Int): Int
    external fun nativeGetStatus(handle: Long): IntArray
    external fun nativeGetDebugState(handle: Long): IntArray
    external fun nativeGetFrameToken(handle: Long): Int
    external fun nativeCopyFrame(handle: Long, pixels: IntArray)
    external fun nativeTapButton(handle: Long, key: Int)
    external fun nativeSetButton(handle: Long, key: Int, pressed: Boolean)
    external fun nativeSendCommand(handle: Long, command: Int, argument: Int)
    external fun nativeSetRenderingEnabled(handle: Long, enabled: Boolean)
    external fun nativeFlushSave(handle: Long)
}
