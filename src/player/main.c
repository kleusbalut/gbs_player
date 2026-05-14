// ================================================================
// GBS Player for Game Boy Color  (GBDK-2020 / SDCC)
// ================================================================
#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/font.h>
#include <string.h>
#include "gbs_info.h"
#include "jp_font.h"

// ── Constants ─────────────────────────────────────────────────────
#define SRAM_MAGIC  0x4748u
#define NAME_MAGIC  0x4E4Du
#define MAX_PL      20
#define MAX_NAME    32
#define SCR_W       20
#define SCR_H       18
#define USE_TIMER   (GBS_TIMER_CTL & 4)

// UI tile indices (loaded at UI_TILES_START)
#define UI_TILES_START  96
#define UI_TILES_COUNT  21
#define T_ICON_PLAY    96
#define T_ICON_PAUSE   97
#define T_ICON_GRAB    98
#define T_CORNER_TL    99
#define T_CORNER_BL   100
#define T_CORNER_TR   101
#define T_CORNER_BR   102
#define T_BAR_H_TOP   103
#define T_BAR_H_BOT   104
#define T_BAR_V_LEFT  105
#define T_BAR_V_RIGHT 106
#define T_TJUNC_LEFT  107
#define T_TJUNC_RIGHT 108
#define T_TJUNC_TOP   109
#define T_TJUNC_BOT   110
#define T_BAR_V_CENTER 111
#define T_BRACKET_L   112
#define T_BRACKET_R   113
#define T_BRACKET_BL  114
#define T_BRACKET_BR  115
#define T_BAR_H_CTR   116

// Japanese font tile base indices
#define JP_TILES_START      117
#define JP_TILES_COUNT      113
#define JP_HIRA_START       117   // あ-ん (46)
#define JP_SMALL_HIRA_START 163   // ぁぃぅぇぉゃゅょっ (9)
#define JP_KATA_START       172   // ア-ン (46)
#define JP_SMALL_KATA_START 218   // ァィゥェォャュョッ (9)
#define JP_LONG_VOWEL       227   // ー
#define JP_HANDAKUTEN       229   // ゜
#define JP_DAKUTEN          228   // ゛

// Tile 0 = space (font_ibm: ' ' - 0x20)
#define T_SPACE        0
// Repeat mode icon tiles (loaded at VRAM 3-5)
#define T_RPT_NONE     3
#define T_RPT_ALL      4
#define T_RPT_ONE      5

// MBC1 バンク切替
#define ROM_BANK(bank)  do { \
    *((volatile UINT8 *)0x6000) = 0; \
    *((volatile UINT8 *)0x4000) = 0; \
    *((volatile UINT8 *)0x2000) = (bank); \
} while(0)
#define BANK1()  ROM_BANK(1u)

// Gold 系 helper が参照する home bank shadow / VBlank state
#define GBS_HRAM_ROM_BANK (*((volatile UINT8 *)0xFF9F))
#if GBS_COMPAT_RB
#define GBS_RED_AUDIO_BANK (*((volatile UINT8 *)0xC0EF))
#define GBS_RED_AUDIO_SAVED_BANK (*((volatile UINT8 *)0xC0F0))
#define RED_TRACK1_END_TIMEOUT 120u
#define RED_TRACK1_FIXED_TIMEOUT 720u
#endif
#if GBS_HAS_CEEA_FLAG
#define GBS_WRAM_VBL_OCCURRED (*((volatile UINT8 *)0xCEEA))
#define GBS_WRAM_BANK_BACKUP  (*((volatile UINT8 *)0xD155))
#endif
#define GBS_HELPER_SP_SAVE_ADDR 0xFF94
#define GBS_HELPER_IE_SAVE_ADDR 0xFF96
#if GBS_COMPAT_RB
#define GBS_INIT_STACK_PTR 0xC2C0
#define GBS_PLAY_STACK_PTR 0xC2C0
#else
#define GBS_INIT_STACK_PTR GBS_STACK_SAFE
#define GBS_PLAY_STACK_PTR GBS_STACK_SAFE
#endif

#if GBS_COMPAT_RB
/* Bank 0 helper work area reserved for Red-specific audio glue.
 * Keep this outside the GBS engine's WRAM scratch range (C101-C2BF). */
#define RED_HELPER_LAST_MUSIC_ADDR   0xD1F0
#define RED_HELPER_MUSIC_HEADER_ADDR 0xD1F1
#define RED_HELPER_FADE_RELOAD_ADDR  0xD1F2
#define RED_HELPER_FADE_COUNTER_ADDR 0xD1F3
#define RED_SILENCE_TRACE_MASK_ADDR  (*((volatile UINT8 *)0xD1F4))
#define RED_SILENCE_TRACE_PCM12_ADDR (*((volatile UINT8 *)0xD1F5))
#define RED_SILENCE_TRACE_PCM34_ADDR (*((volatile UINT8 *)0xD1F6))
#define RED_SILENCE_TRACE_CNT_ADDR   (*((volatile UINT8 *)0xD1F7))
#endif
/* Android bridge state must not overlap the player's HRAM globals.
 * Keep it near the top of HRAM, below the trampoline SP save slot. */
#define ANDROID_STATUS_MAGIC_ADDR   (*((volatile UINT8 *)0xFFE8))
#define ANDROID_STATUS_SONG_ADDR    (*((volatile UINT8 *)0xFFE9))
#define ANDROID_STATUS_FLAGS_ADDR   (*((volatile UINT8 *)0xFFEA))
#define ANDROID_STATUS_SOURCE_ADDR  (*((volatile UINT8 *)0xFFEB))
#define ANDROID_STATUS_SEC_LO_ADDR  (*((volatile UINT8 *)0xFFEC))
#define ANDROID_STATUS_SEC_HI_ADDR  (*((volatile UINT8 *)0xFFED))
#define ANDROID_CMD_ADDR            (*((volatile UINT8 *)0xFFEE))
#define ANDROID_CMD_ARG_ADDR        (*((volatile UINT8 *)0xFFEF))
#define ANDROID_STATUS_DUR_LO_ADDR  (*((volatile UINT8 *)0xFFF0))
#define ANDROID_STATUS_DUR_HI_ADDR  (*((volatile UINT8 *)0xFFF1))
#define ANDROID_STATUS_REPEAT_ADDR  (*((volatile UINT8 *)0xFFF2))
#define ANDROID_STATUS_VIEW_ADDR    (*((volatile UINT8 *)0xFFF3))

#ifndef GBS_VOL_SHADOW_ADDR
#define GBS_VOL_SHADOW_ADDR 0x0000
#endif

#ifndef GBS_PAN_SHADOW_ADDR
#define GBS_PAN_SHADOW_ADDR 0x0000
#endif

// ── Types ─────────────────────────────────────────────────────────
typedef struct {
    UINT16 magic;
    UINT8  count;
    UINT8  tracks[MAX_PL];
    UINT8  repeat;
    UINT8  fade_time;  // フェード時間インデックス (0=OFF, 1=2s, 2=3s(default), 3=4s)
    UINT8  mono;       // 0=ステレオ(default), 1=モノラル
    UINT8  silence;    // 無音検出インデックス (0=5s(default), 1=OFF, 2=2s, 3=3s)
    UINT8  track_time[GBS_NUM_SONGS]; // 曲ごとの再生時間インデックス (0-6)
    // --- v6: song name data ---
    UINT16 name_magic;                    // NAME_MAGIC if song names present
    UINT8  song_names[GBS_NUM_SONGS][MAX_NAME]; // custom encoding
    UINT8  custom_title[32];              // custom encoding (0=use ROM default)
    UINT8  custom_author[32];             // custom encoding (0=use ROM default)
} SaveData;
// track_time インデックス: 0=90s(default), 1=OFF, 2=30s, 3=1m, 4=2m, 5=3m, 6=5m
// fade_time インデックス: 0=OFF, 1=2s, 2=3s(default), 3=4s

// ── Globals ───────────────────────────────────────────────────────
static SaveData sav;
static UINT8 cur_song, playing, paused;
static UINT8 gbs_init_song;
static UINT8 sel, pl_sel, view, redraw, pj;
static UINT8 pl_idx;    // プレイリスト再生位置 (0xFF = PL再生していない)
static UINT8 play_src;  // 再生元 (0=Songs, 1=Playlist)

static UINT8 grab;      // SELECT でつかんだ PL 位置 (PL_NONE=つかんでいない)
static UINT8 opt_sel;   // オプション画面のカーソル位置
static UINT8 prev_view; // オプション画面を開く前のview (B押下で戻る用)
static UINT8 opt_items[8]; // オプション項目IDリスト
static UINT8 opt_count; // オプション項目数
static UINT8 opt_song;  // オプション画面で操作対象の曲番号

static UINT8 player_sel;
static UINT8 player_prev_view;
static UINT8 player_press_action;
static UINT8 player_press_timer;
static UINT16 player_cursor_timer;

static UINT8 fb[SCR_H][SCR_W];
static palette_color_t pal[4];
static UINT8 fb_row;    // VRAM転送の進捗行 (0=転送不要, 1-18=転送中)
static UINT8 rpt_cnt;   // キーリピートカウンタ
static UINT16 vbl_cnt;  // 再生中のVBlankカウンタ (自動曲送り用)
static UINT8 fade_vol;  // フェードアウト音量 (7=最大, 0=無音, PL_NONE=フェード中でない)
static UINT8 fade_cnt;  // フェードアウト: 段階切替用フレームカウンタ
static UINT8 fade_wait; // フェード完了後の待機カウンタ (0=待機なし)
static UINT8 scroll_pos;  // スクロールオフセット
static UINT8 scroll_cnt;  // スクロールフレームカウンタ
static UINT8 header_scroll_pos;  // タイトル/作曲者スクロールオフセット
static UINT16 header_scroll_wait; // タイトル/作曲者スクロール開始待機カウンタ
static UINT8 header_scroll_wrap; // タイトル/作曲者の一周の長さ
static UINT8 name_scroll_pos;  // 曲名スクロールオフセット
static UINT16 name_scroll_wait; // 曲名スクロール開始待機カウンタ
static UINT8 name_scroll_wrap; // 一周の長さ (len+3, 0=未計算)
static UINT8 prev_sel;   // 前回のカーソル位置 (スクロールリセット用)
static UINT8 prev_pl_sel; // 前回のPLカーソル位置
static UINT8 mono_flag;   // トランポリンASM用モノラルフラグ (sav.monoのミラー)
static UINT16 silence_cnt; // 無音フレームカウンタ
static UINT16 silence_stuck_cnt; // CGB/Red no-progress counter
static UINT8 silence_pcm12_prev;
static UINT8 silence_pcm34_prev;
static UINT8 silence_pcm12_cur;
static UINT8 silence_pcm34_cur;
static UINT8 silence_sig_prev[10];
static UINT8 silence_sig_cur[10];
static UINT8 sel_hold_cnt; // SELECT長押しカウンタ
static UINT8 sel_triggered; // SELECT長押し発動フラグ

#define PL_NONE    0xFF
#define RPT_DELAY  12   // 長押し開始までのフレーム数 (~200ms)
#define RPT_SPEED   4   // リピート間隔フレーム数 (~67ms)
#define FADE_GAP    60   // フェード完了後の待機フレーム数 (≈ 1秒)
#define SCROLL_SPEED 6   // スクロール速度 (6フレームごとに1文字)
#define HEADER_SCROLL_DELAY 240 // タイトル/作曲者スクロール開始までの待機
#define NAME_SCROLL_DELAY 240 // 曲名スクロール開始までの待機 (4秒 = 60fps * 4)
// SILENCE_LIMIT は silence_tbl[] に移行
#define SEL_LONG_PRESS 15 // SELECT長押し判定フレーム数 (~250ms)

