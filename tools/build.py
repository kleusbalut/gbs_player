#!/usr/bin/env python3
"""
tools/build.py  --  GBS Player build helper
Usage:
  python tools/build.py header  <file.gbs>          # Generate src/player/gbs_info.h
  python tools/build.py merge   <player.gb> <file.gbs> <out.gbc>  # Merge ROM + GBS
  python tools/build.py metadata <file.gbs> <out.json>            # Export Android metadata
  make GBDK=/c/dev/gbdk GBS=<file.gb|file.gbc>      # Auto-wrap supported GB/GBC ROMs
"""
import json, sys, os
import os.path
from gbs_common import (
    utf8_to_custom, parse_gbs_header, load_song_names,
)

# ── GBS header layout (all offsets from file start) ───────────────────────────
# 0x00  3  "GBS"
# 0x03  1  version (1)
# 0x04  1  num_songs
# 0x05  1  first_song (1-based)
# 0x06  2  load_addr  (LE)
# 0x08  2  init_addr  (LE)
# 0x0A  2  play_addr  (LE)
# 0x0C  2  stack_ptr  (LE)
# 0x0E  1  timer_mod  (TMA)
# 0x0F  1  timer_ctl  (TAC)
# 0x10 32  title  (UTF-8 / ASCII, zero-padded)
# 0x30 32  author
# 0x50 32  copyright
# 0x70 …  code/data (placed at load_addr in ROM bank 1)

# ── Custom encoding for Japanese characters ──────────────────────────────────
# Dakuten/handakuten are separate characters (each occupies 1 byte/tile).
# e.g. "ガ" → [カ, ゛] = [0xB5, 0x01] (2 bytes)
#
# 0x00      : null terminator
# 0x01      : ゛ (dakuten, U+3099)
# 0x02      : ゜ (handakuten, U+309A)
# 0x03      : ー (long vowel)
# 0x04-0x0C : Small hira (9: ぁぃぅぇぉゃゅょっ)
# 0x0D-0x15 : Small kata (9: ァィゥェォャュョッ)
# 0x20-0x7E : ASCII
# 0x80-0xAD : Base hiragana (46: あ-ん)
# 0xB0-0xDD : Base katakana (46: ア-ン)

HIRAGANA = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
KATAKANA = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
SMALL_HIRA = "ぁぃぅぇぉゃゅょっ"
SMALL_KATA = "ァィゥェォャュョッ"

# Decomposition tables: composed char → (base char, mark)
# Dakuten: voiced consonants → base + ゛
DAKUTEN_DECOMP = {}
for _composed, _base in [
    ('が','か'),('ぎ','き'),('ぐ','く'),('げ','け'),('ご','こ'),
    ('ざ','さ'),('じ','し'),('ず','す'),('ぜ','せ'),('ぞ','そ'),
    ('だ','た'),('ぢ','ち'),('づ','つ'),('で','て'),('ど','と'),
    ('ば','は'),('び','ひ'),('ぶ','ふ'),('べ','へ'),('ぼ','ほ'),
    ('ゔ','う'),
    ('ガ','カ'),('ギ','キ'),('グ','ク'),('ゲ','ケ'),('ゴ','コ'),
    ('ザ','サ'),('ジ','シ'),('ズ','ス'),('ゼ','セ'),('ゾ','ソ'),
    ('ダ','タ'),('ヂ','チ'),('ヅ','ツ'),('デ','テ'),('ド','ト'),
    ('バ','ハ'),('ビ','ヒ'),('ブ','フ'),('ベ','ヘ'),('ボ','ホ'),
    ('ヴ','ウ'),
]:
    DAKUTEN_DECOMP[_composed] = _base

# Handakuten: p-row → base + ゜
HANDAKUTEN_DECOMP = {}
for _composed, _base in [
    ('ぱ','は'),('ぴ','ひ'),('ぷ','ふ'),('ぺ','へ'),('ぽ','ほ'),
    ('パ','ハ'),('ピ','ヒ'),('プ','フ'),('ペ','ヘ'),('ポ','ホ'),
]:
    HANDAKUTEN_DECOMP[_composed] = _base

def utf8_to_custom(text, max_len=31):
    """Convert UTF-8 text to custom 1-byte encoding. Returns list of ints.
    Dakuten/handakuten characters are decomposed into base + mark (2 bytes).
    """
    result = []
    for ch in text:
        if len(result) >= max_len:
            break
        cp = ord(ch)
        if 0x20 <= cp <= 0x7E:
            result.append(cp)
        elif ch in HANDAKUTEN_DECOMP:
            base = HANDAKUTEN_DECOMP[ch]
            if base in HIRAGANA:
                result.append(0x80 + HIRAGANA.index(base))
            elif base in KATAKANA:
                result.append(0xB0 + KATAKANA.index(base))
            if len(result) < max_len:
                result.append(0x02)  # ゜
        elif ch in DAKUTEN_DECOMP:
            base = DAKUTEN_DECOMP[ch]
            if base in HIRAGANA:
                result.append(0x80 + HIRAGANA.index(base))
            elif base in KATAKANA:
                result.append(0xB0 + KATAKANA.index(base))
            if len(result) < max_len:
                result.append(0x01)  # ゛
        elif ch == '\u3099' or ch == '\u309B' or ch == '\uFF9E':
            result.append(0x01)  # ゛
        elif ch == '\u309A' or ch == '\u309C' or ch == '\uFF9F':
            result.append(0x02)  # ゜
        elif ch == 'ー' or ch == '\uFF70':
            result.append(0x03)
        elif ch in SMALL_HIRA:
            result.append(0x04 + SMALL_HIRA.index(ch))
        elif ch in SMALL_KATA:
            result.append(0x0D + SMALL_KATA.index(ch))
        elif ch in HIRAGANA:
            result.append(0x80 + HIRAGANA.index(ch))
        elif ch in KATAKANA:
            result.append(0xB0 + KATAKANA.index(ch))
        # Skip unsupported characters
    # Pad with zeros to max_len+1 (null terminated, fixed size)
    while len(result) < max_len + 1:
        result.append(0)
    return result[:max_len + 1]

TRACK_TIME_LABELS = ["90s", "OFF", "30s", "1m", "2m", "3m", "5m"]

COMPAT_NONE = ""
COMPAT_RB_A = "rb_a"
COMPAT_RB_B = "rb_b"
COMPAT_RB_UNSUPPORTED = "rb_unsupported"
COMPAT_GS_A = "gs_a"
COMPAT_GS_B = "gs_b"
COMPAT_C = "c"

TITLE_PREFIXES = (
    (COMPAT_RB_A, bytes.fromhex("504F4B454D4F4E20524544")),
    (COMPAT_RB_B, bytes.fromhex("504F4B454D4F4E20424C5545")),
    (COMPAT_RB_UNSUPPORTED, bytes.fromhex("504F4B454D4F4E2059454C4C4F57")),
    (COMPAT_GS_A, bytes.fromhex("504F4B454D4F4E5F474C44")),
    (COMPAT_GS_B, bytes.fromhex("504F4B454D4F4E5F534C56")),
    (COMPAT_C, bytes.fromhex("504F4B454D4F4E5F4352595354414C")),
)

def _is_rb_family(compat):
    return compat in (COMPAT_RB_A, COMPAT_RB_B)

def _is_unsupported_rb_variant(compat):
    return compat == COMPAT_RB_UNSUPPORTED

def _is_gs_family(compat):
    return compat in (COMPAT_GS_A, COMPAT_GS_B)

def _is_c_family(compat):
    return compat == COMPAT_C

def _detect_compat(title_bytes, code):
    title_upper = title_bytes.split(b"\x00", 1)[0].upper()
    for compat, prefix in TITLE_PREFIXES:
        if title_upper.startswith(prefix):
            return compat
    if code in ("AAUJ", "AAUE"):
        return COMPAT_GS_A
    if code in ("AAXJ", "AAXE"):
        return COMPAT_GS_B
    if code == "BYTE":
        return COMPAT_C
    return COMPAT_NONE

def _detect_compat_from_title(title):
    raw = title.encode("ascii", errors="ignore")
    return _detect_compat(raw, "")

def _detect_compat_from_gbs_path(path):
    name = os.path.basename(path).upper()
    for part in name.replace(".", "-").split("-"):
        compat = _detect_compat(b"", part)
        if compat:
            return compat
    return COMPAT_NONE

def _rom_ascii(raw, start, size):
    return raw[start:start + size].split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()

