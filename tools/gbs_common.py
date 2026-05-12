#!/usr/bin/env python3
"""
tools/gbs_common.py  --  Shared utilities for GBS Player tools

Shared between build.py and sav_editor.py:
  - Japanese character encoding constants and tables
  - utf8_to_custom() / custom_to_utf8() encoding functions
  - parse_gbs_header() GBS file parser
  - load_song_names() companion file loader
"""
import os, struct

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

HIRAGANA  = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
KATAKANA  = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
SMALL_HIRA = "ぁぃぅぇぉゃゅょっ"
SMALL_KATA = "ァィゥェォャュョッ"

# Decomposition tables: composed char → base char
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

# Reverse composition maps (base char → composed char)
_DAKUTEN_COMPOSE    = {v: k for k, v in DAKUTEN_DECOMP.items()}
_HANDAKUTEN_COMPOSE = {v: k for k, v in HANDAKUTEN_DECOMP.items()}


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
        elif ch == '゙' or ch == '゛' or ch == 'ﾞ':
            result.append(0x01)  # ゛
        elif ch == '゚' or ch == '゜' or ch == 'ﾟ':
            result.append(0x02)  # ゜
        elif ch == 'ー' or ch == 'ｰ':
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


def _byte_to_base_char(b):
    """Convert an encoded byte to its base character (for composition)."""
    if 0x80 <= b <= 0xAD:
        idx = b - 0x80
        return HIRAGANA[idx] if idx < len(HIRAGANA) else None
    if 0xB0 <= b <= 0xDD:
        idx = b - 0xB0
        return KATAKANA[idx] if idx < len(KATAKANA) else None
    return None


def custom_to_utf8(data):
    """Convert custom encoding bytes to UTF-8. Composes base+mark → dakuten chars."""
    result = []
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0:
            break
        next_b = data[i + 1] if i + 1 < len(data) else 0
        if next_b == 0x01:  # ゛ follows
            ch = _byte_to_base_char(b)
            if ch and ch in _DAKUTEN_COMPOSE:
                result.append(_DAKUTEN_COMPOSE[ch])
                i += 2
                continue
        elif next_b == 0x02:  # ゜ follows
            ch = _byte_to_base_char(b)
            if ch and ch in _HANDAKUTEN_COMPOSE:
                result.append(_HANDAKUTEN_COMPOSE[ch])
                i += 2
                continue
        if 0x20 <= b <= 0x7E:
            result.append(chr(b))
        elif b == 0x01:
            result.append('゛')  # ゛
        elif b == 0x02:
            result.append('゜')  # ゜
        elif b == 0x03:
            result.append('ー')
        elif 0x04 <= b <= 0x0C:
            idx = b - 0x04
            if idx < len(SMALL_HIRA):
                result.append(SMALL_HIRA[idx])
        elif 0x0D <= b <= 0x15:
            idx = b - 0x0D
            if idx < len(SMALL_KATA):
                result.append(SMALL_KATA[idx])
        elif 0x80 <= b <= 0xAD:
            idx = b - 0x80
            if idx < len(HIRAGANA):
                result.append(HIRAGANA[idx])
        elif 0xB0 <= b <= 0xDD:
            idx = b - 0xB0
            if idx < len(KATAKANA):
                result.append(KATAKANA[idx])
        i += 1
    return "".join(result)


def parse_gbs_header(path):
    """Parse GBS file header. Returns dict of header fields (no payload).
    Raises ValueError if the file is not a valid GBS file.
    """
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:3] != b"GBS":
        raise ValueError(f"{path} is not a GBS file (magic mismatch)")
    h = struct.unpack_from("<BBBHHHHBB", raw, 3)
    ver, num, first, load, init, play, stack, tmod, tctl = h
    def s(off): return raw[off:off+32].rstrip(b"\x00").decode("ascii", errors="replace")
    return {
        "num_songs":  num,
        "first_song": first,
        "load_addr":  load,
        "init_addr":  init,
        "play_addr":  play,
        "stack_ptr":  stack,
        "timer_mod":  tmod,
        "timer_ctl":  tctl,
        "title":      s(0x10),
        "author":     s(0x30),
        "copyright":  s(0x50),
    }


def load_song_names(gbs_path, num_songs):
    """Load song names from companion file. Returns (names, source_path)."""
    base = os.path.splitext(gbs_path)[0]
    candidates = [
        base + ".names.txt",
        os.path.join(os.path.dirname(gbs_path) or ".", "songnames.txt"),
    ]
    names = [""] * num_songs
    for path in candidates:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if i >= num_songs:
                    break
                names[i] = line.strip()
            print(f"[gbs_common] Song names loaded from: {path} ({min(len(lines), num_songs)} names)")
            return names, path
    return names, None