// オプション画面の項目ID
#define OPT_ADD   0  // PL追加
#define OPT_DEL   1  // PL削除
#define OPT_MOVE  2  // PL移動 (つかみモード開始)
#define OPT_TIME  3  // 再生時間
#define OPT_RPT   4  // リピート
#define OPT_FADE  5  // フェード時間
#define OPT_MONO  6  // モノラル/ステレオ
#define OPT_SIL   7  // 無音検出
#define OPT_VISIBLE_ROWS 7u

#define ANDROID_CMD_NONE   0u
#define ANDROID_CMD_TOGGLE 1u
#define ANDROID_CMD_STOP   2u
#define ANDROID_CMD_NEXT   3u
#define ANDROID_CMD_PREV   4u
#define ANDROID_CMD_REPEAT 6u
#define ANDROID_CMD_PLAYER_DOWN 7u
#define ANDROID_CMD_PLAYER_UP   8u

#define VIEW_SONGS 0u
#define VIEW_PL    1u
#define VIEW_OPT   2u
#define VIEW_PLAYER 3u

#define PLAYER_ACT_PREV   0u
#define PLAYER_ACT_TOGGLE 1u
#define PLAYER_ACT_NEXT   2u
#define PLAYER_ACT_BACK   3u
#define PLAYER_ACT_STOP   4u
#define PLAYER_ACT_RPT    5u
#define PLAYER_ACT_NONE   0xFFu
#define PLAYER_CURSOR_TIMEOUT 1800u

#ifndef GBS_TITLE_ENC_DEFINED
static const UINT8 GBS_TITLE_ENC[32] = {0};
static const UINT8 GBS_AUTHOR_ENC[32] = {0};
#endif

// 自動曲送り時間テーブル (VBlank数, ~60fps)
// index: 0=90s(default), 1=OFF, 2=30s, 3=1m, 4=2m, 5=3m, 6=5m
static const UINT16 track_time_tbl[7] = {5400, 0, 1800, 3600, 7200, 10800, 18000};
static const char  *track_time_str[7] = {"90s", "OFF", "30s", "1m", "2m", "3m", "5m"};

// フェード時間テーブル (1段階あたりのフレーム数, 7段階)
// index: 0=OFF, 1=2s, 2=3s(default), 3=4s
static const UINT8  fade_frames_tbl[4] = {0, 17, 26, 34};
static const UINT8  fade_secs_tbl[4] = {0, 2, 3, 4};
static const char  *fade_time_str[4] = {"OFF", "2s", "3s", "4s"};

// 無音検出時間テーブル (VBlank数, ~60fps)
// index: 0=5s(default), 1=OFF, 2=2s, 3=3s
static const UINT16 silence_tbl[4] = {300, 0, 120, 180};
static const char  *silence_str[4] = {"5s", "OFF", "2s", "3s"};

static UINT8 runtime_is_playing(void);
static UINT8 runtime_is_paused(void);
static void runtime_set_play_state(UINT8 is_playing, UINT8 is_paused);
static UINT8 get_default_track_time(UINT8 song);

static const UINT8 *display_title(void) {
    return (sav.name_magic == NAME_MAGIC && sav.custom_title[0]) ? (const UINT8 *)sav.custom_title : GBS_TITLE_ENC;
}

static const UINT8 *display_author(void) {
    return (sav.name_magic == NAME_MAGIC && sav.custom_author[0]) ? (const UINT8 *)sav.custom_author : GBS_AUTHOR_ENC;
}

static void reset_fade_state(void) {
    fade_vol = PL_NONE;
    fade_wait = 0;
}

static void reset_silence_state(void) {
    silence_stuck_cnt = 0;
    silence_pcm12_prev = 0u;
    silence_pcm34_prev = 0u;
    silence_pcm12_cur = 0u;
    silence_pcm34_cur = 0u;
    memset(silence_sig_prev, 0, sizeof(silence_sig_prev));
    memset(silence_sig_cur, 0, sizeof(silence_sig_cur));
}

static void sync_android_status(void) {
    UINT8 flags = 0u;
    UINT16 secs = (UINT16)(vbl_cnt / 60u);
    UINT16 duration_secs = 0u;
    UINT8 tt_idx = sav.track_time[cur_song];

    ANDROID_STATUS_MAGIC_ADDR = 0x47u; /* 'G' */
    ANDROID_STATUS_SONG_ADDR = cur_song;
    if (runtime_is_playing()) flags |= 0x01u;
    if (runtime_is_paused()) flags |= 0x02u;
    ANDROID_STATUS_FLAGS_ADDR = flags;
    ANDROID_STATUS_SOURCE_ADDR = play_src;
    ANDROID_STATUS_SEC_LO_ADDR = (UINT8)(secs & 0xFFu);
    ANDROID_STATUS_SEC_HI_ADDR = (UINT8)(secs >> 8);
    if (sav.repeat != 1u && tt_idx != 1u) {
        duration_secs = (UINT16)(track_time_tbl[tt_idx] / 60u + fade_secs_tbl[sav.fade_time] + 1u);
    }
    ANDROID_STATUS_DUR_LO_ADDR = (UINT8)(duration_secs & 0xFFu);
    ANDROID_STATUS_DUR_HI_ADDR = (UINT8)(duration_secs >> 8);
    ANDROID_STATUS_REPEAT_ADDR = sav.repeat;
    ANDROID_STATUS_VIEW_ADDR = view;
}

#if GBS_COMPAT_RB
static UINT8 normalize_red_play_bank(UINT8 bank) {
#if GBS_SOURCE_IS_ROM
    if (bank == 0u) return 1u;
    return bank;
#else
    if (bank == 0u || bank == 1u) return 1u;
    if (bank == 0x08u) return 2u;
    if (bank == 0x1Fu) return 3u;
    if (bank > 3u) return 3u;
    return bank;
#endif
}

static UINT8 current_red_play_bank(void) {
    UINT8 bank = GBS_RED_AUDIO_BANK;
    if (bank == 0u) bank = GBS_RED_AUDIO_SAVED_BANK;
    return normalize_red_play_bank(bank);
}

static void clear_wram_range(UINT16 start, UINT16 end) {
    volatile UINT8 *p = (volatile UINT8 *)start;
    while (start < end) {
        *p++ = 0u;
        start++;
    }
}

static void reset_red_audio_wram(void) {
    /* Preserve GBDK internals around C0A0-C0AF and the player's globals at C2C8+.
     * Clear the Red audio engine's per-song work so INIT starts from a clean slate. */
    clear_wram_range(0xC000u, 0xC0A0u);
    clear_wram_range(0xC0B0u, 0xC2C0u);
}
#endif

static void select_play_bank(void) {
#if GBS_COMPAT_RB
    UINT8 bank = current_red_play_bank();
    GBS_HRAM_ROM_BANK = bank;
    ROM_BANK(bank);
#else
    BANK1();
#endif
}

static UINT8 runtime_is_playing(void) {
    return playing;
}

static UINT8 runtime_is_paused(void) {
    return paused;
}

static void runtime_set_play_state(UINT8 is_playing, UINT8 is_paused) {
    playing = is_playing;
    paused = is_paused;
}

static UINT8 fade_scale_level(UINT8 level, UINT8 vol) {
    return (UINT8)((level * vol + 6u) / 7u);
}

static UINT8 fade_nr50(UINT8 vol) {
    UINT8 base;
    UINT8 left;
    UINT8 right;
    UINT8 vin;

    if (GBS_VOL_SHADOW_ADDR != 0u) {
        base = *((volatile UINT8 *)GBS_VOL_SHADOW_ADDR);
    } else {
        base = 0x77u;
    }

    vin = (UINT8)(base & 0x88u);
    left = fade_scale_level((UINT8)((base >> 4) & 0x07u), vol);
    right = fade_scale_level((UINT8)(base & 0x07u), vol);
    return (UINT8)(vin | (left << 4) | right);
}

static void audio_hw_silence(void) {
    /* Mute routing first, then clear DAC/trigger-related regs before power cycling.
     * This reduces speaker clicks when switching tracks. */
    NR50_REG = 0x00u;
    NR51_REG = 0x00u;
    NR12_REG = 0x00u;
    NR22_REG = 0x00u;
    NR30_REG = 0x00u;
    NR42_REG = 0x00u;
    NR14_REG = 0x00u;
    NR24_REG = 0x00u;
    NR34_REG = 0x00u;
    NR44_REG = 0x00u;
    NR52_REG = 0x00u;
}

static UINT8 pcm_nibble_energy(UINT8 sample) {
    sample &= 0x0Fu;
    if (sample == 0x00u) return 0u;
    if (sample >= 0x08u) return (UINT8)(sample - 0x08u);
    return (UINT8)(0x08u - sample);
}

static UINT8 audio_activity_mask(void) {
    UINT8 s;
    if (_cpu == CGB_TYPE) {
        UINT8 pcm12 = *((volatile UINT8 *)0xFF76u);
        UINT8 pcm34 = *((volatile UINT8 *)0xFF77u);
        UINT8 energy = 0u;
        s = 0u;
        silence_pcm12_cur = pcm12;
        silence_pcm34_cur = pcm34;
        if ((NR52_REG & 0x01u) && (NR12_REG & 0xF8u)) energy = (UINT8)(energy + pcm_nibble_energy(pcm12));
        if ((NR52_REG & 0x02u) && (NR22_REG & 0xF8u)) energy = (UINT8)(energy + pcm_nibble_energy((UINT8)(pcm12 >> 4)));
        if ((NR52_REG & 0x04u) && (NR30_REG & 0x80u)) energy = (UINT8)(energy + pcm_nibble_energy(pcm34));
        if ((NR52_REG & 0x08u) && (NR42_REG & 0xF8u)) energy = (UINT8)(energy + pcm_nibble_energy((UINT8)(pcm34 >> 4)));
        if (energy > 2u) s = 0x0Fu;
#if GBS_COMPAT_RB
        RED_SILENCE_TRACE_PCM12_ADDR = pcm12;
        RED_SILENCE_TRACE_PCM34_ADDR = pcm34;
#endif
        return s;
    }

    s = NR52_REG & 0x0Fu;
    if (s & 0x01u) { if (!(NR12_REG & 0xF8u)) s &= (UINT8)~0x01u; }
    if (s & 0x02u) { if (!(NR22_REG & 0xF8u)) s &= (UINT8)~0x02u; }
    if (s & 0x04u) { if (!(NR30_REG & 0x80u)) s &= (UINT8)~0x04u; }
    if (s & 0x08u) { if (!(NR42_REG & 0xF8u)) s &= (UINT8)~0x08u; }
    return s;
}

static void capture_silence_signature(void) {
    silence_sig_cur[0] = silence_pcm12_cur;
    silence_sig_cur[1] = silence_pcm34_cur;
    silence_sig_cur[2] = *((volatile UINT8 *)0xC026u);
    silence_sig_cur[3] = *((volatile UINT8 *)0xC027u);
    silence_sig_cur[4] = *((volatile UINT8 *)0xC028u);
    silence_sig_cur[5] = *((volatile UINT8 *)0xC029u);
    silence_sig_cur[6] = *((volatile UINT8 *)0xC02Au);
    silence_sig_cur[7] = *((volatile UINT8 *)0xC02Bu);
    silence_sig_cur[8] = *((volatile UINT8 *)0xC02Cu);
    silence_sig_cur[9] = *((volatile UINT8 *)0xC02Du);
}

