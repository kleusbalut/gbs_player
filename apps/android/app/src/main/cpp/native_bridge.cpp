#include <jni.h>
#include <atomic>
#include <chrono>
#include <fstream>
#include <mutex>
#include <string>
#include <vector>

extern "C" {
#include "gb.h"
}

namespace {
constexpr unsigned SAMPLE_RATE = 48000;
constexpr int SCREEN_WIDTH = 160;
constexpr int SCREEN_HEIGHT = 144;
constexpr size_t SCREEN_PIXELS = SCREEN_WIDTH * SCREEN_HEIGHT;
constexpr uint8_t HRAM_BASE = 0x80;
constexpr uint8_t STATUS_MAGIC_OFFSET = 0xE8 - HRAM_BASE;
constexpr uint8_t STATUS_SONG_OFFSET = 0xE9 - HRAM_BASE;
constexpr uint8_t STATUS_FLAGS_OFFSET = 0xEA - HRAM_BASE;
constexpr uint8_t STATUS_SECONDS_LO_OFFSET = 0xEC - HRAM_BASE;
constexpr uint8_t STATUS_SECONDS_HI_OFFSET = 0xED - HRAM_BASE;
constexpr uint8_t COMMAND_OFFSET = 0xEE - HRAM_BASE;
constexpr uint8_t COMMAND_ARG_OFFSET = 0xEF - HRAM_BASE;
constexpr uint8_t STATUS_DURATION_LO_OFFSET = 0xF0 - HRAM_BASE;
constexpr uint8_t STATUS_DURATION_HI_OFFSET = 0xF1 - HRAM_BASE;
constexpr uint8_t STATUS_REPEAT_OFFSET = 0xF2 - HRAM_BASE;
constexpr size_t QUEUE_TARGET_FRAMES = SAMPLE_RATE / 10;
constexpr size_t QUEUE_MAX_FRAMES = SAMPLE_RATE / 4;
constexpr auto SAVE_FLUSH_INTERVAL = std::chrono::seconds(2);

struct EmulatorState {
    GB_gameboy_t gb {};
    std::mutex mutex;
    std::vector<int16_t> pcm;
    size_t pcmRead = 0;
    size_t pcmWrite = 0;
    size_t pcmCount = 0;
    std::string savePath;
    std::vector<uint32_t> frame;
    std::atomic<int> frameToken {0};
    bool saveDirty = false;
    std::chrono::steady_clock::time_point lastSaveFlush {};
};

size_t pcm_available_samples(const EmulatorState *state)
{
    return state->pcmCount;
}

void pcm_drop_sample(EmulatorState *state)
{
    if (state->pcmCount == 0 || state->pcm.empty()) return;
    state->pcmRead = (state->pcmRead + 1) % state->pcm.size();
    state->pcmCount--;
}

void pcm_push_sample(EmulatorState *state, int16_t sample)
{
    if (state->pcm.empty()) return;
    if (state->pcmCount == state->pcm.size()) {
        pcm_drop_sample(state);
    }
    state->pcm[state->pcmWrite] = sample;
    state->pcmWrite = (state->pcmWrite + 1) % state->pcm.size();
    state->pcmCount++;
}

int16_t pcm_pop_sample(EmulatorState *state)
{
    if (state->pcmCount == 0 || state->pcm.empty()) return 0;
    const int16_t sample = state->pcm[state->pcmRead];
    state->pcmRead = (state->pcmRead + 1) % state->pcm.size();
    state->pcmCount--;
    return sample;
}

void load_android_boot_rom(GB_gameboy_t *gb, GB_boot_rom_t)
{
    // Keep a tiny stub available, but Android startup uses a direct post-boot
    // state setup below because the minimal stub path proved too fragile with
    // this GBDK-built ROM.
    static const unsigned char boot_stub[] = {
        0x3E, 0x01,             // ld a, $01
        0xE0, 0x50,             // ldh [$50], a
        0xC3, 0x00, 0x01,       // jp $0100
    };
    GB_load_boot_rom_from_buffer(gb, boot_stub, sizeof(boot_stub));
}

void force_cgb_post_boot_state(GB_gameboy_t *gb)
{
    gb->af = 0x1180;
    gb->bc = 0x0000;
    gb->de = 0xFF56;
    gb->hl = 0x000D;
    gb->sp = 0xFFFE;
    gb->pc = 0x0100;

    gb->io_registers[GB_IO_JOYP] = 0xCF;
    gb->io_registers[GB_IO_SC] = 0x7E;
    gb->io_registers[GB_IO_IF] = 0x00;
    gb->io_registers[GB_IO_TAC] = 0x00;
    gb->io_registers[GB_IO_LCDC] = 0x91;
    gb->io_registers[GB_IO_STAT] = 0x85;
    gb->io_registers[GB_IO_SCY] = 0x00;
    gb->io_registers[GB_IO_SCX] = 0x00;
    gb->io_registers[GB_IO_LYC] = 0x00;
    gb->io_registers[GB_IO_BGP] = 0xFC;
    gb->io_registers[GB_IO_OBP0] = 0xFF;
    gb->io_registers[GB_IO_OBP1] = 0xFF;
    gb->io_registers[GB_IO_WY] = 0x00;
    gb->io_registers[GB_IO_WX] = 0x00;
    gb->io_registers[GB_IO_KEY0] = 0x80;
    gb->io_registers[GB_IO_KEY1] = 0x00;
    gb->io_registers[GB_IO_BANK] = 0x01;
    gb->io_registers[GB_IO_VBK] = 0xFE;
    gb->io_registers[GB_IO_SVBK] = 0xF8;
    gb->interrupt_enable = 0x00;
    gb->ime = false;
    gb->boot_rom_finished = true;
    gb->cgb_mode = true;
    gb->cgb_ram_bank = 1;
    gb->halted = false;
    memset(gb->hram, 0, sizeof(gb->hram));
}

uint32_t rgb_encode_callback(GB_gameboy_t *, uint8_t r, uint8_t g, uint8_t b)
{
    return 0xFF000000u | (static_cast<uint32_t>(r) << 16) | (static_cast<uint32_t>(g) << 8) | b;
}

void vblank_callback(GB_gameboy_t *gb, GB_vblank_type_t)
{
    auto *state = static_cast<EmulatorState *>(GB_get_user_data(gb));
    if (!state) return;
    state->frameToken.fetch_add(1, std::memory_order_relaxed);
}

void sample_callback(GB_gameboy_t *gb, GB_sample_t *sample)
{
    auto *state = static_cast<EmulatorState *>(GB_get_user_data(gb));
    if (!state) return;

    if (state->pcmCount + 2 > state->pcm.size()) {
        pcm_drop_sample(state);
        pcm_drop_sample(state);
    }
    pcm_push_sample(state, sample->left);
    pcm_push_sample(state, sample->right);
}

bool memory_write_callback(GB_gameboy_t *gb, uint16_t addr, uint8_t)
{
    auto *state = static_cast<EmulatorState *>(GB_get_user_data(gb));
    if (state && addr >= 0xA000 && addr <= 0xBFFF) {
        state->saveDirty = true;
    }
    return true;
}

std::string jstring_to_string(JNIEnv *env, jstring value)
{
    const char *chars = env->GetStringUTFChars(value, nullptr);
    std::string out(chars ? chars : "");
    env->ReleaseStringUTFChars(value, chars);
    return out;
}

void flush_save_locked(EmulatorState *state, bool force)
{
    if (!force && !state->saveDirty) return;

    int size = GB_save_battery_size(&state->gb);
    if (size <= 0) {
        state->saveDirty = false;
        return;
    }

    std::vector<uint8_t> save(static_cast<size_t>(size));
    if (GB_save_battery_to_buffer(&state->gb, save.data(), save.size()) == 0) {
        std::ofstream out(state->savePath, std::ios::binary | std::ios::trunc);
        out.write(reinterpret_cast<const char *>(save.data()), static_cast<std::streamsize>(save.size()));
        if (out.good()) {
            state->saveDirty = false;
            state->lastSaveFlush = std::chrono::steady_clock::now();
        }
    }
}

void flush_save_if_due_locked(EmulatorState *state)
{
    if (!state->saveDirty) return;

    const auto now = std::chrono::steady_clock::now();
    if (state->lastSaveFlush.time_since_epoch().count() == 0 ||
        now - state->lastSaveFlush >= SAVE_FLUSH_INTERVAL) {
        flush_save_locked(state, false);
    }
}

void tap_button_locked(EmulatorState *state, GB_key_t key)
{
    GB_set_key_state(&state->gb, key, true);
    GB_run_frame(&state->gb);
    flush_save_if_due_locked(state);
    GB_set_key_state(&state->gb, key, false);
    GB_run_frame(&state->gb);
    flush_save_if_due_locked(state);
}

void produce_audio_locked(EmulatorState *state, size_t requiredFrames)
{
    const size_t requiredSamples = requiredFrames * 2;
    const size_t targetSamples = (requiredFrames + QUEUE_TARGET_FRAMES) * 2;

    while (pcm_available_samples(state) < requiredSamples) {
        GB_run_frame(&state->gb);
        flush_save_if_due_locked(state);
    }

    while (pcm_available_samples(state) < targetSamples && pcm_available_samples(state) < QUEUE_MAX_FRAMES * 2) {
        GB_run_frame(&state->gb);
        flush_save_if_due_locked(state);
    }
}
}