def _parse_gf_rom_header(path, raw):
    """Return GBS header values for supported GB/GBC ROM audio drivers.

    The player still executes the original sound engine; this function only
    supplies the GBS wrapper metadata and preserves ROM bank numbering by
    placing bank 1+ contiguously after the Bank 0 tail.
    """
    if len(raw) < 0x150:
        raise ValueError(f"{path} is too small to be a GB/GBC ROM")

    title_bytes = raw[0x134:0x134 + 16]
    code = _rom_ascii(raw, 0x13F, 4)
    compat = _detect_compat(title_bytes, code)
    generic_meta = {
        "title": "Wrapped GB/GBC ROM",
        "author": "Unknown Author",
        "copyright": "",
        "compat": compat,
    }

    if compat == COMPAT_RB_A:
        return {
            "num_songs": 51, "first_song": 1,
            "load_addr": 0x3F56, "init_addr": 0x3F56, "play_addr": 0x3F7E,
            "stack_ptr": 0xDFFF, "timer_mod": 0x00, "timer_ctl": 0x00,
            **generic_meta,
        }
    if compat == COMPAT_RB_B:
        return {
            "num_songs": 51, "first_song": 1,
            "load_addr": 0x3F56, "init_addr": 0x3F56, "play_addr": 0x3F7E,
            "stack_ptr": 0xDFFF, "timer_mod": 0x00, "timer_ctl": 0x00,
            **generic_meta,
        }
    if compat == COMPAT_RB_UNSUPPORTED:
        return {
            "num_songs": 51, "first_song": 1,
            "load_addr": 0x3F56, "init_addr": 0x3F56, "play_addr": 0x3F7E,
            "stack_ptr": 0xDFFF, "timer_mod": 0x00, "timer_ctl": 0x00,
            **generic_meta,
        }
    if compat == COMPAT_GS_A:
        return {
            "num_songs": 92, "first_song": 82,
            "load_addr": 0x3D72, "init_addr": 0x3D72, "play_addr": 0x405C,
            "stack_ptr": 0xDFFF, "timer_mod": 0x00, "timer_ctl": 0x80,
            **generic_meta,
        }
    if compat == COMPAT_GS_B:
        return {
            "num_songs": 92, "first_song": 82,
            "load_addr": 0x3D72, "init_addr": 0x3D72, "play_addr": 0x405C,
            "stack_ptr": 0xDFFF, "timer_mod": 0x00, "timer_ctl": 0x80,
            **generic_meta,
        }
    if compat == COMPAT_C:
        return {
            "num_songs": 102, "first_song": 1,
            "load_addr": 0x3B70, "init_addr": 0x3B70, "play_addr": 0x405C,
            "stack_ptr": 0xC0FE, "timer_mod": 0x00, "timer_ctl": 0x00,
            **generic_meta,
        }

    raise ValueError(
        f"{path} is not a supported GB/GBC ROM profile (code='{code}')"
    )

RB_FAMILY_DISPATCH_TABLE = bytes([
    0xDC, 0x01, 0xC3, 0x03, 0xEF, 0x01, 0xBA, 0x01,
    0xBD, 0x01, 0xC0, 0x01, 0xC3, 0x01, 0xC7, 0x01,
    0xCA, 0x01, 0xCD, 0x01, 0xD0, 0x01, 0xD4, 0x01,
    0xD8, 0x01, 0xDB, 0x01, 0xDE, 0x01, 0xE1, 0x01,
    0xE5, 0x01, 0xEB, 0x01, 0xF3, 0x01, 0xF7, 0x01,
    0xFB, 0x01, 0xEA, 0x02, 0xED, 0x02, 0xF0, 0x02,
    0xF3, 0x02, 0xF6, 0x02, 0xF9, 0x02, 0xFC, 0x02,
    0xC7, 0x03, 0xCA, 0x03, 0xCD, 0x03, 0xD0, 0x03,
    0xD2, 0x03, 0xD6, 0x03, 0xD9, 0x03, 0xDC, 0x03,
    0xE0, 0x03, 0xE4, 0x03, 0xE8, 0x03, 0xEC, 0x03,
    0xF0, 0x03, 0xF3, 0x03, 0xF6, 0x03, 0xF9, 0x03,
    0xFC, 0x03, 0xE8, 0x01, 0x86, 0x02, 0x9A, 0x02,
    0x86, 0x03, 0x89, 0x03, 0x91, 0x03, 0x94, 0x03,
])

RB_A_DIRECT_DISPATCH_OVERRIDES = {
    # This profile needs the intro in AUDIO_3 and has one duplicate AUDIO_3
    # entry around the late-game songs. Keep the verified middle range
    # unchanged, then remove the duplicate and shift the remaining entries.
    0:  (0xDC, 0x03),
    35: (0xE0, 0x03),
    36: (0xE4, 0x03),
    37: (0xE8, 0x03),
    38: (0xEC, 0x03),
    39: (0xF0, 0x03),
    40: (0xF3, 0x03),
    41: (0xF6, 0x03),
    42: (0xF9, 0x03),
    43: (0xFC, 0x03),
    44: (0xE8, 0x01),
    45: (0x86, 0x02),
    46: (0x9A, 0x02),
    47: (0x86, 0x03),
    48: (0x89, 0x03),
    49: (0x91, 0x03),
    50: (0x94, 0x03),
}

RB_B_DIRECT_DISPATCH_OVERRIDES = {
    # This profile also has the intro in AUDIO_3 and a duplicate late entry,
    # so drop the duplicate and shift later entries.
    0: (0xDC, 0x03),
    35: (0xE0, 0x03),
    36: (0xE4, 0x03),
    37: (0xE8, 0x03),
    38: (0xEC, 0x03),
    39: (0xF0, 0x03),
    40: (0xF3, 0x03),
    41: (0xF6, 0x03),
    42: (0xF9, 0x03),
    43: (0xFC, 0x03),
    44: (0xE8, 0x01),
    45: (0x86, 0x02),
    46: (0x9A, 0x02),
    47: (0x86, 0x03),
    48: (0x89, 0x03),
    49: (0x91, 0x03),
    50: (0x94, 0x03),
}

def _find_in_bank(raw, bank_arg, pattern, label):
    start = bank_arg * 0x4000
    bank = raw[start:start + 0x4000]
    pos = bank.find(pattern)
    if pos < 0:
        raise ValueError(f"could not locate {label} in ROM bank 0x{bank_arg:02X}")
    return 0x4000 + pos

def _build_rb_family_bank0_payload(raw, compat):
    """Build the Bank 0 GBS stub for this older audio-driver family.

    The native ROM's Bank 0 is replaced by the player, so the original game
    entrypoint is not available. The GBS payload therefore needs a small
    dispatcher in the Bank 0 tail, equivalent to the one in the known GBS
    extraction, but with direct ROM bank numbers and per-ROM routine addresses.
    """
    load = 0x3F56
    init_addr = 0x3F56
    play_addr = 0x3F7E
    table_addr = 0x3F9A
    bank_args = (0x02, 0x08, 0x1F)

    init_pattern = bytes.fromhex("ea01c0feff")
    play_pattern = bytes.fromhex("0e0006002126c009")
    init_addrs = [_find_in_bank(raw, b, init_pattern, "music init") for b in bank_args]
    play_addrs = [_find_in_bank(raw, b, play_pattern, "music play") for b in bank_args]

    def word(v):
        return [v & 0xFF, (v >> 8) & 0xFF]

    payload = bytearray(b"\xC9" * (0x4000 - load))
    init = bytearray([
        0x21, *word(table_addr),      # ld hl, dispatch table
        0x87,                         # add a, a
        0x85,                         # add a, l
        0x6F,                         # ld l, a
        0x2A,                         # ld a, (hl+)
        0x47,                         # ld b, a
        0x7E,                         # ld a, (hl)
        0xEA, 0x00, 0x20,             # ld ($2000), a
        0xEA, 0xEF, 0xC0,             # ld ($C0EF), a
        0xFE, bank_args[0],           # cp bank 1
        0x20, 0x06,                   # jr nz, .bank2
        0x78,                         # ld a, b
        0xCD, *word(init_addrs[0]),    # call init1
        0x18, 0x0E,                   # jr .done
        0xFE, bank_args[1],           # .bank2: cp bank 2
        0x20, 0x06,                   # jr nz, .bank3
        0x78,                         # ld a, b
        0xCD, *word(init_addrs[1]),    # call init2
        0x18, 0x04,                   # jr .done
        0x78,                         # .bank3: ld a, b
        0xCD, *word(init_addrs[2]),    # call init3
        0xC9,                         # .done: ret
    ])
    play = bytearray([
        0xFA, 0xEF, 0xC0,             # ld a, ($C0EF)
        0xFE, bank_args[0],           # cp bank 1
        0x20, 0x05,                   # jr nz, .bank2
        0xCD, *word(play_addrs[0]),    # call play1
        0x18, 0x0F,                   # jr .done
        0xFE, bank_args[1],           # .bank2: cp bank 2
        0x20, 0x08,                   # jr nz, .bank3
        0xCD, *word(play_addrs[1]),    # call play2
        0x18, 0x06,                   # jr .done
        0x00, 0x00, 0x00,             # keep bank3 target at 0x3F96
        0xCD, *word(play_addrs[2]),    # .bank3: call play3
        0xC9,                         # .done: ret
    ])

    dispatch = bytearray()
    bank_map = {0x01: bank_args[0], 0x02: bank_args[1], 0x03: bank_args[2]}
    max_dispatch_bytes = 0x4000 - table_addr
    for i in range(0, min(len(RB_FAMILY_DISPATCH_TABLE), max_dispatch_bytes), 2):
        song_index = i // 2
        song_id = RB_FAMILY_DISPATCH_TABLE[i]
        song_bank = RB_FAMILY_DISPATCH_TABLE[i + 1]
        if compat == COMPAT_RB_A and song_index in RB_A_DIRECT_DISPATCH_OVERRIDES:
            song_id, song_bank = RB_A_DIRECT_DISPATCH_OVERRIDES[song_index]
        elif compat == COMPAT_RB_B and song_index in RB_B_DIRECT_DISPATCH_OVERRIDES:
            song_id, song_bank = RB_B_DIRECT_DISPATCH_OVERRIDES[song_index]
        dispatch.append(song_id)
        dispatch.append(bank_map[song_bank])

    payload[init_addr - load:init_addr - load + len(init)] = init
    payload[play_addr - load:play_addr - load + len(play)] = play
    payload[table_addr - load:table_addr - load + len(dispatch)] = dispatch
    return payload