static UINT8 silence_signature_same(void) {
    UINT8 i;
    for (i = 0u; i != 10u; i++) {
        if (silence_sig_cur[i] != silence_sig_prev[i]) return 0u;
    }
    return 1u;
}

static void silence_signature_commit(void) {
    UINT8 i;
    for (i = 0u; i != 10u; i++) silence_sig_prev[i] = silence_sig_cur[i];
}

#if GBS_COMPAT_RB
static UINT8 red_track1_stuck_silence_candidate(void) {
    UINT8 i;
    static const UINT16 probe_addrs[] = {
        0xC026u, 0xC02Au, 0xC076u, 0xC07Eu, 0xC086u, 0xC08Eu,
        0xC096u, 0xC09Eu, 0xC0A6u, 0xC0AEu
    };

    if (cur_song != 0u) return 0u;
    if (_cpu != CGB_TYPE) return 0u;
    if (current_red_play_bank() != 3u) return 0u;
    if (vbl_cnt < 120u) return 0u;
    if (*((volatile UINT8 *)0xC0EEu) != 0x33u) return 0u;
    if (*((volatile UINT8 *)0xC0F0u) != 0x03u) return 0u;
    if (*((volatile UINT8 *)0xC0E8u) != 0x00u) return 0u;
    if (*((volatile UINT8 *)0xC0E9u) != 0x00u) return 0u;
    if (silence_pcm34_cur != 0x00u) return 0u;
    if ((silence_pcm12_cur & 0xF0u) != 0x00u) return 0u;

    for (i = 2u; i != 10u; i++) {
        if (silence_sig_cur[i] != 0u) return 0u;
    }
    for (i = 0u; i != (UINT8)(sizeof(probe_addrs) / sizeof(probe_addrs[0])); i++) {
        if (*((volatile UINT8 *)probe_addrs[i]) != 0x00u) return 0u;
    }
    return 1u;
}
#endif

static UINT8 fade_shadow_push(void) {
    UINT8 base;

    if (fade_vol == PL_NONE || GBS_VOL_SHADOW_ADDR == 0u) {
        return 0u;
    }

    base = *((volatile UINT8 *)GBS_VOL_SHADOW_ADDR);
    *((volatile UINT8 *)GBS_VOL_SHADOW_ADDR) = fade_nr50(fade_vol);
    return base;
}

static void fade_shadow_pop(UINT8 base) {
    if (fade_vol == PL_NONE || GBS_VOL_SHADOW_ADDR == 0u) {
        return;
    }
    *((volatile UINT8 *)GBS_VOL_SHADOW_ADDR) = base;
}

static void fade_tick_isr(void) {
    if (fade_wait) return;
    if (fade_vol == PL_NONE) return;
    fade_cnt++;
    if (fade_cnt < fade_frames_tbl[sav.fade_time]) return;
    fade_cnt = 0;
    if (fade_vol > 1u) {
        fade_vol--;
    } else {
        runtime_set_play_state(0u, 0u);
        fade_vol = PL_NONE;
        fade_cnt = 0u;
        audio_hw_silence();
        fade_wait = FADE_GAP;
    }
}

static void restore_ui_regs(void) {
    LCDC_REG = 0xC1;
    STAT_REG = 0x80;
    SCY_REG  = 0x00;
    SCX_REG  = 0x00;
    LYC_REG  = 0x00;
    BGP_REG  = 0xFC;
    OBP0_REG = 0x00;
    OBP1_REG = 0x00;
    WY_REG   = 0x00;
    WX_REG   = 0x07;
}

// Custom UI tiles (2bpp GB format, 16 bytes each)
// Generated from assets/ui/gbs_player.gbr
static const UINT8 ui_tiles[] = {
    0x20,0x20,0x30,0x30,0x38,0x38,0x3C,0x3C,0x3C,0x3C,0x38,0x38,0x30,0x30,0x20,0x20, // ICON_PLAY
    0x00,0x00,0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x00,0x00, // ICON_PAUSE
    0x04,0x04,0x06,0x06,0x1F,0x3F,0x26,0x26,0x24,0x24,0x20,0x20,0x20,0x20,0xFF,0xFF, // ICON_GRAB
    0x00,0x00,0x3F,0x00,0x60,0x1F,0x4F,0x3F,0x50,0x30,0x50,0x30,0x50,0x30,0x50,0x30, // CORNER_TL
    0x50,0x30,0x50,0x30,0x50,0x30,0x50,0x30,0x4F,0x3F,0x60,0x1F,0x3F,0x00,0x00,0x00, // CORNER_BL
    0x00,0x00,0xFC,0x00,0x06,0xF8,0xF2,0xFC,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C, // CORNER_TR
    0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0xF2,0xFC,0x06,0xF8,0xFC,0x00,0x00,0x00, // CORNER_BR
    0x00,0x00,0xFF,0x00,0x00,0xFF,0xFF,0xFF,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00, // BAR_H_TOP
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xFF,0xFF,0x00,0xFF,0xFF,0x00,0x00,0x00, // BAR_H_BOT
    0x50,0x30,0x50,0x30,0x50,0x30,0x50,0x30,0x50,0x30,0x50,0x30,0x50,0x30,0x50,0x30, // BAR_V_LEFT
    0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C, // BAR_V_RIGHT
    0x50,0x30,0x50,0x30,0x50,0x30,0x50,0x30,0x5F,0x3F,0x50,0x30,0x50,0x30,0x50,0x30, // TJUNC_LEFT
    0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C,0xFA,0xFC,0x0A,0x0C,0x0A,0x0C,0x0A,0x0C, // TJUNC_RIGHT
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xFF,0xFF,0x10,0x10,0x10,0x10,0x10,0x10, // TJUNC_TOP
    0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0xFF,0xFF,0x00,0xFF,0xFF,0x00,0x00,0x00, // TJUNC_BOT
    0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10,0x10, // BAR_V_CENTER
    0x0E,0x0E,0x0C,0x08,0x0C,0x08,0x0C,0x08,0xFC,0xF8,0x0C,0x08,0x0C,0x08,0x0E,0x0E, // BRACKET_L
    0x70,0x70,0x30,0x10,0x30,0x10,0x30,0x10,0x3F,0x1F,0x30,0x10,0x30,0x10,0x70,0x70, // BRACKET_R
    0x0E,0x0E,0x0C,0x08,0x0C,0x08,0x0C,0x08,0xFC,0xF8,0x0C,0xC8,0xCC,0x08,0x0E,0x0E, // BRACKET_BL
    0x70,0x70,0x30,0x10,0x30,0x10,0x30,0x10,0x3F,0x1F,0x30,0x13,0x33,0x10,0x70,0x70, // BRACKET_BR
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0xFF,0xFF,0x00,0x00,0x00,0x00,0x00,0x00, // BAR_H_CTR
};

// Repeat mode icon tiles (loaded at VRAM 3-5)
static const UINT8 rpt_tiles[] = {
    0x00,0x08,0x0C,0x0C,0x7E,0x7E,0x00,0x00,0x00,0x00,0x7E,0x7E,0x30,0x30,0x00,0x10, // RPT_NONE
    0x08,0x08,0x3C,0x7C,0x48,0x48,0x40,0x42,0x02,0x42,0x12,0x12,0x3C,0x3E,0x10,0x10, // RPT_ALL
    0x00,0x04,0x3E,0x7E,0x40,0x44,0x40,0x40,0x04,0x44,0x04,0x0C,0x04,0x04,0x04,0x0E, // RPT_ONE
};

// ── SRAM ──────────────────────────────────────────────────────────
static void sav_rw(UINT8 wr) {
    volatile UINT8 *s = (volatile UINT8 *)0xA000;
    UINT8 *m = (UINT8 *)&sav;
    UINT16 i;
    *((volatile UINT8 *)0x0000) = 0x0A;
    for (i = 0; i < (UINT16)sizeof(SaveData); i++) {
        if (wr) s[i] = m[i]; else m[i] = s[i];
    }
    *((volatile UINT8 *)0x0000) = 0x00;
}

static void sav_load(void) {
    UINT8 i;
    sav_rw(0);
    if (sav.magic != SRAM_MAGIC) {
        sav.magic     = SRAM_MAGIC;
        sav.count     = 0;
        sav.repeat    = 0;
        sav.fade_time = 2;  // 2 = 3s (default)
        sav.mono      = 0;  // 0 = ステレオ (default)
        sav.silence   = 0;  // 0 = 5s (default)
        for (i = 0; i < (UINT8)GBS_NUM_SONGS; i++)
            sav.track_time[i] = get_default_track_time(i);
        sav.name_magic = 0;
    }
    if (sav.name_magic != NAME_MAGIC) {
        sav.custom_title[0] = 0u;
        sav.custom_author[0] = 0u;
    }
}

// ── Song name access ──────────────────────────────────────────────
// gbs_info.h に曲名配列がない場合のフォールバック
#ifndef GBS_SONG_NAMES_DEFINED
#define GBS_SONG_NAMES_DEFINED 0
#endif
static const UINT8 _empty_name[MAX_NAME] = {0};

#if GBS_SONG_NAMES_DEFINED
#define ROM_HAS_NAMES 1
#ifndef GBS_ROM_NAME_COUNT
#define GBS_ROM_NAME_COUNT 0
#endif
#else
#define ROM_HAS_NAMES 0
#endif

#ifndef GBS_TRACK_TIMES_DEFINED
#define GBS_TRACK_TIMES_DEFINED 0
#endif

#if GBS_TRACK_TIMES_DEFINED
#define ROM_HAS_TRACK_TIMES 1
#ifndef GBS_ROM_TRACK_TIME_COUNT
#define GBS_ROM_TRACK_TIME_COUNT 0
#endif
#else
#define ROM_HAS_TRACK_TIMES 0
#endif

// SAVに曲名があればSAV優先、なければROM埋め込みを使用
static const UINT8 *get_song_name(UINT8 song) {
    if (sav.name_magic == NAME_MAGIC && sav.song_names[song][0] != 0u) {
        return sav.song_names[song];
    }
#if ROM_HAS_NAMES
    UINT8 i;
    for (i = 0; i < (UINT8)GBS_ROM_NAME_COUNT; i++) {
        if (gbs_song_name_ids[i] == song) {
            return &gbs_song_name_data[gbs_song_name_offsets[i]];
        }
    }
    return _empty_name;
#else
    return _empty_name;
#endif
}

static UINT8 get_default_track_time(UINT8 song) {
#if ROM_HAS_TRACK_TIMES
    UINT8 i;
    for (i = 0; i < (UINT8)GBS_ROM_TRACK_TIME_COUNT; i++) {
        if (gbs_track_time_ids[i] == song) {
            return gbs_track_time_values[i];
        }
    }
#endif
    return 0u;
}

// ── Trampolines (ROM固定, インラインASM) ─────────────────────────
#define _STR(x)  #x
#define STR(x)   _STR(x)