extern "C" JNIEXPORT jlong JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeCreate(
    JNIEnv *env,
    jobject,
    jstring rom_path,
    jstring save_path)
{
    auto *state = new EmulatorState();
    state->savePath = jstring_to_string(env, save_path);
    state->pcm.resize(QUEUE_MAX_FRAMES * 2);
    state->frame.resize(SCREEN_PIXELS);
    const auto romPath = jstring_to_string(env, rom_path);

    GB_init(&state->gb, GB_MODEL_CGB_E);
    GB_set_boot_rom_load_callback(&state->gb, load_android_boot_rom);
    GB_load_rom(&state->gb, romPath.c_str());
    GB_set_user_data(&state->gb, state);
    GB_apu_set_sample_callback(&state->gb, sample_callback);
    GB_set_sample_rate(&state->gb, SAMPLE_RATE);
    GB_set_highpass_filter_mode(&state->gb, GB_HIGHPASS_REMOVE_DC_OFFSET);
    GB_set_rgb_encode_callback(&state->gb, rgb_encode_callback);
    GB_set_pixels_output(&state->gb, state->frame.data());
    GB_set_vblank_callback(&state->gb, vblank_callback);
    GB_set_write_memory_callback(&state->gb, memory_write_callback);

    std::ifstream saveIn(state->savePath, std::ios::binary);
    if (saveIn.good()) {
        std::vector<uint8_t> save((std::istreambuf_iterator<char>(saveIn)), std::istreambuf_iterator<char>());
        if (!save.empty()) {
            GB_load_battery_from_buffer(&state->gb, save.data(), save.size());
        }
    }

    // Re-run reset after the callback is registered, then force a stable CGB
    // post-boot state directly instead of relying on a minimal stub sequence.
    GB_reset(&state->gb);
    force_cgb_post_boot_state(&state->gb);
    state->saveDirty = false;
    state->lastSaveFlush = std::chrono::steady_clock::now();

    return reinterpret_cast<jlong>(state);
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeDestroy(
    JNIEnv *,
    jobject,
    jlong handle)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    if (!state) return;
    {
        std::scoped_lock lock(state->mutex);
        flush_save_locked(state, true);
        GB_free(&state->gb);
    }
    delete state;
}