def _parse_rom_as_gbs(path, raw):
    h = _parse_gf_rom_header(path, raw)
    load = h["load_addr"]
    if not (0x0000 <= load < 0x4000):
        raise ValueError(f"unsupported ROM load address 0x{load:04X}")
    compat = h.get("compat", COMPAT_NONE)
    if _is_unsupported_rb_variant(compat):
        raise ValueError(
            "This GB/GBC ROM profile is recognized but not supported yet; "
            "its audio bank layout differs from the supported profiles"
        )
    if _is_rb_family(compat):
        h["payload"] = bytes(_build_rb_family_bank0_payload(raw, compat)) + raw[0x4000:]
    else:
        h["payload"] = raw[load:0x4000] + raw[0x4000:]
    h["source_rom"] = os.path.basename(path)
    print(
        f"[build.py] Wrapped GB/GBC ROM as GBS "
        f"({h['num_songs']} songs, load=0x{load:04X}, profile={compat or 'generic'})"
    )
    return h

def parse_song_list_line(line):
    """Parse a song-list line.

    Supported formats:
      - legacy: <name>
      - new:    <name>\t<time>
    """
    text = line.rstrip("\r\n")
    stripped = text.strip()
    if not stripped:
        return "", None
    parts = text.split("\t", 1)
    if len(parts) == 2:
        time_label = parts[1].strip()
        if time_label in TRACK_TIME_LABELS:
            return parts[0].strip(), TRACK_TIME_LABELS.index(time_label)
    return text.strip(), None

def load_song_lists(gbs_path, num_songs):
    """Load metadata, song names, and optional track times from companion file.

    Returns (names, times, metadata, source_path).
    """
    base = os.path.splitext(gbs_path)[0]
    candidates = [
        base + ".names.txt",
        os.path.join(os.path.dirname(gbs_path) or ".", "songnames.txt"),
    ]
    names = [""] * num_songs
    times = [None] * num_songs
    metadata = {}
    for path in candidates:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            song_index = 0
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    key_value = stripped[1:].split(":", 1)
                    if len(key_value) == 2:
                        key = key_value[0].strip().lower()
                        value = key_value[1].strip()
                        if key in ("title", "author", "copyright"):
                            metadata[key] = value
                            continue
                if song_index >= num_songs:
                    break
                names[song_index], times[song_index] = parse_song_list_line(line)
                song_index += 1
            print(f"[build.py] Song list loaded from: {path} ({min(song_index, num_songs)} entries)")
            return names, times, metadata, path
    return names, times, metadata, None

def apply_song_list_metadata(g, metadata):
    for key in ("title", "author", "copyright"):
        value = metadata.get(key)
        if value:
            g[key] = value

def parse_gbs(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:3] == b"GBS":
        try:
            h = parse_gbs_header(path)
        except ValueError as e:
            sys.exit(f"ERROR: {e}")
        h["payload"] = raw[0x70:]
        h["compat"] = (
            _detect_compat_from_title(h.get("title", "")) or
            _detect_compat_from_gbs_path(path)
        )
        return h
    try:
        return _parse_rom_as_gbs(path, raw)
    except ValueError as e:
        sys.exit(f"ERROR: {e}")