void gbs_init_trampoline(void) __naked {
    __asm
        di
        ld  b, a
        ld  a, (#0xFFFF)
        ld  (#GBS_HELPER_IE_SAVE_ADDR), a
        xor a, a
        ld  (#0xFFFF), a
        ld  (#GBS_HELPER_SP_SAVE_ADDR), sp
        ld  sp, #GBS_INIT_STACK_PTR
        ld  a, b
        call #GBS_INIT_ADDR
        di
        ld  hl, #GBS_HELPER_SP_SAVE_ADDR
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  sp, hl
        ld  a, (#GBS_HELPER_IE_SAVE_ADDR)
        ld  (#0xFFFF), a
        ret
    __endasm;
}

#if GBS_COMPAT_GS
void gbs_gold_init_trampoline(void) __naked {
    __asm
        call #GBS_INIT_ADDR
        ret
    __endasm;
}

void gbs_gold_play_trampoline(void) __naked {
    __asm
        ld  a, (#_mono_flag)
        or  a, a
        jr  z, .gold_no_pre_mono
        ld  a, #0xFF
        ldh (#0x25), a
    .gold_no_pre_mono:
        call #GBS_PLAY_ADDR
        ld  a, (#_mono_flag)
        or  a, a
        jr  z, .gold_no_mono
        ld  a, #0xFF
        ldh (#0x25), a
    .gold_no_mono:
        ret
    __endasm;
}
#endif

void gbs_play_trampoline(void) __naked {
    __asm
        di
        ld  a, (#0xFFFF)
        ld  (#GBS_HELPER_IE_SAVE_ADDR), a
        xor a, a
        ld  (#0xFFFF), a
        ld  (#GBS_HELPER_SP_SAVE_ADDR), sp
        ld  sp, #GBS_PLAY_STACK_PTR
        ld  a, (#_mono_flag)
        or  a, a
        jr  z, .no_pre_mono
        ld  a, #0xFF
        ldh (#0x25), a
    .no_pre_mono:
        call #GBS_PLAY_ADDR
        ld  a, (#_mono_flag)
        or  a, a
        jr  z, .no_mono
        ld  a, #0xFF
        ldh (#0x25), a
    .no_mono:
        di
        ld  hl, #GBS_HELPER_SP_SAVE_ADDR
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  sp, hl
        ld  a, (#GBS_HELPER_IE_SAVE_ADDR)
        ld  (#0xFFFF), a
        ret
    __endasm;
}

// ── ISR ──────────────────────────────────────────────────────────
#if USE_TIMER
void timer_isr(void) {
    UINT8 fade_shadow_base;
#if GBS_HAS_CEEA_FLAG
    GBS_WRAM_BANK_BACKUP = GBS_HRAM_ROM_BANK;
    GBS_WRAM_VBL_OCCURRED = 0;
#endif
    if (runtime_is_playing()) {
        select_play_bank();
        fade_shadow_base = fade_shadow_push();
#if GBS_COMPAT_GS
        gbs_gold_play_trampoline();
#else
        gbs_play_trampoline();
#endif
        fade_shadow_pop(fade_shadow_base);
        if (fade_vol != PL_NONE) {
            fade_tick_isr();
            if (GBS_VOL_SHADOW_ADDR == 0u) {
                NR50_REG = fade_nr50(fade_vol);
            }
        }
        restore_ui_regs();
    }
}
void vbl_count_isr(void) {
#if GBS_HAS_CEEA_FLAG
    GBS_WRAM_BANK_BACKUP = GBS_HRAM_ROM_BANK;
    GBS_WRAM_VBL_OCCURRED = 0;
#endif
    if (runtime_is_playing()) {
        vbl_cnt++;
    }
}
#else
void vbl_play_isr(void) {
    UINT8 fade_shadow_base;
#if GBS_HAS_CEEA_FLAG
    GBS_WRAM_BANK_BACKUP = GBS_HRAM_ROM_BANK;
    GBS_WRAM_VBL_OCCURRED = 0;
#endif
    if (runtime_is_playing()) {
        select_play_bank();
        fade_shadow_base = fade_shadow_push();
#if GBS_COMPAT_GS
        gbs_gold_play_trampoline();
#else
        gbs_play_trampoline();
#endif
        fade_shadow_pop(fade_shadow_base);
        if (fade_vol != PL_NONE) {
            fade_tick_isr();
            if (GBS_VOL_SHADOW_ADDR == 0u) {
                NR50_REG = fade_nr50(fade_vol);
            }
        }
        restore_ui_regs();
    }
    if (runtime_is_playing()) {
        vbl_cnt++;
    }
}
#endif

// ── GBS Control ───────────────────────────────────────────────────
static void gbs_start(UINT8 song) {
    disable_interrupts();
    IE_REG  &= ~TIM_IFLAG;
    TAC_REG  = 0x00;
    runtime_set_play_state(0u, 0u);
    reset_fade_state();
    audio_hw_silence();
    NR52_REG = 0x80; NR50_REG = 0x77; NR51_REG = 0xFF;
    GBS_HRAM_ROM_BANK = 1;
#if GBS_HAS_CEEA_FLAG
    GBS_WRAM_BANK_BACKUP = 1;
    GBS_WRAM_VBL_OCCURRED = 0;
#endif
    mono_flag = sav.mono;
    cur_song  = song;
    gbs_init_song = song;
#if GBS_COMPAT_RB
    reset_red_audio_wram();
    *((volatile UINT8 *)0xC02A) = 0x00u;
    *((volatile UINT8 *)0xC02B) = 0x00u;
    *((volatile UINT8 *)0xC02C) = 0x00u;
    *((volatile UINT8 *)0xC02D) = 0x00u;
#endif
    BANK1();
#if GBS_COMPAT_GS
    __asm
        ld  a, (#_gbs_init_song)
        call _gbs_gold_init_trampoline
    __endasm;
#else
    __asm
        ld  a, (#_gbs_init_song)
        call _gbs_init_trampoline
    __endasm;
#endif
#if GBS_COMPAT_RB
    GBS_HRAM_ROM_BANK = current_red_play_bank();
#endif
    restore_ui_regs();
    runtime_set_play_state(1u, 0u);
    vbl_cnt     = 0;
    silence_cnt = 0;
    reset_silence_state();
    fade_vol    = PL_NONE;
    name_scroll_pos = 0;
    name_scroll_wait = 0;
    name_scroll_wrap = 0;
    sync_android_status();
#if USE_TIMER
    TMA_REG = GBS_TIMER_MOD;
    TAC_REG = GBS_TIMER_CTL;
    IE_REG |= TIM_IFLAG;
#endif
    enable_interrupts();
    redraw = 1;
}

static void gbs_stop(void) {
    disable_interrupts();
    IE_REG  &= ~TIM_IFLAG;
    TAC_REG  = 0x00;
    runtime_set_play_state(0u, 0u);
    reset_silence_state();
#if GBS_COMPAT_RB
    reset_red_audio_wram();
    *((volatile UINT8 *)0xC02A) = 0x00u;
    *((volatile UINT8 *)0xC02B) = 0x00u;
    *((volatile UINT8 *)0xC02C) = 0x00u;
    *((volatile UINT8 *)0xC02D) = 0x00u;
#endif
    audio_hw_silence();
    sync_android_status();
    enable_interrupts();
    redraw = 1;
}

static void gbs_fade_start(void) {
    if (sav.fade_time == 0u) {
        gbs_stop();
        fade_wait = FADE_GAP;
        return;
    }
    fade_vol = 7;
    fade_cnt = 0;
}

static void gbs_pause(void) {
    disable_interrupts();
    runtime_set_play_state(0u, 1u);
    NR50_REG = 0x00;
    NR51_REG = 0x00;
    sync_android_status();
    enable_interrupts();
    redraw = 1;
}

static void gbs_resume(void) {
    disable_interrupts();
    runtime_set_play_state(1u, 0u);
    NR51_REG = 0xFF;
    NR50_REG = 0x77;
    sync_android_status();
    enable_interrupts();
    redraw = 1;
}

static void sync_cursors(void);

static void android_play_current_source(void) {
    if (play_src == 1u && sav.count) {
        if (pl_idx == PL_NONE || pl_idx >= sav.count) {
            pl_idx = 0u;
        }
        gbs_start(sav.tracks[pl_idx]);
        sync_cursors();
    } else {
        if (cur_song >= (UINT8)GBS_NUM_SONGS) {
            cur_song = 0u;
        }
        play_src = 0u;
        pl_idx = PL_NONE;
        gbs_start(cur_song);
        sync_cursors();
    }
}

// ── Helpers ──────────────────────────────────────────────────────
static UINT8 pl_find(UINT8 song) {
    UINT8 i;
    for (i = 0; i < sav.count; i++) {
        if (sav.tracks[i] == song) return i;
    }
    return PL_NONE;
}

// ── Display ───────────────────────────────────────────────────────
#define CHR(c) ((UINT8)((c) - 0x20u))

// カスタムエンコーディングからタイルインデックスへ変換
// 濁点・半濁点は別文字 (1タイル占有)
static UINT8 enc_to_tile(UINT8 enc) {
    if (enc >= 0xB0u && enc <= 0xDDu)
        return (UINT8)(JP_KATA_START + (enc - 0xB0u));       // base kata ア-ン
    if (enc >= 0x80u && enc <= 0xADu)
        return (UINT8)(JP_HIRA_START + (enc - 0x80u));       // base hira あ-ん
    if (enc >= 0x20u && enc <= 0x7Eu)
        return (UINT8)(enc - 0x20u);                          // ASCII
    if (enc >= 0x0Du && enc <= 0x15u)
        return (UINT8)(JP_SMALL_KATA_START + (enc - 0x0Du)); // small kata ァ-ッ
    if (enc >= 0x04u && enc <= 0x0Cu)
        return (UINT8)(JP_SMALL_HIRA_START + (enc - 0x04u)); // small hira ぁ-っ
    if (enc == 0x03u) return JP_LONG_VOWEL;                   // ー
    if (enc == 0x02u) return JP_HANDAKUTEN;                   // ゜
    if (enc == 0x01u) return JP_DAKUTEN;                      // ゛
    return T_SPACE;
}

static void fb_str(UINT8 x, UINT8 y, const char *s) {
    while (*s && x < SCR_W) fb[y][x++] = CHR(*s++);
}

// カスタムエンコーディング文字列をfbに描画
static void fb_enc_str(UINT8 x, UINT8 y, const UINT8 *s, UINT8 maxw) {
    while (*s && maxw > 0u && x < SCR_W) {
        fb[y][x++] = enc_to_tile(*s++);
        maxw--;
    }
}

// カスタムエンコーディング文字列をスクロール付きでfbに描画
static void fb_enc_scroll(UINT8 x, UINT8 y, const UINT8 *s,
                           UINT8 maxw, UINT8 offset) {
    UINT8 len, i, wrap, ci;
    for (len = 0; s[len]; len++) {}
    if (len <= maxw) {
        fb_enc_str(x, y, s, maxw);
        return;
    }
    wrap = (UINT8)(len + 3u);
    name_scroll_wrap = wrap; // 一周検出用に記録
    for (i = 0; i < maxw; i++) {
        ci = (UINT8)((offset + i) % wrap);
        fb[y][(UINT8)(x + i)] = (ci < len) ? enc_to_tile(s[ci]) : T_SPACE;
    }
}

// カスタムエンコード文字列をスクロール付きでfbに描画 (曲名スクロール状態を変更しない)
static void fb_enc_scroll_static(UINT8 x, UINT8 y, const UINT8 *s,
                                 UINT8 maxw, UINT8 offset) {
    UINT8 len, i, wrap, ci;
    for (len = 0; s[len]; len++) {}
    if (len <= maxw) {
        fb_enc_str(x, y, s, maxw);
        return;
    }
    wrap = (UINT8)(len + 3u);
    for (i = 0; i < maxw; i++) {
        ci = (UINT8)((offset + i) % wrap);
        fb[y][(UINT8)(x + i)] = (ci < len) ? enc_to_tile(s[ci]) : T_SPACE;
    }
}

static UINT8 enc_scroll_wrap(const UINT8 *s, UINT8 maxw) {
    UINT8 len;
    for (len = 0; s[len]; len++) {}
    return (len <= maxw) ? 0u : (UINT8)(len + 3u);
}

// スクロール付き文字列描画
static void fb_scroll_str(UINT8 y, const char *s, UINT8 offset,
                           UINT8 x0, UINT8 w) {
    UINT8 len, x, wrap, ci;
    for (len = 0; s[len]; len++) {}
    if (len <= w) {
        fb_str(x0, y, s);
        return;
    }
    wrap = (UINT8)(len + 3u);
    for (x = 0; x < w; x++) {
        ci = (UINT8)((offset + x) % wrap);
        fb[y][(UINT8)(x0 + x)] = (ci < len) ? CHR(s[ci]) : T_SPACE;
    }
}

static void fb_u8(UINT8 x, UINT8 y, UINT8 n) {
    fb[y][x]   = CHR('0' + n / 10u);
    fb[y][x+1] = CHR('0' + n % 10u);
}

// 3桁表示 (100以上の曲番号対応)
static void fb_u8_3(UINT8 x, UINT8 y, UINT8 n) {
    if (n >= 100u) {
        fb[y][x]   = CHR('0' + n / 100u);
        fb[y][x+1] = CHR('0' + (n / 10u) % 10u);
        fb[y][x+2] = CHR('0' + n % 10u);
    } else {
        fb[y][x]   = CHR('0' + n / 10u);
        fb[y][x+1] = CHR('0' + n % 10u);
        fb[y][x+2] = CHR(':');
    }
}

// 曲の長さ表示: /D:DD を fb[3][7-11] に書き込む
static void fb_duration(void) {
    UINT8 tt_idx;
    UINT16 dur_secs;
    UINT8 d_mn, d_sc;
    fb[3][7] = CHR('/');
    tt_idx = sav.track_time[cur_song];
    if (sav.repeat == 1u || tt_idx == 1u) {
        fb[3][8] = CHR('-');
        fb[3][9] = CHR(':');
        fb[3][10] = CHR('-');
        fb[3][11] = CHR('-');
    } else {
        dur_secs = (UINT16)(track_time_tbl[tt_idx] / 60u + fade_secs_tbl[sav.fade_time] + 1u);
        d_mn = (UINT8)(dur_secs / 60u);
        d_sc = (UINT8)(dur_secs % 60u);
        if (d_mn > 9u) d_mn = 9;
        fb[3][8] = CHR('0' + d_mn);
        fb[3][9] = CHR(':');
        fb[3][10] = CHR('0' + d_sc / 10u);
        fb[3][11] = CHR('0' + d_sc % 10u);
    }
}

static void fb_player_button(UINT8 x, UINT8 y, UINT8 w, const char *label, UINT8 action) {
    UINT8 i, len, tx, pressed, selected;
    pressed = (player_press_action == action);
    selected = (player_cursor_timer && player_sel == action);
    len = 0;
    while (label[len]) len++;

    fb[y][x] = T_CORNER_TL;
    for (i = 1u; i + 1u < w; i++) {
        fb[y][(UINT8)(x + i)] = pressed ? T_BAR_H_CTR : T_BAR_H_TOP;
    }
    fb[y][(UINT8)(x + w - 1u)] = T_CORNER_TR;

    fb[(UINT8)(y + 1u)][x] = T_BAR_V_LEFT;
    for (i = 1u; i + 1u < w; i++) {
        fb[(UINT8)(y + 1u)][(UINT8)(x + i)] = T_SPACE;
    }
    fb[(UINT8)(y + 1u)][(UINT8)(x + w - 1u)] = T_BAR_V_RIGHT;

    fb[(UINT8)(y + 2u)][x] = T_CORNER_BL;
    for (i = 1u; i + 1u < w; i++) {
        fb[(UINT8)(y + 2u)][(UINT8)(x + i)] = pressed ? T_BAR_H_BOT : T_BAR_H_BOT;
    }
    fb[(UINT8)(y + 2u)][(UINT8)(x + w - 1u)] = T_CORNER_BR;

    tx = (UINT8)(x + ((w - len) / 2u));
    fb_str(tx, (UINT8)(y + 1u), label);
    if (selected) {
        fb[(UINT8)(y + 1u)][x] = CHR('>');
    }
    if (pressed) {
        fb[y][(UINT8)(x + 1u)] = T_BAR_H_CTR;
        fb[(UINT8)(y + 2u)][(UINT8)(x + 1u)] = T_BAR_H_CTR;
    }
}

// 曲名スクロール行更新
static void scroll_name_row(UINT8 row, UINT8 song, UINT8 show_number) {
    UINT8 j;
    UINT8 name_x;
    UINT8 name_w;
    const UINT8 *nm = get_song_name(song);
    name_x = show_number ? 4u : 1u;
    name_w = show_number ? 16u : 19u;
    if (nm[0]) {
        for (j = name_x; j < 20u; j++) fb[row][j] = T_SPACE;
        fb_enc_scroll(name_x, row, nm, name_w, name_scroll_pos);
        set_bkg_tiles(name_x, row, name_w, 1, &fb[row][name_x]);
    }
}

// 曲リスト行の描画 (全画面幅: cols 0-19, 枠なし)
// format: [icon]NN:songname  (icon=1col, NN=2col, :=1col, name=16col)
// 100曲以上: [icon]NNN songname
// do_scroll: カーソルまたは再生中の行 → 曲名が長い場合スクロール
static void fb_song_row(UINT8 row, UINT8 song_idx, UINT8 is_cursor,
                         UINT8 is_playing, UINT8 is_paused,
                         UINT8 grab_cursor, UINT8 do_scroll,
                         UINT8 show_number) {
    const UINT8 *name;
    UINT8 name_x;
    UINT8 name_w;
    if (grab_cursor) {
        fb[row][0] = T_ICON_GRAB;
    } else if (is_cursor) {
        fb[row][0] = CHR('>');
    }

    if (is_playing) {
        fb[row][0] = T_ICON_PLAY;
    } else if (is_paused) {
        fb[row][0] = T_ICON_PAUSE;
    }

    name = get_song_name(song_idx);
    name_x = show_number ? 4u : 1u;
    name_w = show_number ? 16u : 19u;
    if (show_number) {
        if ((UINT8)GBS_NUM_SONGS >= 100u) {
            // 3桁: "NNN songname"
            fb_u8_3(1, row, (UINT8)(song_idx + 1u));
        } else {
            // 2桁: "NN:songname"
            fb_u8(1, row, (UINT8)(song_idx + 1u));
            fb[row][3] = CHR(':');
        }
    }
    if (name[0]) {
        if (do_scroll)
            fb_enc_scroll(name_x, row, name, name_w, name_scroll_pos);
        else
            fb_enc_str(name_x, row, name, name_w);
    }
}

// fb を構築
static void build_fb(void) {
    static const char *rpt[3] = {"---","ONE","ALL"};
    UINT8 i, j, idx, s0, p0, row;

    memset(fb, T_SPACE, sizeof(fb));

    // ── フレーム: 上枠 (row 0) + タイトル ──
    fb[0][0] = T_CORNER_TL;
    fb[0][19] = T_CORNER_TR;
    fb_enc_scroll_static(1, 0, display_title(), 18, (view == VIEW_PLAYER) ? 0u : header_scroll_pos);

    // ── フレーム: 左右枠 (rows 1-3) ──
    for (i = 1; i <= 3; i++) {
        fb[i][0] = T_BAR_V_LEFT;
        fb[i][19] = T_BAR_V_RIGHT;
    }

    // ── ヘッダー: rows 1-3 ──
    // Row 1: 再生中の曲名
    if (playing || paused) {
        const UINT8 *pnm = get_song_name(cur_song);
        if (pnm[0])
            fb_enc_scroll(1, 1, pnm, 18, name_scroll_pos);
    }
    // Row 2: 作曲者
    fb_enc_scroll_static(1, 2, display_author(), 18, (view == VIEW_PLAYER) ? 0u : header_scroll_pos);

    // Row 3: ステータス行
    {
        UINT16 secs;
        UINT8 mn, sc;
        if (playing)
            fb[3][1] = T_ICON_PLAY;
        else if (paused)
            fb[3][1] = T_ICON_PAUSE;

        if (paused && (scroll_pos & 4u)) {
            // 点滅: スペース (経過時間 + 曲の長さ)
        } else {
            secs = vbl_cnt / 60u;
            mn = (UINT8)(secs / 60u);
            sc = (UINT8)(secs % 60u);
            if (mn > 9u) mn = 9;
            fb[3][3] = CHR('0' + mn);
            fb[3][4] = CHR(':');
            fb[3][5] = CHR('0' + sc / 10u);
            fb[3][6] = CHR('0' + sc % 10u);
            fb_duration();
        }

        fb[3][18] = (sav.repeat == 0u) ? T_RPT_NONE :
                    (sav.repeat == 1u) ? T_RPT_ONE  : T_RPT_ALL;
    }

    if (view == VIEW_PLAYER) {
        fb[4][0] = T_CORNER_BL;
        fb[4][1] = T_BRACKET_BL;
        fb_str(2, 4, "PLAYER");
        fb[4][9] = T_BRACKET_BR;
        for (j = 10; j < 19; j++) fb[4][j] = T_BAR_H_BOT;
        fb[4][19] = T_CORNER_BR;

        fb_player_button(0, 7, 7, "PREV", PLAYER_ACT_PREV);
        fb_player_button(7, 7, 6, (playing && !paused) ? "PAUS" : "PLAY", PLAYER_ACT_TOGGLE);
        fb_player_button(13, 7, 7, "NEXT", PLAYER_ACT_NEXT);
        fb_player_button(0, 12, 6, "BACK", PLAYER_ACT_BACK);
        fb_player_button(7, 12, 6, "STOP", PLAYER_ACT_STOP);
        fb_player_button(14, 12, 6, "RPT", PLAYER_ACT_RPT);
    } else if (view == 2u) {
        // ══ オプション画面 ══
        opt_count = 0;
        if (pl_find(opt_song) == PL_NONE && sav.count < MAX_PL)
            opt_items[opt_count++] = OPT_ADD;
        if (pl_find(opt_song) != PL_NONE)
            opt_items[opt_count++] = OPT_DEL;
        // Move (PL画面からのみ、曲数2以上)
        if (prev_view == 1u && sav.count > 1u)
            opt_items[opt_count++] = OPT_MOVE;
        opt_items[opt_count++] = OPT_TIME;
        opt_items[opt_count++] = OPT_FADE;
        opt_items[opt_count++] = OPT_SIL;
        opt_items[opt_count++] = OPT_RPT;
        opt_items[opt_count++] = OPT_MONO;
        if (opt_sel >= opt_count) opt_sel = (UINT8)(opt_count - 1u);

        // Row 4: 仕切り + [OPTION] ラベル
        fb[4][0] = T_TJUNC_LEFT;
        fb[4][1] = T_BRACKET_L;
        fb_str(2, 4, "OPTION");
        fb[4][8] = T_BRACKET_R;
        for (j = 9; j < 19; j++) fb[4][j] = T_BAR_H_CTR;
        fb[4][19] = T_TJUNC_RIGHT;

        // Rows 5-12: 左右枠
        for (i = 5; i <= 12; i++) {
            fb[i][0] = T_BAR_V_LEFT;
            fb[i][19] = T_BAR_V_RIGHT;
        }

        // SONG番号
        fb_str(2, 5, "SONG:");
        fb_u8(7, 5, (UINT8)(opt_song + 1u));

        // オプション項目 (rows 6-12, カーソルに追従してスクロール)
        p0 = (opt_sel >= OPT_VISIBLE_ROWS) ? (UINT8)(opt_sel - (OPT_VISIBLE_ROWS - 1u)) : 0u;
        for (i = 0; i < OPT_VISIBLE_ROWS; i++) {
            UINT8 opt_idx = (UINT8)(p0 + i);
            row = (UINT8)(6u + i);
            if (opt_idx >= opt_count) continue;

            fb[row][1] = (opt_idx == opt_sel) ? CHR('>') : T_SPACE;
            if (opt_items[opt_idx] == OPT_ADD) {
                fb_str(2, row, "ADD PLAYLIST");
            } else if (opt_items[opt_idx] == OPT_DEL) {
                fb_str(2, row, "DEL PLAYLIST");
            } else if (opt_items[opt_idx] == OPT_MOVE) {
                fb_str(2, row, "Move");
            } else if (opt_items[opt_idx] == OPT_TIME) {
                fb_str(2, row, "Time:");
                fb_str(8, row, track_time_str[sav.track_time[opt_song]]);
            } else if (opt_items[opt_idx] == OPT_FADE) {
                fb_str(2, row, "Fade:");
                fb_str(8, row, fade_time_str[sav.fade_time]);
            } else if (opt_items[opt_idx] == OPT_SIL) {
                fb_str(2, row, "Sil:");
                fb_str(7, row, silence_str[sav.silence]);
            } else if (opt_items[opt_idx] == OPT_RPT) {
                fb_str(2, row, "RPT:");
                fb_str(7, row, rpt[sav.repeat]);
            } else {
                fb_str(2, row, "Out:");
                fb_str(7, row, sav.mono ? "MONO" : "STEREO");
            }
        }

        // Row 13: 下枠
        fb[13][0] = T_CORNER_BL;
        fb[13][19] = T_CORNER_BR;
        for (j = 1; j < 19; j++) fb[13][j] = T_BAR_H_BOT;

        fb_str(0, 15, "B:Back A/LR:Change");
        fb_str(0, 16, "Up/Down:Select");
    } else if (view == 0u) {
        // ══ SONGS 全画面 ══
        fb[4][0] = T_CORNER_BL;
        fb[4][1] = T_BRACKET_BL;
        fb_str(2, 4, "SONGS");
        fb[4][7] = T_BRACKET_BR;
        for (j = 8; j < 19; j++) fb[4][j] = T_BAR_H_BOT;
        fb[4][19] = T_CORNER_BR;

        // 曲リスト (全幅: cols 0-19, 枠なし, 8行)
        s0 = (sel >= 7u) ? (UINT8)(sel - 6u) : 0u;
        for (i = 0; i < 8u; i++) {
            row = (UINT8)(5u + i);
            idx = (UINT8)(s0 + i);
            if (idx < (UINT8)GBS_NUM_SONGS) {
                fb_song_row(row, idx,
                            (idx == sel),
                            (idx == cur_song && playing),
                            (idx == cur_song && paused),
                            0,
                            (idx == sel || (idx == cur_song && (playing || paused))),
                            1u);
            }
        }

        // Row 13: 下枠 + カウンター (枠なし)
        for (j = 0; j < 12; j++) fb[13][j] = T_BAR_H_BOT;
        fb[13][12] = T_BRACKET_BL;
        fb_u8(13, 13, (UINT8)(sel + 1u));
        fb[13][15] = CHR('/');
        fb_u8(16, 13, (UINT8)GBS_NUM_SONGS);
        fb[13][18] = T_BRACKET_BR;
        fb[13][19] = T_BAR_H_BOT;

        fb_str(0, 15, "LR:SK B:Stop A:Play");
        fb_str(0, 16, "SELECT:PL START:Opt");
    } else {
        // ══ PLAYLIST 全画面 ══
        fb[4][0] = T_CORNER_BL;
        fb[4][1] = T_BRACKET_BL;
        fb_str(2, 4, "PLAYLIST");
        fb[4][10] = T_BRACKET_BR;
        for (j = 11; j < 19; j++) fb[4][j] = T_BAR_H_BOT;
        fb[4][19] = T_CORNER_BR;

        if (sav.count == 0u) {
            fb_str(6, 8, "(empty)");
        } else {
            p0 = (pl_sel >= 7u) ? (UINT8)(pl_sel - 6u) : 0u;
            for (i = 0; i < 8u; i++) {
                row = (UINT8)(5u + i);
                idx = (UINT8)(p0 + i);
                if (idx < sav.count) {
                    fb_song_row(row, sav.tracks[idx],
                                (idx == pl_sel),
                                (idx == pl_idx && playing),
                                (idx == pl_idx && paused),
                                (grab != PL_NONE && idx == pl_sel),
                                (idx == pl_sel || (idx == pl_idx && (playing || paused))),
                                0u);
                }
            }
        }

        // Row 13: 下枠 + カウンター (枠なし)
        for (j = 0; j < 12; j++) fb[13][j] = T_BAR_H_BOT;
        fb[13][12] = T_BRACKET_BL;
        if (sav.count) {
            fb_u8(13, 13, (UINT8)(pl_sel + 1u));
            fb[13][15] = CHR('/');
            fb_u8(16, 13, sav.count);
        }
        fb[13][18] = T_BRACKET_BR;
        fb[13][19] = T_BAR_H_BOT;

        if (grab != PL_NONE) {
            fb_str(0, 15, "B:Cancel A/SEL:Set");
            fb_str(0, 16, "Up/Down:Move");
        } else {
            fb_str(0, 15, "LR:SK B:Stop A:Play");
            fb_str(0, 16, "SEL:Song START:Opt");
        }
    }
}

// 1フレームあたり最大 ROWS_PER_FRAME 行を VRAM に転送
#define ROWS_PER_FRAME 6
static void flush_fb(void) {
    UINT8 i, end;
    if (!fb_row) return;
    end = fb_row + ROWS_PER_FRAME;
    if (end > SCR_H + 1u) end = SCR_H + 1u;
    for (i = fb_row; i < end; i++) {
        set_bkg_tiles(0, (UINT8)(i - 1u), SCR_W, 1, fb[i - 1u]);
    }
    fb_row = (end > SCR_H) ? 0u : end;
}

// ヘッダー軽量更新 (行0-3毎フレーム、曲名はスクロール時のみ)
// scroll_dirty: 1=タイトル/作曲者更新, 2=曲名更新, 3=両方
static UINT8 scroll_dirty;

static void update_header(void) {
    UINT8 j;
    UINT16 secs;
    UINT8 mn, sc;

    if (view == VIEW_PLAYER) {
        if (paused && (scroll_pos & 4u)) {
            for (j = 3; j <= 11; j++) fb[3][j] = T_SPACE;
        } else {
            secs = vbl_cnt / 60u;
            mn = (UINT8)(secs / 60u);
            sc = (UINT8)(secs % 60u);
            if (mn > 9u) mn = 9;
            fb[3][3] = CHR('0' + mn);
            fb[3][4] = CHR(':');
            fb[3][5] = CHR('0' + sc / 10u);
            fb[3][6] = CHR('0' + sc % 10u);
            fb_duration();
        }
        set_bkg_tiles(3, 3, 9, 1, &fb[3][3]);
        scroll_dirty = 0;
        return;
    }

    // 行0: タイトルスクロール (header_scroll_posが変わった時のみ)
    if (scroll_dirty & 1u) {
        for (j = 1; j < 19; j++) fb[0][j] = T_SPACE;
        fb_enc_scroll_static(1, 0, display_title(), 18, header_scroll_pos);
        set_bkg_tiles(1, 0, 18, 1, &fb[0][1]);
    }

    // 行1: 再生中の曲名スクロール (name_scroll_posが変わった時のみ)
    if (scroll_dirty & 2u) {
        if (playing || paused) {
            const UINT8 *pnm = get_song_name(cur_song);
            if (pnm[0]) {
                for (j = 1; j < 19; j++) fb[1][j] = T_SPACE;
                fb_enc_scroll(1, 1, pnm, 18, name_scroll_pos);
                set_bkg_tiles(1, 1, 18, 1, &fb[1][1]);
            }
        }
    }

    // 行2: 作曲者スクロール (header_scroll_posが変わった時のみ)
    if (scroll_dirty & 1u) {
        for (j = 1; j < 19; j++) fb[2][j] = T_SPACE;
        fb_enc_scroll_static(1, 2, display_author(), 18, header_scroll_pos);
        set_bkg_tiles(1, 2, 18, 1, &fb[2][1]);
    }

    // 行3: 経過時間 + 曲の長さ (毎フレーム更新 — 9バイト)
    if (paused && (scroll_pos & 4u)) {
        for (j = 3; j <= 11; j++) fb[3][j] = T_SPACE;
    } else {
        secs = vbl_cnt / 60u;
        mn = (UINT8)(secs / 60u);
        sc = (UINT8)(secs % 60u);
        if (mn > 9u) mn = 9;
        fb[3][3] = CHR('0' + mn);
        fb[3][4] = CHR(':');
        fb[3][5] = CHR('0' + sc / 10u);
        fb[3][6] = CHR('0' + sc % 10u);
        fb_duration();
    }
    set_bkg_tiles(3, 3, 9, 1, &fb[3][3]);

    // 曲名スクロール (name_scroll_posが変わった時のみ、対象行だけ)
    if (scroll_dirty & 2u) {
        UINT8 cur_idx;

        if (view == 0u) {
            UINT8 s0;
            s0 = (sel >= 7u) ? (UINT8)(sel - 6u) : 0u;
            if (sel < (UINT8)GBS_NUM_SONGS)
                scroll_name_row((UINT8)(5u + sel - s0), sel, 1u);
            cur_idx = cur_song;
            if ((playing || paused) && cur_idx != sel &&
                cur_idx >= s0 && cur_idx < (UINT8)(s0 + 8u) &&
                cur_idx < (UINT8)GBS_NUM_SONGS)
                scroll_name_row((UINT8)(5u + cur_idx - s0), cur_idx, 1u);
        } else if (view == 1u && sav.count) {
            UINT8 p0;
            p0 = (pl_sel >= 7u) ? (UINT8)(pl_sel - 6u) : 0u;
            if (pl_sel < sav.count)
                scroll_name_row((UINT8)(5u + pl_sel - p0), sav.tracks[pl_sel], 0u);
            if ((playing || paused) && pl_idx != PL_NONE &&
                pl_idx != pl_sel &&
                pl_idx >= p0 && pl_idx < (UINT8)(p0 + 8u) &&
                pl_idx < sav.count)
                scroll_name_row((UINT8)(5u + pl_idx - p0), sav.tracks[pl_idx], 0u);
        }
    }

    scroll_dirty = 0;
}

// ── Playlist helpers ─────────────────────────────────────────────
static void sync_cursors(void) {
    if (play_src == 1u && pl_idx != PL_NONE && pl_idx < sav.count) {
        pl_sel = pl_idx;
        sel = sav.tracks[pl_idx];
    } else if (play_src == 0u) {
        sel = cur_song;
    }
    redraw = 1;
}

static void play_from_sel(void) {
    if (view == 1u && sav.count) {
        play_src = 1;
        pl_idx = pl_sel;
        gbs_start(sav.tracks[pl_idx]);
        sync_cursors();
    } else {
        play_src = 0;
        pl_idx = PL_NONE;
        gbs_start(sel);
    }
}

static void next_track(void) {
    if (play_src == 1u) {
        // Playlist mode
        if (pl_idx == PL_NONE || !sav.count) return;
        pl_idx = (UINT8)(pl_idx + 1u);
        if (pl_idx >= sav.count) {
            if (sav.repeat == 2u) {
                pl_idx = 0;
            } else {
                pl_idx = PL_NONE;
                gbs_stop();
                return;
            }
        }
        gbs_start(sav.tracks[pl_idx]);
    } else {
        // Songs mode
        UINT8 next = (UINT8)(cur_song + 1u);
        if (next >= (UINT8)GBS_NUM_SONGS) {
            if (sav.repeat == 2u) {
                next = 0;
            } else {
                gbs_stop();
                return;
            }
        }
        gbs_start(next);
    }
    sync_cursors();
}

static void prev_track(void) {
    if (play_src == 1u) {
        // Playlist mode
        if (pl_idx == PL_NONE || !sav.count) return;
        if (pl_idx == 0u) {
            if (sav.repeat == 2u) {
                pl_idx = (UINT8)(sav.count - 1u);
            } else {
                return;
            }
        } else {
            pl_idx--;
        }
        gbs_start(sav.tracks[pl_idx]);
    } else {
        // Songs mode
        if (cur_song == 0u) {
            if (sav.repeat == 2u) {
                gbs_start((UINT8)(GBS_NUM_SONGS - 1u));
            } else {
                return;
            }
        } else {
            gbs_start((UINT8)(cur_song - 1u));
        }
    }
    sync_cursors();
}

static void player_do_action(UINT8 action) {
    if (action == PLAYER_ACT_PREV) {
        reset_fade_state();
        if (playing || paused) {
            prev_track();
        } else if (play_src == 1u && sav.count) {
            if (pl_idx == PL_NONE || pl_idx >= sav.count) {
                pl_idx = 0u;
            } else if (pl_idx == 0u) {
                pl_idx = (sav.repeat == 2u) ? (UINT8)(sav.count - 1u) : 0u;
            } else {
                pl_idx--;
            }
            gbs_start(sav.tracks[pl_idx]);
            sync_cursors();
        } else {
            if (cur_song > 0u) {
                gbs_start((UINT8)(cur_song - 1u));
            } else if (sav.repeat == 2u) {
                gbs_start((UINT8)(GBS_NUM_SONGS - 1u));
            } else {
                gbs_start(cur_song);
            }
            play_src = 0u;
            pl_idx = PL_NONE;
            sync_cursors();
        }
    } else if (action == PLAYER_ACT_TOGGLE) {
        if (paused) {
            gbs_resume();
        } else if (playing) {
            gbs_pause();
        } else {
            android_play_current_source();
        }
    } else if (action == PLAYER_ACT_NEXT) {
        reset_fade_state();
        if (playing || paused) {
            next_track();
        } else if (play_src == 1u && sav.count) {
            if (pl_idx == PL_NONE || pl_idx >= sav.count) {
                pl_idx = 0u;
            } else {
                pl_idx = (UINT8)(pl_idx + 1u);
                if (pl_idx >= sav.count) {
                    pl_idx = (sav.repeat == 2u) ? 0u : (UINT8)(sav.count - 1u);
                }
            }
            gbs_start(sav.tracks[pl_idx]);
            sync_cursors();
        } else {
            if ((UINT8)(cur_song + 1u) < (UINT8)GBS_NUM_SONGS) {
                gbs_start((UINT8)(cur_song + 1u));
            } else if (sav.repeat == 2u) {
                gbs_start(0u);
            } else {
                gbs_start(cur_song);
            }
            play_src = 0u;
            pl_idx = PL_NONE;
            sync_cursors();
        }
    } else if (action == PLAYER_ACT_BACK) {
        view = player_prev_view;
        if (view == VIEW_OPT || view == VIEW_PLAYER) view = VIEW_SONGS;
        redraw = 1;
    } else if (action == PLAYER_ACT_STOP) {
        reset_fade_state();
        gbs_stop();
    } else if (action == PLAYER_ACT_RPT) {
        sav.repeat = (UINT8)((sav.repeat + 1u) % 3u);
        sav_rw(1);
        sync_android_status();
        redraw = 1;
    }
}

static void process_android_command(void) {
    UINT8 cmd;
    UINT8 arg;

    cmd = ANDROID_CMD_ADDR;
    if (cmd == ANDROID_CMD_NONE) return;

    arg = ANDROID_CMD_ARG_ADDR;
    ANDROID_CMD_ADDR = ANDROID_CMD_NONE;
    ANDROID_CMD_ARG_ADDR = 0u;

    if (cmd == ANDROID_CMD_TOGGLE) {
        player_do_action(PLAYER_ACT_TOGGLE);
        return;
    }

    if (cmd == ANDROID_CMD_STOP) {
        player_do_action(PLAYER_ACT_STOP);
        return;
    }

    if (cmd == ANDROID_CMD_NEXT) {
        player_do_action(PLAYER_ACT_NEXT);
        return;
    }

    if (cmd == ANDROID_CMD_PREV) {
        player_do_action(PLAYER_ACT_PREV);
        return;
    }

    if (cmd == 5u && arg < (UINT8)GBS_NUM_SONGS) {
        reset_fade_state();
        play_src = 0u;
        pl_idx = PL_NONE;
        gbs_start(arg);
        sync_cursors();
        return;
    }

    if (cmd == ANDROID_CMD_REPEAT) {
        if (arg < 3u) {
            sav.repeat = arg;
        } else {
            sav.repeat = (UINT8)((sav.repeat + 1u) % 3u);
        }
        sav_rw(1);
        sync_android_status();
        redraw = 1;
    }

    if (cmd == ANDROID_CMD_PLAYER_DOWN) {
        if (view == VIEW_PLAYER && arg <= PLAYER_ACT_RPT) {
            player_sel = arg;
            player_press_action = arg;
            player_press_timer = 0u;
            player_do_action(arg);
            redraw = 1;
        }
        return;
    }

    if (cmd == ANDROID_CMD_PLAYER_UP) {
        if (player_press_action == arg) {
            player_press_action = PLAYER_ACT_NONE;
            redraw = 1;
        }
        return;
    }
}

// PL並べ替え実行: grabからpl_selへインサート移動
static void pl_do_move(void) {
    UINT8 k, tmp;
    if (grab == PL_NONE || grab == pl_sel) {
        grab = PL_NONE;
        redraw = 1;
        return;
    }
    tmp = sav.tracks[grab];
    if (grab < pl_sel) {
        for (k = grab; k < pl_sel; k++)
            sav.tracks[k] = sav.tracks[(UINT8)(k + 1u)];
    } else {
        for (k = grab; k > pl_sel; k--)
            sav.tracks[k] = sav.tracks[(UINT8)(k - 1u)];
    }
    sav.tracks[pl_sel] = tmp;
    if (pl_idx == grab) {
        pl_idx = pl_sel;
    } else if (grab < pl_sel) {
        if (pl_idx > grab && pl_idx <= pl_sel) pl_idx--;
    } else {
        if (pl_idx >= pl_sel && pl_idx < grab) pl_idx++;
    }
    sav_rw(1);
    grab = PL_NONE;
    redraw = 1;
}

// ── Input ─────────────────────────────────────────────────────────
static void handle_input(void) {
    UINT8 cj = joypad();
    UINT8 j  = cj & (UINT8)~pj;  // 新規押下
    UINT8 ud, move, k, target;
    UINT8 *curs;
    UINT8 mx;

    if ((cj & (J_START | J_SELECT)) == (J_START | J_SELECT) &&
        (j & (J_START | J_SELECT))) {
        if (view == VIEW_PLAYER) {
            view = player_prev_view;
            if (view == VIEW_OPT || view == VIEW_PLAYER) view = VIEW_SONGS;
        } else {
            player_prev_view = (view == VIEW_OPT) ? prev_view : view;
            player_sel = PLAYER_ACT_TOGGLE;
            player_press_action = PLAYER_ACT_NONE;
            player_press_timer = 0u;
            player_cursor_timer = PLAYER_CURSOR_TIMEOUT;
            grab = PL_NONE;
            view = VIEW_PLAYER;
        }
        pj = cj;
        redraw = 1;
        return;
    }

    if (view == VIEW_PLAYER) {
        pj = cj;
        if (j) {
            player_cursor_timer = PLAYER_CURSOR_TIMEOUT;
        }
        if (j & J_LEFT) {
            if (player_sel == 0u) player_sel = PLAYER_ACT_RPT;
            else player_sel--;
            redraw = 1;
        }
        if (j & J_RIGHT) {
            player_sel = (UINT8)((player_sel + 1u) % 6u);
            redraw = 1;
        }
        if (j & J_UP) {
            if (player_sel >= 3u) player_sel = (UINT8)(player_sel - 3u);
            redraw = 1;
        }
        if (j & J_DOWN) {
            if (player_sel < 3u) player_sel = (UINT8)(player_sel + 3u);
            redraw = 1;
        }
        if (j & J_A) {
            player_press_action = player_sel;
            player_press_timer = 6u;
            player_do_action(player_sel);
            redraw = 1;
        }
        if (j & J_B) {
            player_do_action(PLAYER_ACT_BACK);
        }
        return;
    }

    // オプション画面
    if (view == 2u) {
        UINT8 act;
        pj = cj;
        act = opt_items[opt_sel];
        if (j & (J_A | J_LEFT | J_RIGHT)) {
            if (act == OPT_ADD && (j & J_A)) {
                sav.tracks[sav.count++] = opt_song;
                sav_rw(1);
            } else if (act == OPT_DEL && (j & J_A)) {
                UINT8 di;
                di = pl_find(opt_song);
                if (di != PL_NONE) {
                    if (pl_idx != PL_NONE) {
                        if (di < pl_idx) pl_idx--;
                        else if (di == pl_idx) pl_idx = PL_NONE;
                    }
                    for (k = di; (UINT8)(k+1u) < sav.count; k++)
                        sav.tracks[k] = sav.tracks[(UINT8)(k+1u)];
                    sav.count--;
                    if (pl_sel >= sav.count && pl_sel) pl_sel--;
                    sav_rw(1);
                }
            } else if (act == OPT_MOVE && (j & J_A)) {
                // つかみモード開始: オプション画面を閉じてPL画面に戻る
                grab = pl_sel;
                view = prev_view;
                redraw = 1;
                return;
            } else if (act == OPT_TIME) {
                if (j & (J_A | J_RIGHT))
                    sav.track_time[opt_song] = (UINT8)((sav.track_time[opt_song] + 1u) % 7u);
                else
                    sav.track_time[opt_song] = (UINT8)((sav.track_time[opt_song] + 6u) % 7u);
                sav_rw(1);
            } else if (act == OPT_FADE) {
                if (j & (J_A | J_RIGHT))
                    sav.fade_time = (UINT8)((sav.fade_time + 1u) % 4u);
                else
                    sav.fade_time = (UINT8)((sav.fade_time + 3u) % 4u);
                sav_rw(1);
            } else if (act == OPT_SIL) {
                if (j & (J_A | J_RIGHT))
                    sav.silence = (UINT8)((sav.silence + 1u) % 4u);
                else
                    sav.silence = (UINT8)((sav.silence + 3u) % 4u);
                sav_rw(1);
            } else if (act == OPT_RPT) {
                if (j & (J_A | J_RIGHT))
                    sav.repeat = (UINT8)((sav.repeat + 1u) % 3u);
                else
                    sav.repeat = (UINT8)((sav.repeat + 2u) % 3u);
                sav_rw(1);
            } else if (act == OPT_MONO) {
                sav.mono = sav.mono ? 0u : 1u;
                mono_flag = sav.mono;
                sav_rw(1);
            }
            redraw = 1;
        }
        if (j & J_UP)   { if (opt_sel > 0u) opt_sel--; redraw = 1; }
        if (j & J_DOWN) { if (opt_sel + 1u < opt_count) opt_sel++; redraw = 1; }
        if (j & J_B) {
            view = prev_view;
            redraw = 1;
        }
        return;
    }

    ud = cj & (J_UP | J_DOWN);
    move = 0;

    // 上下キーリピート処理
    if (ud) {
        if (j & (J_UP | J_DOWN)) {
            rpt_cnt = 0;
            move = 1;
        } else {
            rpt_cnt++;
            if (rpt_cnt >= RPT_DELAY) {
                if (((UINT8)(rpt_cnt - RPT_DELAY) % RPT_SPEED) == 0u)
                    move = 1;
            }
        }
    } else {
        rpt_cnt = 0;
    }

    // SELECT 長押し判定
    if (cj & J_SELECT) {
        if (j & J_SELECT) {
            // SELECT 新規押下
            sel_hold_cnt = 0;
            sel_triggered = 0;
        } else {
            // SELECT 押し続け
            sel_hold_cnt++;
            if (sel_hold_cnt >= SEL_LONG_PRESS && !sel_triggered) {
                sel_triggered = 1;
                // PL画面でつかみモード
                if (view == 1u && sav.count > 1u) {
                    if (grab == PL_NONE) {
                        grab = pl_sel;
                    } else {
                        pl_do_move();
                    }
                    redraw = 1;
                }
            }
        }
    } else {
        // SELECT 離された
        if (pj & J_SELECT) {
            if (!sel_triggered) {
                // 短押し: 画面切替
                if (view == 0u) {
                    if (sav.count) view = 1;
                } else if (view == 1u) {
                    // PL→Songs に切替時、grab解除
                    if (grab != PL_NONE) {
                        grab = PL_NONE;
                    }
                    view = 0;
                }
                redraw = 1;
            }
        }
        sel_hold_cnt = 0;
        sel_triggered = 0;
    }

    pj = cj;

    curs = view ? &pl_sel : &sel;
    mx   = view
        ? (sav.count ? (UINT8)(sav.count - 1u) : 0u)
        : (UINT8)(GBS_NUM_SONGS - 1u);

    if (move) {
        if ((cj & J_UP)   && *curs > 0u) { (*curs)--; redraw=1; }
        if ((cj & J_DOWN) && *curs < mx) { (*curs)++; redraw=1; }
    }

    // A: つかみ中なら確定 / それ以外は再生/一時停止
    if (j & J_A) {
        if (grab != PL_NONE && view == 1u) {
            pl_do_move();
        } else {
            target = (view == 1u && sav.count) ? sav.tracks[pl_sel] : sel;
            if (playing && target == cur_song) {
                gbs_pause();
            } else if (paused && target == cur_song) {
                gbs_resume();
            } else {
                reset_fade_state();
                play_from_sel();
            }
        }
    }

    // LEFT/RIGHT: 曲戻し/曲送り (再生中のみ)
    if (j & J_RIGHT) {
        if (playing || paused) {
            reset_fade_state();
            next_track();
        }
    }
    if (j & J_LEFT) {
        if (playing || paused) {
            reset_fade_state();
            prev_track();
        }
    }

    // B: 停止 (つかみ中はキャンセル)
    if (j & J_B) {
        if (grab != PL_NONE) {
            grab = PL_NONE;
            redraw = 1;
        } else {
            reset_fade_state();
            gbs_stop();
            pl_idx = PL_NONE;
        }
    }

    // START: オプション画面を開く
    if ((j & J_START) && view != 2u) {
        prev_view = view;
        opt_song = (view == 1u && sav.count) ? sav.tracks[pl_sel] : sel;
        view = 2;
        opt_sel = 0;
        redraw = 1;
    }
}

// ── Main ──────────────────────────────────────────────────────────
void main(void) {
    pal[0] = RGB(31,31,31);
    pal[1] = RGB(21,21,21);
    pal[2] = RGB(10,10,10);
    pal[3] = RGB( 0, 0, 0);

    font_init();
    font_load(font_ibm);
    set_bkg_data(UI_TILES_START, UI_TILES_COUNT, ui_tiles);
    set_bkg_data(T_RPT_NONE, 3, rpt_tiles);
    set_bkg_data(JP_TILES_START, JP_TILES_COUNT, jp_font_tiles);

    BANK1();
    sav_load();
    mono_flag = sav.mono;

#if USE_TIMER
    add_TIM(timer_isr);
    add_VBL(vbl_count_isr);
#else
    add_VBL(vbl_play_isr);
#endif

    set_bkg_palette(0, 1, pal);
    SHOW_BKG;
    DISPLAY_ON;

    cur_song = 0u;
    sel      = 0u;
    pl_idx   = PL_NONE;
    grab     = PL_NONE;
    opt_sel  = 0;
    sel_hold_cnt = 0;
    sel_triggered = 0;
    player_sel = PLAYER_ACT_TOGGLE;
    player_prev_view = VIEW_SONGS;
    player_press_action = PLAYER_ACT_NONE;
    player_press_timer = 0;
    player_cursor_timer = PLAYER_CURSOR_TIMEOUT;
    header_scroll_pos = 0;
    header_scroll_wait = 0;
    header_scroll_wrap = 0;
    name_scroll_pos = 0;
    name_scroll_wait = 0;
    name_scroll_wrap = 0;
    prev_sel = sel;
    prev_pl_sel = 0;
    redraw   = 1;
    enable_interrupts();

    play_src = 0;
    if (sav.count) {
        view   = 1;
        play_src = 1;
        pl_idx = 0;
        gbs_start(sav.tracks[0]);
        sync_cursors();
    } else {
        view = 0;
        play_from_sel();
    }

    fade_vol = PL_NONE;
    ANDROID_CMD_ADDR = ANDROID_CMD_NONE;
    ANDROID_CMD_ARG_ADDR = 0u;
    sync_android_status();
    build_fb();
    fb_row = 1;
    redraw = 0;

    while (1) {
        UINT16 limit;
        UINT8 wrap_title;
        UINT8 wrap_author;
        wait_vbl_done();
        flush_fb();
        sync_android_status();
        process_android_command();

        // フェード完了後の待機処理
        if (fade_wait) {
            fade_wait--;
            if (!fade_wait) {
                fade_vol = PL_NONE;
                next_track();
            }
        }
        // 自動曲送り
        if (playing && fade_vol == PL_NONE && !fade_wait && view != 2u) {
            limit = track_time_tbl[sav.track_time[cur_song]];
#if GBS_COMPAT_RB
            if (cur_song == 0u) {
                limit = RED_TRACK1_FIXED_TIMEOUT;
            }
#endif
            if (limit && vbl_cnt >= limit) {
                if (sav.repeat != 1u) {
                    gbs_fade_start();
                }
            }
        }

        // 無音検出 (CGB: PCMレジスタ, DMG: NR52+DACフォールバック)
        if (playing && fade_vol == PL_NONE && !fade_wait) {
            UINT16 slimit = silence_tbl[sav.silence];
            if (slimit) {
                UINT8 s = audio_activity_mask();
                capture_silence_signature();
#if GBS_COMPAT_RB
                RED_SILENCE_TRACE_MASK_ADDR = s;
                RED_SILENCE_TRACE_CNT_ADDR = (UINT8)((silence_stuck_cnt < 255u) ? silence_stuck_cnt : 255u);
#endif
                if (s == 0u) {
                    silence_cnt++;
                    silence_stuck_cnt = 0u;
                    if (silence_cnt >= slimit) {
                        silence_cnt = 0;
                        gbs_stop();
                        fade_wait = FADE_GAP;
                    }
                } else {
#if GBS_COMPAT_RB
                    if (red_track1_stuck_silence_candidate()) {
                        silence_stuck_cnt++;
                        if (silence_stuck_cnt >= RED_TRACK1_END_TIMEOUT) {
                            silence_cnt = 0;
                            silence_stuck_cnt = 0;
                            gbs_stop();
                            fade_wait = FADE_GAP;
                        }
                    } else
#endif
                    if (_cpu == CGB_TYPE &&
                        silence_pcm12_cur == silence_pcm12_prev &&
                        silence_pcm34_cur == silence_pcm34_prev &&
                        silence_signature_same()) {
                        silence_stuck_cnt++;
                        if (silence_stuck_cnt >= slimit) {
                            silence_cnt = 0;
                            silence_stuck_cnt = 0;
                            gbs_stop();
                            fade_wait = FADE_GAP;
                        }
                    } else {
                        silence_stuck_cnt = 0;
                    }
                    silence_cnt = 0;
                }
                silence_pcm12_prev = silence_pcm12_cur;
                silence_pcm34_prev = silence_pcm34_cur;
                silence_signature_commit();
            }
        }

        // スクロール更新 (SCROLL_SPEEDフレームごと)
        scroll_cnt++;
        if (scroll_cnt >= SCROLL_SPEED) {
            scroll_cnt = 0;
            scroll_pos++;
            wrap_title = enc_scroll_wrap(display_title(), 18u);
            wrap_author = enc_scroll_wrap(display_author(), 18u);
            header_scroll_wrap = (wrap_title > wrap_author) ? wrap_title : wrap_author;
            if (header_scroll_wrap) {
                if (header_scroll_wait < HEADER_SCROLL_DELAY) {
                    header_scroll_wait += SCROLL_SPEED;
                } else {
                    header_scroll_pos++;
                    scroll_dirty |= 1u; // タイトル/作曲者更新
                    if (header_scroll_pos >= header_scroll_wrap) {
                        header_scroll_pos = 0;
                        header_scroll_wait = 0;
                    }
                }
            } else if (header_scroll_pos || header_scroll_wait) {
                header_scroll_pos = 0;
                header_scroll_wait = 0;
                scroll_dirty |= 1u;
            }
            // 曲名スクロールは待機後に開始、一周したら再待機
            if (name_scroll_wait < NAME_SCROLL_DELAY) {
                name_scroll_wait += SCROLL_SPEED;
            } else {
                name_scroll_pos++;
                scroll_dirty |= 2u; // 曲名更新
                if (name_scroll_wrap && name_scroll_pos >= name_scroll_wrap) {
                    name_scroll_pos = 0;
                    name_scroll_wait = 0;
                }
            }
        }
        // カーソル移動・曲変更時に曲名スクロールをリセット
        if (sel != prev_sel || pl_sel != prev_pl_sel) {
            name_scroll_pos = 0;
            name_scroll_wait = 0;
            name_scroll_wrap = 0;
            scroll_dirty |= 2u;
            prev_sel = sel;
            prev_pl_sel = pl_sel;
        }
        update_header();

        if (player_press_timer) {
            player_press_timer--;
            if (!player_press_timer) {
                player_press_action = PLAYER_ACT_NONE;
                redraw = 1;
            }
        }
        if (view == VIEW_PLAYER && player_cursor_timer) {
            player_cursor_timer--;
            if (!player_cursor_timer) {
                redraw = 1;
            }
        }

        handle_input();
        if (redraw) {
            build_fb();
            fb_row = 1;
            redraw = 0;
        }
    }
}