extern "C" JNIEXPORT jint JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeFillAudio(
    JNIEnv *env,
    jobject,
    jlong handle,
    jshortArray pcm,
    jint frames)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    if (!state || frames <= 0) return 0;

    std::scoped_lock lock(state->mutex);
    const size_t requiredSamples = static_cast<size_t>(frames) * 2;
    produce_audio_locked(state, static_cast<size_t>(frames));

    jshort *out = env->GetShortArrayElements(pcm, nullptr);
    if (!out) return 0;
    for (size_t i = 0; i < requiredSamples; i++) {
        out[i] = pcm_pop_sample(state);
    }
    env->ReleaseShortArrayElements(pcm, out, 0);
    return frames;
}

extern "C" JNIEXPORT jintArray JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeGetStatus(
    JNIEnv *env,
    jobject,
    jlong handle)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    jint values[6] = {0, 0, 0, 0, 0, 0};
    if (state) {
        std::scoped_lock lock(state->mutex);
        size_t size = 0;
        auto *hram = static_cast<uint8_t *>(GB_get_direct_access(&state->gb, GB_DIRECT_ACCESS_HRAM, &size, nullptr));
        if (hram && size > STATUS_REPEAT_OFFSET && hram[STATUS_MAGIC_OFFSET] == 0x47) {
            values[0] = hram[STATUS_SONG_OFFSET];
            values[1] = (hram[STATUS_FLAGS_OFFSET] & 0x01) ? 1 : 0;
            values[2] = (hram[STATUS_FLAGS_OFFSET] & 0x02) ? 1 : 0;
            values[3] = hram[STATUS_SECONDS_LO_OFFSET] | (hram[STATUS_SECONDS_HI_OFFSET] << 8);
            values[4] = hram[STATUS_DURATION_LO_OFFSET] | (hram[STATUS_DURATION_HI_OFFSET] << 8);
            values[5] = hram[STATUS_REPEAT_OFFSET];
        }
    }
    jintArray result = env->NewIntArray(6);
    env->SetIntArrayRegion(result, 0, 6, values);
    return result;
}