def cmd_metadata(gbs_path, out_path):
    g = parse_gbs(gbs_path)
    names, times, metadata, names_path = load_song_lists(gbs_path, g["num_songs"])
    apply_song_list_metadata(g, metadata)
    songs = []
    for i in range(g["num_songs"]):
        songs.append({
            "index": i,
            "number": i + 1,
            "name": names[i] or f"Track {i + 1}",
            "trackTime": TRACK_TIME_LABELS[times[i]] if times[i] is not None else TRACK_TIME_LABELS[0],
        })

    payload = {
        "title": g["title"] or "Unknown Title",
        "author": g["author"] or "Unknown Author",
        "copyright": g["copyright"] or "",
        "numSongs": g["num_songs"],
        "firstSong": g["first_song"],
        "sourceGbs": os.path.basename(gbs_path),
        "songNamesSource": os.path.basename(names_path) if names_path else None,
        "songs": songs,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[build.py] metadata written: {out_path}")

# ── GBS payload scanner ───────────────────────────────────────────────────────
def _scan_rst(payload, rst_vec):
    """Return True if RST $XX (opcode = rst_vec | 0xC7) appears in payload."""
    opcode = 0xC7 | rst_vec
    return bytes([opcode]) in payload

def _scan_call(payload, addr):
    """Return True if CALL addr (0xCD lo hi) appears anywhere in payload."""
    lo = addr & 0xFF
    hi = (addr >> 8) & 0xFF
    needle = bytes([0xCD, lo, hi])
    return needle in payload

def _scan_addr_access(payload, addr):
    """Return True if LD A,(addr) [0xFA] or LD (addr),A [0xEA] appears in payload."""
    lo = addr & 0xFF
    hi = (addr >> 8) & 0xFF
    for opcode in (0xFA, 0xEA):
        if bytes([opcode, lo, hi]) in payload:
            return True
    return False

def _addr_to_payload_off(load, addr):
    """Map a ROM address to a payload offset, or return None if unmappable."""
    if load <= addr < 0x4000:
        return addr - load
    if 0x4000 <= addr < 0x8000:
        return (0x4000 - load) + (addr - 0x4000)
    return None

def _looks_like_subroutine(payload, load, addr):
    """Heuristic: addr points at mapped code that reaches RET quickly."""
    off = _addr_to_payload_off(load, addr)
    if off is None or off >= len(payload):
        return False
    window = payload[off:min(off + 32, len(payload))]
    if not window:
        return False
    if window[0] in (0xD3, 0xDB, 0xDD, 0xE3, 0xE4, 0xEB, 0xEC, 0xED, 0xF4, 0xFC, 0xFD):
        return False
    return 0xC9 in window or 0xD9 in window

def _find_call_hl_helpers(payload, load):
    """Detect low-address helpers that behave like a CALL-HL trampoline.

    Pattern:
      LD HL, <mapped payload code>
      CALL <low address>

    A helper like this can be reproduced safely with a one-byte `JP HL`
    stub placed at the low address in the Bank 0 gap.
    """
    hits = {}
    for i in range(3, len(payload) - 2):
        if payload[i] != 0xCD:
            continue
        target = payload[i + 1] | (payload[i + 2] << 8)
        if target >= load:
            continue
        if payload[i - 3] != 0x21:
            continue
        hl_addr = payload[i - 2] | (payload[i - 1] << 8)
        if not _looks_like_subroutine(payload, load, hl_addr):
            continue
        info = hits.setdefault(target, {"count": 0, "hl_addrs": set()})
        info["count"] += 1
        info["hl_addrs"].add(hl_addr)

    out = []
    for target, info in sorted(hits.items()):
        if info["count"] >= 2 or len(info["hl_addrs"]) >= 2:
            out.append((target, info))
    return out

def cmd_header(gbs_path):
    g = parse_gbs(gbs_path)
    out_path = os.path.join(os.path.dirname(__file__), "..", "src", "player", "gbs_info.h")
    stack_safe = g["stack_ptr"]

    # Load song names
    names, times, metadata, names_path = load_song_lists(gbs_path, g["num_songs"])
    apply_song_list_metadata(g, metadata)
    title  = g["title"].replace('"', '\\"')  or "Unknown Title"
    author = g["author"].replace('"', '\\"') or "Unknown Author"
    copy   = g["copyright"].replace('"', '\\"') or "(c) Unknown"
    title_enc = utf8_to_custom(g["title"] or "Unknown Title", 31)
    author_enc = utf8_to_custom(g["author"] or "Unknown Author", 31)
    has_names = any(n != "" for n in names)
    has_track_times = any(t is not None for t in times)
    if has_names:
        embed_mode = os.environ.get("GBS_EMBED_NAMES", "on").strip().lower()
        if embed_mode in ("0", "false", "no", "off", "disable", "disabled"):
            print(f"[build.py] Song-name embedding disabled; ignoring {names_path}")
            names = [""] * g["num_songs"]
            has_names = False

    compat = g.get("compat", COMPAT_NONE)
    rb_family = _is_rb_family(compat)
    gs_family = _is_gs_family(compat)
    c_family = _is_c_family(compat)
    source_is_rom = 1 if g.get("source_rom") else 0
    has_ceea_est  = 1 if gs_family or _scan_addr_access(g["payload"], 0xCEEA) else 0
    silence_grace = 480 if gs_family else 0
    vol_shadow_addr = 0
    pan_shadow_addr = 0
    if gs_family:
        vol_shadow_addr = 0xC19A
        pan_shadow_addr = 0xC19B
    elif c_family:
        vol_shadow_addr = 0xC29A
        pan_shadow_addr = 0xC29B

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("// Auto-generated by tools/build.py  --  DO NOT EDIT\n")
        f.write(f'// Source: {os.path.basename(gbs_path)}\n')
        f.write("#ifndef GBS_INFO_H\n#define GBS_INFO_H\n\n")
        f.write(f'#define GBS_TITLE      "{title[:18]}"\n')
        f.write(f'#define GBS_AUTHOR     "{author[:18]}"\n')
        f.write(f'#define GBS_COPYRIGHT  "{copy[:18]}"\n\n')
        f.write("#define GBS_TITLE_ENC_DEFINED 1\n")
        f.write("static const UINT8 GBS_TITLE_ENC[32] = {" + ",".join(str(v) for v in title_enc) + "};\n")
        f.write("static const UINT8 GBS_AUTHOR_ENC[32] = {" + ",".join(str(v) for v in author_enc) + "};\n\n")
        # Compatibility toggles used by main.c/runtime.
        f.write(f'#define GBS_COMPAT_GS {1 if gs_family else 0}\n')
        f.write(f'#define GBS_COMPAT_RB {1 if rb_family else 0}\n\n')
        f.write(f'#define GBS_SOURCE_IS_ROM {source_is_rom}\n\n')
        # GBS_HAS_CEEA_FLAG: GBS engine uses CEEA ($CEEA) for VBlank sync.
        # The VBL ISR must clear CEEA before calling gbs_play_trampoline so that
        # any DelayFrame stub inside the GBS engine can unblock via HALT.
        f.write(f'#define GBS_HAS_CEEA_FLAG {has_ceea_est}\n')
        # GBS_SILENCE_GRACE_FRAMES: frames to suppress silence detection after gbs_start().
        # Use >0 for GBS engines that take time to produce sound after INIT.
        f.write(f'#define GBS_SILENCE_GRACE_FRAMES {silence_grace}\n\n')
        f.write(f'#define GBS_VOL_SHADOW_ADDR 0x{vol_shadow_addr:04X}\n')
        f.write(f'#define GBS_PAN_SHADOW_ADDR 0x{pan_shadow_addr:04X}\n\n')
        f.write(f'#define GBS_NUM_SONGS   {g["num_songs"]}\n')
        f.write(f'#define GBS_FIRST_SONG  {g["first_song"]}\n\n')
        f.write(f'#define GBS_INIT_ADDR   0x{g["init_addr"]:04X}\n')
        f.write(f'#define GBS_PLAY_ADDR   0x{g["play_addr"]:04X}\n')
        f.write(f'#define GBS_STACK_PTR   0x{g["stack_ptr"]:04X}\n\n')
        f.write(f'#define GBS_STACK_SAFE  0x{stack_safe:04X}\n\n')
        f.write(f'#define GBS_TIMER_CTL   0x{g["timer_ctl"]:02X}\n')
        f.write(f'#define GBS_TIMER_MOD   0x{g["timer_mod"]:02X}\n\n')

        # Song names array (sparse blob, only non-empty names are embedded)
        f.write(f'#define GBS_SONG_NAMES_DEFINED {1 if has_names else 0}\n')
        f.write(f'#define GBS_TRACK_TIMES_DEFINED {1 if has_track_times else 0}\n\n')
        if has_names:
            sparse = []
            total = 0
            for i, name in enumerate(names):
                if name:
                    encoded = utf8_to_custom(name, 31)
                    sparse.append((i, name, encoded, total))
                    total += len(encoded)

            f.write(f'#define GBS_ROM_NAME_COUNT {len(sparse)}\n\n')
            f.write(f'static const UINT8 gbs_song_name_ids[{len(sparse)}] = {{\n')
            f.write("    " + ",".join(str(i) for i, _, _, _ in sparse) + '\n')
            f.write('};\n\n')

            f.write(f'static const UINT16 gbs_song_name_offsets[{len(sparse)}] = {{\n')
            f.write("    " + ",".join(f"0x{off:04X}" for _, _, _, off in sparse) + '\n')
            f.write('};\n\n')

            f.write(f'static const UINT8 gbs_song_name_data[{total}] = {{\n')
            for _, name, encoded, _ in sparse:
                hex_str = ",".join(f"0x{b:02X}" for b in encoded)
                f.write(f'    {hex_str}, // {name}\n')
            f.write('};\n\n')

        if has_track_times:
            sparse_times = []
            for i, time_idx in enumerate(times):
                if time_idx is not None:
                    sparse_times.append((i, time_idx))
            f.write(f'#define GBS_ROM_TRACK_TIME_COUNT {len(sparse_times)}\n\n')
            f.write(f'static const UINT8 gbs_track_time_ids[{len(sparse_times)}] = {{\n')
            f.write("    " + ",".join(str(i) for i, _ in sparse_times) + '\n')
            f.write('};\n\n')
            f.write(f'static const UINT8 gbs_track_time_values[{len(sparse_times)}] = {{\n')
            f.write("    " + ",".join(str(v) for _, v in sparse_times) + '\n')
            f.write('};\n\n')

        f.write("#endif // GBS_INFO_H\n")
    print(f"[build.py] gbs_info.h written: {g['num_songs']} songs, "
          f"load=0x{g['load_addr']:04X}, init=0x{g['init_addr']:04X}, "
          f"play=0x{g['play_addr']:04X}"
          f"{', with song names' if has_names else ''}"
          f"{', with track times' if has_track_times else ''}")


# ── ROM patch helpers ─────────────────────────────────────────────────────────

def write_rom(rom, addr, data):
    """Write bytes from data into rom starting at addr."""
    for i, b in enumerate(data):
        rom[addr + i] = b

def patch_calls(rom, start, opcode, lo, hi, new_addr):
    """Scan rom[start:] for opcode+lo+hi and redirect lo+hi to new_addr."""
    count = 0
    for i in range(start, len(rom) - 2):
        if rom[i] == opcode and rom[i + 1] == lo and rom[i + 2] == hi:
            rom[i + 1] = new_addr & 0xFF
            rom[i + 2] = (new_addr >> 8) & 0xFF
            count += 1
    return count


def cmd_merge(player_path, gbs_path, out_path):
    import math
    g = parse_gbs(gbs_path)
    load    = g["load_addr"]
    payload = bytearray(g["payload"])
    compat = g.get("compat", COMPAT_NONE)
    rb_family = _is_rb_family(compat)
    gs_family = _is_gs_family(compat)
    c_family = _is_c_family(compat)

    with open(player_path, "rb") as f:
        player = bytearray(f.read())

    # Bank 0: take first 16 KB from the compiled player ROM
    if len(player) > 0x4000:
        player = player[:0x4000]
    player.extend(b"\xC9" * (0x4000 - len(player)))  # RET-fill unused area

    # GBDK/SDCC may leave overlapping absolute writes around interrupt vectors.
    # Normalize the VBlank slot and turn every other unused interrupt vector
    # into a bare RETI so stray interrupts do not cause indefinite loops.
    if player[0x40] == 0xC3:
        player[0x43:0x48] = b"\x00" * 5
    for vec in (0x48, 0x50, 0x58, 0x60):
        player[vec] = 0xD9  # RETI
        player[vec + 1:vec + 8] = b"\x00" * 7

    banks = [player]   # banks[0] = Bank 0

    if load >= 0x4000:
        # Entire payload goes into banks 1, 2, …
        remaining = payload
    else:
        # Payload starts part-way through Bank 0 at offset `load`
        b0_payload_len = 0x4000 - load   # bytes that fit in Bank 0
        # Safety: makebin fills unused ROM with 0xFF.
        # Any non-0xFF byte in [load, 0x4000) means player code reaches there.
        for i in range(load, 0x4000):
            if banks[0][i] != 0xFF:
                sys.exit(
                    f"ERROR: player code has data at ROM 0x{i:04X}, "
                    f"which conflicts with GBS load_addr=0x{load:04X}. "
                    f"Player binary is too large.")
        banks[0][load:0x4000] = payload[:b0_payload_len]
        remaining = payload[b0_payload_len:]

    # Distribute remaining payload into banks 1, 2, …
    while remaining:
        chunk = bytearray(remaining[:0x4000])
        chunk.extend(b"\xC9" * (0x4000 - len(chunk)))  # RET-fill partial bank
        banks.append(chunk)
        remaining = remaining[0x4000:]

    # Need at least 2 banks (bank 0 + bank 1)
    # Padding banks are filled with RET (0xC9) instead of NOP (0x00).
    # NOP-filled banks cause a NOP-slide: if GBS code switches to an empty
    # bank and executes there, NOPs run through 0x4000-0x7FFF into VRAM
    # (0x8000+), hitting an invalid opcode and crashing.  RET stops this.
    RET_BANK = bytearray(b"\xC9" * 0x4000)
    if len(banks) < 2:
        banks.append(bytearray(RET_BANK))

    # Round total bank count up to next power of 2
    p = 1
    while p < len(banks):
        p <<= 1
    while len(banks) < p:
        banks.append(bytearray(RET_BANK))

    rom = bytearray().join(banks)

    # -- Defensive patches for GBS compatibility --
    # 1. Patch unused RST vectors with RET (0xC9).
    #    GBDK leaves RST 00/08/10/18/38 as 0xFF.  0xFF = RST 38 opcode,
    #    so any accidental execution creates an infinite RST 38 loop → crash.
    #    (GBDK uses RST 20/28/30 — those are left untouched.)
    for rst_addr in [0x00, 0x08, 0x10, 0x18, 0x38]:
        if rom[rst_addr] == 0xFF:
            rom[rst_addr] = 0xC9  # RET

    # 2. Fill 0xFF gap between player code end and GBS load_addr with RET.
    #    Prevents crash if GBS code calls/jumps into the unused ROM region.
    gap_start = 0
    if load < 0x4000:
        for i in range(load - 1, -1, -1):
            if rom[i] != 0xFF:
                gap_start = i + 1
                break
        n_filled = 0
        for i in range(gap_start, load):
            rom[i] = 0xC9  # RET
            n_filled += 1
        if n_filled:
            print(f"[build.py] Filled {n_filled} byte gap "
                  f"(0x{gap_start:04X}-0x{load-1:04X}) with RET")

    # 3. Auto-scan GBS payload and install helpers as needed.
    #
    #    The scan looks for specific call targets and RST opcodes that the GBS
    #    engine uses but that do not exist in the standalone player ROM.
    #    All helpers are placed in the Bank 0 gap (gap_start … load-1).
    #    This replaces the previous title-string check so that any GBS with
    #    similar calling conventions benefits automatically.
    #
    #    Scan range: load_addr onwards (player Bank 0 code is excluded to
    #    avoid false positives from player-internal calls).
    if load < 0x4000:
        scan_region = bytes(rom[load:])

        needs_farcall    = _scan_rst(scan_region, 0x08)       # RST $08  (0xFF)
        needs_bankswitch = _scan_rst(scan_region, 0x10)       # RST $10  (0xD7)
        needs_jumptable  = _scan_rst(scan_region, 0x28)       # RST $28  (0xEF)
        needs_delayframe = _scan_call(scan_region, 0x032E)    # CALL $032E
        needs_mapmusic   = _scan_call(scan_region, 0x2D96)    # CALL $2D96
        needs_bytefill   = _scan_call(scan_region, 0x1922)    # CALL $1922
        needs_copyret    = _scan_call(scan_region, 0x1955)    # CALL $1955
        needs_rb_audio   = (
            rb_family
            and (_scan_call(scan_region, 0x20AF)
                 or _scan_call(scan_region, 0x23A1)
                 or _scan_call(scan_region, 0x23B1)
                 or _scan_call(scan_region, 0x3739))
        )
        if rb_family:
            needs_farcall = False
            needs_bankswitch = False
            needs_jumptable = False
        has_ceea         = _scan_addr_access(scan_region, 0xCEEA)  # CEEA access
        call_hl_helpers  = _find_call_hl_helpers(payload, load)
        if rb_family:
            call_hl_helpers = []

        needs_any = any([needs_farcall, needs_bankswitch, needs_jumptable,
                         needs_delayframe, needs_mapmusic, needs_bytefill,
                         needs_copyret, needs_rb_audio, call_hl_helpers])

        if needs_any:
            helper_addr = gap_start
            bank_base = 0x39 if gs_family else 0x00
            bank_shadow = 0x9D if c_family else 0x9F

            # FarCall helper (RST $08 target):
            # Switches bank, calls HL, restores bank.
            # Uses reserved WRAM scratch:
            #   0xC2C2-0xC2C3 = returned BC
            #   0xC2C4        = temp bank
            farcall = bytearray([
                0xEA, 0xC4, 0xC2,       # ld  ($C2C4), a         ; save bank arg
                0xF0, bank_shadow,      # ldh a, ($FFxx)
                0xF5,                   # push af                ; save current bank
                0xFA, 0xC4, 0xC2,       # ld  a, ($C2C4)
            ])
            if c_family:
                farcall.extend([
                    0xFE, 0x3A,          # cp  $3A
                    0x38, 0x08,          # jr  c, .check44
                    0xFE, 0x3E,          # cp  $3E
                    0x30, 0x04,          # jr  nc, .check44
                    0xD6, 0x39,          # sub $39
                    0x18, 0x0E,          # jr  .bank_done
                    0xFE, 0x44,          # .check44: cp $44
                    0x20, 0x04,          # jr  nz, .check45
                    0x3E, 0x05,          # ld  a, $05
                    0x18, 0x06,          # jr  .bank_done
                    0xFE, 0x45,          # .check45: cp $45
                    0x20, 0x02,          # jr  nz, .bank_done
                    0x3E, 0x01,          # ld  a, $01
                ])
            elif bank_base:
                farcall.extend([
                    0xD6, bank_base,    # sub $39               ; original->compact
                ])
            farcall.extend([
                0xEA, 0xC4, 0xC2,       # ld  ($C2C4), a
                0xAF,                   # xor a
                0xEA, 0x00, 0x60,       # ld  (0x6000), a
                0xEA, 0x00, 0x40,       # ld  (0x4000), a
                0xFA, 0xC4, 0xC2,       # ld  a, ($C2C4)
                0xE0, bank_shadow,      # ldh ($FFxx), a         ; update shadow
                0xEA, 0x00, 0x20,       # ld  (0x2000), a        ; switch bank
                0xCD, 0x00, 0x00,       # call FarCall_JumpToHL  (patched below)
                0x78,                   # ld  a, b               ; save return BC
                0xEA, 0xC2, 0xC2,       # ld  ($C2C2), a
                0x79,                   # ld  a, c
                0xEA, 0xC3, 0xC2,       # ld  ($C2C3), a
                0xC1,                   # pop bc                 ; restore old bank
                0x78,                   # ld  a, b
                0xEA, 0xC4, 0xC2,       # ld  ($C2C4), a
                0xAF,                   # xor a
                0xEA, 0x00, 0x60,       # ld  (0x6000), a
                0xEA, 0x00, 0x40,       # ld  (0x4000), a
                0xFA, 0xC4, 0xC2,       # ld  a, ($C2C4)
                0xE0, bank_shadow,      # ldh ($FFxx), a
                0xEA, 0x00, 0x20,       # ld  (0x2000), a
                0xFA, 0xC2, 0xC2,       # ld  a, ($C2C2)         ; restore return BC
                0x47,                   # ld  b, a
                0xFA, 0xC3, 0xC2,       # ld  a, ($C2C3)
                0x4F,                   # ld  c, a
                0xC9,                   # ret
                0xE9,                   # FarCall_JumpToHL: jp hl
            ])
            jump_to_hl = helper_addr + len(farcall) - 1
            call_idx = farcall.index(0xCD)
            farcall[call_idx + 1] = jump_to_hl & 0xFF
            farcall[call_idx + 2] = (jump_to_hl >> 8) & 0xFF

            bankswitch_addr = helper_addr + len(farcall)
            if c_family:
                bankswitch_helper = bytearray([
                    0xFE, 0x3A,          # cp  $3A
                    0x38, 0x08,          # jr  c, .check44
                    0xFE, 0x3E,          # cp  $3E
                    0x30, 0x04,          # jr  nc, .check44
                    0xD6, 0x39,          # sub $39
                    0x18, 0x0E,          # jr  .write
                    0xFE, 0x44,          # .check44: cp $44
                    0x20, 0x04,          # jr  nz, .check45
                    0x3E, 0x05,          # ld  a, $05
                    0x18, 0x06,          # jr  .write
                    0xFE, 0x45,          # .check45: cp $45
                    0x20, 0x02,          # jr  nz, .write
                    0x3E, 0x01,          # ld  a, $01
                    0xEA, 0xC4, 0xC2,    # .write: ld ($C2C4), a
                    0xAF,                # xor a
                    0xEA, 0x00, 0x60,    # ld (0x6000), a
                    0xEA, 0x00, 0x40,    # ld (0x4000), a
                    0xFA, 0xC4, 0xC2,    # ld a, ($C2C4)
                    0xE0, bank_shadow,   # .write: ldh ($FFxx), a
                    0xEA, 0x00, 0x20,    # ld  (0x2000), a
                    0xC9,                # ret
                ])
            else:
                bankswitch_helper = bytearray()

            delay_addr = bankswitch_addr + len(bankswitch_helper)

            # DelayFrame stub:
            # Use a fixed busy wait instead of HALT/VBlank sync.
            # In the standalone player, enabling interrupts inside INIT to
            # service HALT-based DelayFrame can corrupt the expected stack flow.
            # A short bounded delay is safer than relying on IME/VBlank state.
            delayframe = bytearray([
                0x06, 0x20,             # ld   b, $20
                0x0E, 0x00,             # ld   c, $00
                0x0D,                   # .inner: dec c
                0x20, 0xFD,             # jr   nz, .inner
                0x05,                   # dec  b
                0x20, 0xF9,             # jr   nz, .inner
                0xC9,                   # ret
            ])

            mapmusic_addr = delay_addr + len(delayframe)

            # GetMapMusic stub ($2D96):
            # Return the currently selected music id tracked by the engine.
            # This driver stores the active song id in a WRAM shadow before
            # entering the loader path that can call GetMapMusic. Returning
            # that value is safer than reading map state, which is undefined
            # in a standalone GBS player.
            mapmusic_stub = bytearray([
                0xFA, 0x9D, 0xC1,       # ld  a, ($C19D)
                0x5F,                   # ld  e, a
                0xFA, 0x9E, 0xC1,       # ld  a, ($C19E)
                0x57,                   # ld  d, a
                0xA7,                   # and a        ; clear carry
                0xC9,                   # ret
            ])

            bytefill_addr = mapmusic_addr + len(mapmusic_stub)

            # ByteFill helper ($1922):
            #   HL = dst, B = count, C = value
            # Fills B bytes and returns.
            bytefill_stub = bytearray([
                0x78,                   # ld   a, b
                0xA7,                   # and  a
                0xC8,                   # ret  z
                0x79,                   # ld   a, c
                0x22,                   # .loop: ld (hl+), a
                0x05,                   # dec  b
                0x20, 0xFC,             # jr   nz, .loop
                0xC9,                   # ret
            ])

            copyret_addr = bytefill_addr + len(bytefill_stub)

            # RET-inclusive copy helper ($1955):
            #   HL = dst, DE = src
            # Copies bytes until a RET opcode (0xC9) is copied, then returns
            # BC = end-of-destination pointer for append-style callers.
            copyret_stub = bytearray([
                0x1A,                   # .loop: ld   a, (de)
                0x13,                   #        inc  de
                0x22,                   #        ld   (hl+), a
                0xFE, 0xC9,             #        cp   $C9
                0x20, 0xF8,             #        jr   nz, .loop
                0x44,                   # ld   b, h
                0x4D,                   # ld   c, l
                0xC9,                   # ret
            ])

            rb_delayframe_addr = copyret_addr + len(copyret_stub)

            rb_delayframe = bytearray([
                0x06, 0x20,             # ld   b, $20
                0x05,                   # .loop: dec  b
                0x20, 0xFD,             # jr   nz, .loop
                0xC9,                   # ret
            ])

            rb_delayframes_addr = rb_delayframe_addr + len(rb_delayframe)

            rb_delayframes = bytearray([
                0x79,                   # ld   a, c
                0xA7,                   # and  a
                0xC8,                   # ret  z
                0xC5,                   # .next: push bc
                0xCD, rb_delayframe_addr & 0xFF, (rb_delayframe_addr >> 8) & 0xFF,
                0xC1,                   # pop  bc
                0x0D,                   # dec  c
                0x20, 0xF8,             # jr   nz, .next
                0xC9,                   # ret
            ])

            rb_resolve_bank_addr = rb_delayframes_addr + len(rb_delayframes)

            rb_resolve_bank = bytearray([
                0xFA, 0xEF, 0xC0,       # ld   a, ($C0EF)
                0xA7,                   # and  a
                0x20, 0x09,             # jr   nz, .normalize
                0xFA, 0xF0, 0xC0,       # ld   a, ($C0F0)
                0xA7,                   # and  a
                0x20, 0x03,             # jr   nz, .normalize
                0x3E, 0x01,             # ld   a, $01
                0xC9,                   # ret
                0xFE, 0x08,             # .normalize: cp   $08
                0x20, 0x03,             # jr   nz, .check_bank3
                0x3E, 0x02,             # ld   a, $02
                0xC9,                   # ret
                0xFE, 0x1F,             # .check_bank3: cp   $1F
                0x20, 0x02,             # jr   nz, .done
                0x3E, 0x03,             # ld   a, $03
                0xC9,                   # ret
                0xC9,                   # .done: ret
            ])

            rb_playsound_addr = rb_resolve_bank_addr + len(rb_resolve_bank)

            rb_playsound = bytearray([
                0xE5,                   # push hl
                0xD5,                   # push de
                0xC5,                   # push bc
                0x47,                   # ld   b, a
                0xFA, 0xEE, 0xC0,       # ld   a, ($C0EE)
                0xA7,                   # and  a
                0x28, 0x11,             # jr   z, .dispatch
                0xAF,                   # xor  a
                0xEA, 0x2A, 0xC0,       # ld   ($C02A), a
                0xEA, 0x2B, 0xC0,       # ld   ($C02B), a
                0xEA, 0x2C, 0xC0,       # ld   ($C02C), a
                0xEA, 0x2D, 0xC0,       # ld   ($C02D), a
                0xAF,                   # xor  a
                0xEA, 0xEE, 0xC0,       # ld   ($C0EE), a
                0xF0, 0x9F,             # ldh  a, ($FF9F)
                0xF5,                   # push af
                0xCD, rb_resolve_bank_addr & 0xFF, (rb_resolve_bank_addr >> 8) & 0xFF,
                0xFE, 0x01,             # cp   $01
                0x28, 0x0F,             # jr   z, .audio1
                0xFE, 0x02,             # cp   $02
                0x28, 0x16,             # jr   z, .audio2
                0xE0, 0x9F,             # .audio3: ldh ($FF9F), a
                0xEA, 0x00, 0x20,       # ld   ($2000), a
                0x78,                   # ld   a, b
                0xCD, 0xEA, 0x58,       # call $58EA
                0x18, 0x14,             # jr   .restore
                0xE0, 0x9F,             # .audio1: ldh ($FF9F), a
                0xEA, 0x00, 0x20,       # ld   ($2000), a
                0x78,                   # ld   a, b
                0xCD, 0x76, 0x58,       # call $5876
                0x18, 0x09,             # jr   .restore
                0xE0, 0x9F,             # .audio2: ldh ($FF9F), a
                0xEA, 0x00, 0x20,       # ld   ($2000), a
                0x78,                   # ld   a, b
                0xCD, 0x35, 0x60,       # call $6035
                0xF1,                   # .restore: pop  af
                0xE0, 0x9F,             # ldh  ($FF9F), a
                0xEA, 0x00, 0x20,       # ld   ($2000), a
                0x18, 0x00,             # jr   .done
                0xC1,                   # pop  bc
                0xD1,                   # pop  de
                0xE1,                   # pop  hl
                0xC9,                   # .done: ret
            ])

            rb_playmusic_addr = rb_playsound_addr + len(rb_playsound)

            rb_playmusic = bytearray([
                0x47,                   # ld   b, a              ; keep target song id
                0x79,                   # ld   a, c
                0xEA, 0xEF, 0xC0,       # ld   ($C0EF), a
                0xEA, 0xF0, 0xC0,       # ld   ($C0F0), a
                0xF5,                   # push af                ; preserve bank
                0x3E, 0xFF,             # ld   a, $FF            ; SFX_STOP_ALL_MUSIC
                0xCD, rb_playsound_addr & 0xFF, (rb_playsound_addr >> 8) & 0xFF,
                0x0E, 0x01,             # ld   c, $01
                0xCD, rb_delayframes_addr & 0xFF, (rb_delayframes_addr >> 8) & 0xFF,
                0xF1,                   # pop  af
                0xEA, 0xEF, 0xC0,       # ld   ($C0EF), a
                0xEA, 0xF0, 0xC0,       # ld   ($C0F0), a
                0x78,                   # ld   a, b
                0xEA, 0xEE, 0xC0,       # ld   ($C0EE), a
                0xC3, rb_playsound_addr & 0xFF, (rb_playsound_addr >> 8) & 0xFF,
            ])

            rb_waitsound_addr = rb_playmusic_addr + len(rb_playmusic)

            # PlaySoundWaitForCurrent helper ($3740):
            # skip waiting while the low-health alarm is active, otherwise wait
            # until SFX channels go idle, then tail-call PlaySound.
            rb_waitsound = bytearray([
                0xF5,                   # push af
                0xFA, 0x83, 0xD0,       # ld   a, ($D083) ; wLowHealthAlarm
                0xE6, 0x80,             # and  $80
                0x20, 0x09,             # jr   nz, .play
                0x21, 0x2A, 0xC0,       # .wait: ld hl, $C02A ; wChannelSoundIDs+CHAN5
                0xAF,                   # xor  a
                0xB6,                   # or   (hl)
                0x23,                   # inc  hl
                0xB6,                   # or   (hl)
                0x23,                   # inc  hl
                0x23,                   # inc  hl
                0xB6,                   # or   (hl)
                0x20, 0xF7,             # jr   nz, .wait
                0xF1,                   # .play: pop  af
                0xC3, rb_playsound_addr & 0xFF, (rb_playsound_addr >> 8) & 0xFF,
            ])

            rb_waitonly_addr = rb_waitsound_addr + len(rb_waitsound)

            # WaitForSoundToFinish helper ($3748):
            # if low-health alarm is active, return immediately; otherwise wait
            # until the SFX channels go idle.
            rb_waitonly = bytearray([
                0xFA, 0x83, 0xD0,       # ld   a, ($D083) ; wLowHealthAlarm
                0xE6, 0x80,             # and  $80
                0xC0,                   # ret  nz
                0xE5,                   # push hl
                0x21, 0x2A, 0xC0,       # .wait: ld hl, $C02A
                0xAF,                   # xor  a
                0xB6,                   # or   (hl)
                0x23,                   # inc  hl
                0xB6,                   # or   (hl)
                0x23,                   # inc  hl
                0x23,                   # inc  hl
                0xB6,                   # or   (hl)
                0x20, 0xF7,             # jr   nz, .wait
                0xE1,                   # pop  hl
                0xC9,                   # ret
            ])

            if not rb_family:
                rb_delayframe = bytearray()
                rb_delayframes = bytearray()
                rb_resolve_bank = bytearray()
                rb_playsound = bytearray()
                rb_playmusic = bytearray()
                rb_waitsound = bytearray()
                rb_waitonly = bytearray()
                rb_delayframes_addr = rb_delayframe_addr
                rb_resolve_bank_addr = rb_delayframes_addr
                rb_playsound_addr = rb_resolve_bank_addr
                rb_playmusic_addr = rb_playsound_addr
                rb_waitsound_addr = rb_playmusic_addr
                rb_waitonly_addr = rb_waitsound_addr

            # RST $28 handler placed in gap (11 bytes):
            # table lookup via HL=table_base, A=index -> JP table[A*2]
            rst28_handler = bytearray([
                0xD5,                   # push de
                0x5F,                   # ld   e, a
                0x16, 0x00,             # ld   d, 0
                0x19,                   # add  hl, de
                0x19,                   # add  hl, de
                0x2A,                   # ld   a, (hl+)
                0x66,                   # ld   h, (hl)
                0x6F,                   # ld   l, a
                0xD1,                   # pop  de
                0xE9,                   # jp   hl
            ])
            rst28_handler_addr = rb_waitonly_addr + len(rb_waitonly)

            # Relocated memset loop (was at 0x0028, player's GBDK helper):
            # LD (HL+),A; DEC C; JR NZ,loop; RET  -- used via JP from 0x00C9
            # JR NZ: PC after instruction = (memset_addr+4), offset = -4 = 0xFC
            memset_addr = rst28_handler_addr + len(rst28_handler)
            memset_loop = bytearray([
                0x22,                   # ld   (hl+), a
                0x0D,                   # dec  c
                0x20, 0xFC,             # jr   nz, -4  (back to ld (hl+),a at +0)
                0xC9,                   # ret
            ])

            helper_end = memset_addr + len(memset_loop)
            rb_play_dispatch_addr = helper_end
            rb_play_dispatch = bytearray()
            if rb_family:
                rb_play_dispatch = bytearray([
                    0xCD, rb_resolve_bank_addr & 0xFF, (rb_resolve_bank_addr >> 8) & 0xFF,
                    0xFE, 0x01,             # cp   $01
                    0x20, 0x05,             # jr   nz, .check_bank2
                    0xCD, 0x03, 0x51,       # call $5103
                    0x18, 0x0F,             # jr   .done
                    0xFE, 0x02,             # .check_bank2: cp   $02
                    0x20, 0x08,             # jr   nz, .bank3
                    0xCD, 0x6E, 0x53,       # call $536E
                    0xCD, 0x79, 0x58,       # call $5879
                    0x18, 0x03,             # jr   .done
                    0xCD, 0x77, 0x51,       # .bank3: call $5177
                    0xC9,                   # .done: ret
                ])
                helper_end = rb_play_dispatch_addr + len(rb_play_dispatch)
            if helper_end > load:
                sys.exit("ERROR: not enough Bank 0 gap space for GBS helpers")

            write_rom(rom, helper_addr,          farcall)
            write_rom(rom, bankswitch_addr,      bankswitch_helper)
            write_rom(rom, delay_addr,            delayframe)
            write_rom(rom, mapmusic_addr,         mapmusic_stub)
            write_rom(rom, bytefill_addr,         bytefill_stub)
            write_rom(rom, copyret_addr,          copyret_stub)
            write_rom(rom, rb_delayframe_addr,    rb_delayframe)
            write_rom(rom, rb_delayframes_addr,   rb_delayframes)
            write_rom(rom, rb_resolve_bank_addr, rb_resolve_bank)
            write_rom(rom, rb_playsound_addr,     rb_playsound)
            write_rom(rom, rb_playmusic_addr,     rb_playmusic)
            write_rom(rom, rb_waitsound_addr,     rb_waitsound)
            write_rom(rom, rb_waitonly_addr,      rb_waitonly)
            if needs_jumptable:
                write_rom(rom, rst28_handler_addr, rst28_handler)
            write_rom(rom, memset_addr,           memset_loop)
            if rb_family:
                write_rom(rom, rb_play_dispatch_addr, rb_play_dispatch)

            c_profile_direct_bank_patches = 0
            if c_family:
                for i in range(load, 0x4000 - 2):
                    # This profile's Bank 0 helper has direct MBC writes that do not
                    # pass through RST $10. Route them through the same helper
                    # so original/compact banks and MBC1 upper bits are normalized.
                    if rom[i:i + 3] == bytes([0xEA, 0x00, 0x20]):
                        rom[i] = 0xCD
                        rom[i + 1] = bankswitch_addr & 0xFF
                        rom[i + 2] = (bankswitch_addr >> 8) & 0xFF
                        c_profile_direct_bank_patches += 1

            # RST $08: FarCall
            if needs_farcall and rom[0x0008] == 0xC9:
                rst8 = [
                    0xC3, helper_addr & 0xFF, (helper_addr >> 8) & 0xFF,
                    0xC9, 0xC9, 0xC9, 0xC9, 0xC9,
                ]
                write_rom(rom, 0x0008, rst8)

            # RST $10: Bankswitch (ldh ($FF9F),a / ld (0x2000),a)
            if needs_bankswitch and rom[0x0010] == 0xC9:
                if c_family:
                    rst10 = [
                        0xC3, bankswitch_addr & 0xFF, (bankswitch_addr >> 8) & 0xFF,
                    ]
                else:
                    rst10 = []
                    if bank_base:
                        rst10.extend([
                            0xD6, bank_base,    # sub $39
                        ])
                    rst10.extend([
                        0xE0, bank_shadow,      # ldh ($FFxx), a
                        0xEA, 0x00, 0x20,       # ld  (0x2000), a
                        0xC9,
                    ])
                while len(rst10) < 8:
                    rst10.append(0xC9)
                write_rom(rom, 0x0010, rst10)

            # RST $28: JumpTable dispatcher.
            # Install a JP trampoline at 0x0028 (3 bytes) pointing to the
            # full handler in the gap.  A direct 11-byte write would overlap
            # 0x0030 (RST $30 / player memcpy helper used by GBDK code), so
            # we use a trampoline that only touches 0x0028-0x002A.
            # At the same time the original GBDK memset loop that lived at
            # 0x0028 is relocated to the gap; patch its one caller (JP $0028
            # at 0x00C9) to point to the new location.
            if needs_jumptable:
                # Install JP trampoline at 0x0028 (3 bytes, safe: 0x002B-0x002F are 0xFF)
                rom[0x0028] = 0xC3
                rom[0x0029] = rst28_handler_addr & 0xFF
                rom[0x002A] = (rst28_handler_addr >> 8) & 0xFF
                # Patch the player's JP $0028 caller at 0x00C9 to use relocated memset
                if rom[0x00C9] == 0xC3 and rom[0x00CA] == 0x28 and rom[0x00CB] == 0x00:
                    rom[0x00CA] = memset_addr & 0xFF
                    rom[0x00CB] = (memset_addr >> 8) & 0xFF

            # VBlank vector: do NOT override 0x0040 here.
            # main.c installs vbl_play_isr via ISR_VECTOR(VECTOR_VBL, vbl_play_isr),
            # which correctly handles VBL:
            #   - clears wVBlankOccurred (CEEA) if GBS_HAS_CEEA_FLAG is set
            #   - calls gbs_play_trampoline() only after playing=1 (post-INIT)
            #   - uses proper GBS stack (GBS_STACK_PTR) via gbs_play_trampoline
            #   - sets frame_done for the main loop
            # A standalone vblank_stub that calls GBS_PLAY_ADDR directly (without
            # stack switch) would run PLAY with uninitialized audio state before
            # INIT completes, causing crashes on emulators with random WRAM.

            # Patch DelayFrame calls to local stub
            delay_patches = 0
            if needs_delayframe:
                delay_patches = patch_calls(rom, load, 0xCD, 0x2E, 0x03, delay_addr)

            # Patch GetMapMusic calls to local stub
            mapmusic_patches = 0
            if needs_mapmusic:
                mapmusic_patches = patch_calls(rom, load, 0xCD, 0x96, 0x2D, mapmusic_addr)

            bytefill_patches = 0
            if needs_bytefill:
                bytefill_patches = patch_calls(rom, load, 0xCD, 0x22, 0x19, bytefill_addr)

            copyret_patches = 0
            if needs_copyret:
                copyret_patches = patch_calls(rom, load, 0xCD, 0x55, 0x19, copyret_addr)

            rb_audio_patches = 0
            if rb_family and needs_rb_audio:
                rb_audio_patches += patch_calls(rom, load, 0xCD, 0xB1, 0x23, rb_playsound_addr)
                rb_audio_patches += patch_calls(rom, load, 0xCD, 0xAF, 0x20, rb_delayframe_addr)
                rb_audio_patches += patch_calls(rom, load, 0xCD, 0x39, 0x37, rb_delayframes_addr)
                rb_audio_patches += patch_calls(rom, load, 0xCD, 0xA1, 0x23, rb_playmusic_addr)
                rb_audio_patches += patch_calls(rom, load, 0xC3, 0xA1, 0x23, rb_playmusic_addr)

                # Bank 3's music-start helper chain ends with JP $2307 into
                # the synthetic Bank 0 helper area.  In the standalone player
                # that target is occupied by normal code, so terminate the
                # helper sequence locally after our PlayMusic replacement.
                for i in range(load, len(rom) - 2):
                    if rom[i] == 0xC3 and rom[i + 1] == 0x07 and rom[i + 2] == 0x23:
                        rom[i] = 0xC9
                        rom[i + 1] = 0x00
                        rom[i + 2] = 0x00

                # Redirect every exact CALL/JP match so bank-local helper chains
                # cannot fall back into missing home-bank code in compacted ROMs.

            # Install inferred CALL-HL trampolines directly at their original
            # low-address targets when that region lies inside the Bank 0 gap.
            for target, info in call_hl_helpers:
                if gap_start <= target < load and rom[target] in (0xC9, 0xFF):
                    rom[target] = 0xE9  # JP HL

            if rb_family and rom[0x3740] in (0xC9, 0xFF):
                rom[0x3740] = 0xC3
                rom[0x3741] = rb_waitsound_addr & 0xFF
                rom[0x3742] = (rb_waitsound_addr >> 8) & 0xFF

            if rb_family and rom[0x3748] in (0xC9, 0xFF):
                rom[0x3748] = 0xC3
                rom[0x3749] = rb_waitonly_addr & 0xFF
                rom[0x374A] = (rb_waitonly_addr >> 8) & 0xFF

            if rb_family and not g.get("source_rom"):
                if rom[0x3F7E] == 0xFA and rom[0x3F7F] == 0xEF and rom[0x3F80] == 0xC0:
                    rom[0x3F7E] = 0xC3
                    rom[0x3F7F] = rb_play_dispatch_addr & 0xFF
                    rom[0x3F80] = (rb_play_dispatch_addr >> 8) & 0xFF

            parts = []
            if needs_farcall:    parts.append(f"FarCall@0x{helper_addr:04X}")
            if needs_bankswitch: parts.append("RST10")
            if needs_jumptable:  parts.append(f"RST28@0x{rst28_handler_addr:04X}(trampoline@0028)")
            if c_profile_direct_bank_patches:
                parts.append(f"CProfileBankMap({c_profile_direct_bank_patches}p)")
            if delay_patches:    parts.append(f"DelayFrame@0x{delay_addr:04X}({delay_patches}p)")
            if mapmusic_patches: parts.append(f"GetMapMusic@0x{mapmusic_addr:04X}({mapmusic_patches}p)")
            if bytefill_patches: parts.append(f"ByteFill@0x{bytefill_addr:04X}({bytefill_patches}p)")
            if copyret_patches:  parts.append(f"CopyRet@0x{copyret_addr:04X}({copyret_patches}p)")
            if rb_audio_patches:
                parts.append(
                    f"RBAudio@0x{rb_playmusic_addr:04X}/0x{rb_playsound_addr:04X}"
                    f"({rb_audio_patches}p)"
                )
            for target, info in call_hl_helpers:
                if gap_start <= target < load:
                    parts.append(f"CallHL@0x{target:04X}({info['count']}x)")
            if has_ceea:         parts.append("CEEA")
            print(f"[build.py] Auto-installed helpers for profile '{compat or 'generic'}': {', '.join(parts)}")
        else:
            print(f"[build.py] No Bank0 helpers needed for profile '{compat or 'generic'}'")

    # 4. Do not rewrite below-load_addr calls generically.
    #    Blindly redirecting calls into the player region to RET can leave
    #    engine state half-initialized.  Per-helper patching above is safer.

    if rb_family and g.get("source_rom"):
        # This profile's AUDIO_2 jingles 0x86/0x9A use sound channels 4-6.
        # Channel-4 handling has a pair of game-state checks against D060 bit7.
        # In a standalone GBS environment that state is not meaningful and can
        # skip or alter the harmony voice, so bypass those checks in AUDIO_2.
        audio_2_start = 0x08 * 0x4000
        audio_2 = rom[audio_2_start:audio_2_start + 0x4000]
        gate = bytes([0xFA, 0x60, 0xD0, 0xCB, 0x7F, 0xC0])
        gate_in_bank = audio_2.find(gate)
        if gate_in_bank >= 0:
            gate_addr = audio_2_start + gate_in_bank
            rom[gate_addr:gate_addr + len(gate)] = b"\x00" * len(gate)
            print(f"[build.py] Patched AUDIO_2 channel-4 game-state gate at 0x{0x4000 + gate_in_bank:04X}")
        else:
            print("[build.py] WARNING: AUDIO_2 channel-4 gate not found")
        if compat == COMPAT_RB_B:
            state_block = bytes([
                0xFA, 0x60, 0xD0,       # ld a, ($D060)
                0xCB, 0x7F,             # bit 7, a
                0x28, 0x09,             # jr z, .done
                0xAF,                   # xor a
                0xEA, 0xF1, 0xC0,       # ld ($C0F1), a
                0x3E, 0x80,             # ld a, $80
                0xEA, 0xF2, 0xC0,       # ld ($C0F2), a
            ])
            state_in_bank = audio_2.find(state_block)
            if state_in_bank >= 0:
                state_addr = audio_2_start + state_in_bank
                rom[state_addr:state_addr + len(state_block)] = b"\x00" * len(state_block)
                print(f"[build.py] Patched AUDIO_2 channel-4 state block at 0x{0x4000 + state_in_bank:04X}")
            else:
                print("[build.py] WARNING: AUDIO_2 channel-4 state block not found")

    # ROM size byte: 0x00=32KB(2 banks), 0x01=64KB(4), 0x02=128KB(8) …
    rom_size_byte = int(math.log2(len(banks))) - 1

    # Patch GB ROM header
    rom[0x143] = 0xC0           # CGB only
    rom[0x147] = 0x03           # MBC1 + RAM + BATTERY
    rom[0x148] = rom_size_byte  # ROM size
    rom[0x149] = 0x02           # 8 KB SRAM

    # Header checksum (0x134–0x14C)
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    with open(out_path, "wb") as f:
        f.write(rom)
    print(f"[build.py] ROM written: {out_path}  "
          f"({len(rom)} bytes, {g['num_songs']} songs, "
          f"{len(banks)} banks, load=0x{load:04X})")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "header" and len(sys.argv) == 3:
        cmd_header(sys.argv[2])
    elif cmd == "merge" and len(sys.argv) == 5:
        cmd_merge(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "metadata" and len(sys.argv) == 4:
        cmd_metadata(sys.argv[2], sys.argv[3])
    else:
        print(__doc__); sys.exit(1)