extern "C" JNIEXPORT jint JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeGetFrameToken(
    JNIEnv *,
    jobject,
    jlong handle)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    if (!state) return 0;
    return state->frameToken.load(std::memory_order_relaxed);
}

extern "C" JNIEXPORT jintArray JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeGetDebugState(
    JNIEnv *env,
    jobject,
    jlong handle)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    jint values[11] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
    if (state) {
        std::scoped_lock lock(state->mutex);
        size_t size = 0;
        auto *hram = static_cast<uint8_t *>(GB_get_direct_access(&state->gb, GB_DIRECT_ACCESS_HRAM, &size, nullptr));
        if (hram && size > STATUS_SECONDS_HI_OFFSET) {
            values[0] = hram[STATUS_MAGIC_OFFSET];
            values[1] = hram[STATUS_SONG_OFFSET];
            values[2] = hram[STATUS_FLAGS_OFFSET];
            values[3] = hram[STATUS_SECONDS_LO_OFFSET] | (hram[STATUS_SECONDS_HI_OFFSET] << 8);
        }
        values[4] = state->frameToken.load(std::memory_order_relaxed);
        values[5] = state->frame.empty() ? 0 : static_cast<jint>(state->frame[0]);
        values[6] = state->gb.pc;
        values[7] = state->gb.sp;
        values[8] = state->gb.af;
        values[9] = state->gb.boot_rom_finished ? 1 : 0;
        values[10] = state->gb.io_registers[GB_IO_LCDC];
    }
    jintArray result = env->NewIntArray(11);
    env->SetIntArrayRegion(result, 0, 11, values);
    return result;
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeCopyFrame(
    JNIEnv *env,
    jobject,
    jlong handle,
    jintArray pixels)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    if (!state) return;
    std::scoped_lock lock(state->mutex);
    env->SetIntArrayRegion(
        pixels,
        0,
        static_cast<jsize>(state->frame.size()),
        reinterpret_cast<const jint *>(state->frame.data())
    );
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeTapButton(
    JNIEnv *,
    jobject,
    jlong handle,
    jint key)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    if (!state) return;
    std::scoped_lock lock(state->mutex);
    tap_button_locked(state, static_cast<GB_key_t>(key));
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeSetButton(
    JNIEnv *,
    jobject,
    jlong handle,
    jint key,
    jboolean pressed)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    if (!state) return;
    std::scoped_lock lock(state->mutex);
    GB_set_key_state(&state->gb, static_cast<GB_key_t>(key), pressed);
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeSendCommand(
    JNIEnv *,
    jobject,
    jlong handle,
    jint command,
    jint argument)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    if (!state) return;
    std::scoped_lock lock(state->mutex);
    size_t size = 0;
    auto *hram = static_cast<uint8_t *>(GB_get_direct_access(&state->gb, GB_DIRECT_ACCESS_HRAM, &size, nullptr));
    if (!hram || size <= COMMAND_ARG_OFFSET) return;
    hram[COMMAND_ARG_OFFSET] = static_cast<uint8_t>(argument);
    hram[COMMAND_OFFSET] = static_cast<uint8_t>(command);
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeSetRenderingEnabled(
    JNIEnv *,
    jobject,
    jlong handle,
    jboolean enabled)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    if (!state) return;
    std::scoped_lock lock(state->mutex);
    GB_set_rendering_disabled(&state->gb, !enabled);
    GB_set_pixels_output(&state->gb, enabled ? state->frame.data() : nullptr);
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_kleusbalut_gbsplayer_android_NativeBridge_nativeFlushSave(
    JNIEnv *,
    jobject,
    jlong handle)
{
    auto *state = reinterpret_cast<EmulatorState *>(handle);
    if (!state) return;
    std::scoped_lock lock(state->mutex);
    flush_save_locked(state, true);
}
