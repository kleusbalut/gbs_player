#!/usr/bin/env python3
"""
Generate 8x8 Japanese font tile data for Game Boy (2bpp format)
from the Pokemon Strict font (pkmn_s.ttf).

Outputs src/player/jp_font.h with all Japanese character tiles.

Tile allocation (0-255):
  0-95   : font_ibm (ASCII 0x20-0x7F)
  3-5    : repeat icons (overlap with font_ibm, OK)
  96-116 : UI tiles (21)
  117-162: base hiragana (46: あ-ん)
  163-171: small hiragana (9: ぁぃぅぇぉゃゅょっ)
  172-217: base katakana (46: ア-ン)
  218-226: small katakana (9: ァィゥェォャュョッ)
  227    : ー (long vowel)
  228    : ゛ (dakuten mark)
  229    : ゜ (handakuten mark)

Custom encoding:
  0x00      : null terminator
  0x01      : ゛ (dakuten, U+3099)
  0x02      : ゜ (handakuten, U+309A)
  0x03      : ー (long vowel)
  0x04-0x0C : small hira (9: ぁぃぅぇぉゃゅょっ)
  0x0D-0x15 : small kata (9: ァィゥェォャュョッ)
  0x20-0x7E : ASCII
  0x80-0xAD : base hiragana (46: あ-ん)
  0xB0-0xDD : base katakana (46: ア-ン)

Requires: pip install Pillow fonttools
"""
import os
from PIL import Image, ImageFont, ImageDraw

# ── Character lists ───────────────────────────────────────────────────────────
BASE_HIRA = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
SMALL_HIRA = "ぁぃぅぇぉゃゅょっ"
BASE_KATA = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
SMALL_KATA = "ァィゥェォャュョッ"

FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts", "pkmnfont", "pkmn_s.ttf")
GBR_PATH  = os.path.join(os.path.dirname(__file__), "..", "assets", "ui", "gbs_player.gbr")

# ── Load a tile from GBR file ─────────────────────────────────────────────────
def load_gbr_tile(gbr_path, tile_index):
    """Load a single tile from a GBTD .gbr file and return 16-byte 2bpp data."""
    import struct
    with open(gbr_path, 'rb') as f:
        raw = f.read()
    # Find tile data record (type 2) — skip 4-byte 'GBO0' header, then records
    pos = 4
    td = None
    while pos + 8 <= len(raw):
        rtype = struct.unpack_from('<H', raw, pos)[0]
        rlen = struct.unpack_from('<I', raw, pos + 4)[0]
        if rtype == 0x0002:
            td = raw[pos + 8:pos + 8 + rlen]
            break
        pos += 8 + rlen
    if td is None:
        raise RuntimeError(f"No tile data in {gbr_path}")
    # GBR tile data: 40-byte header + N tiles at 64 bytes each (1 byte per pixel)
    hdr = 40
    offset = hdr + tile_index * 64
    px = td[offset:offset + 64]
    # Convert to 2bpp
    result = []
    for y in range(8):
        lo = hi = 0
        for x in range(8):
            v = px[y * 8 + x]
            if v & 1: lo |= (0x80 >> x)
            if v & 2: hi |= (0x80 >> x)
        result.append(lo)
        result.append(hi)
    return result

# ── Render a character from TTF to 8x8 bitmap ────────────────────────────────
def render_char(font, ch):
    """Render a single character to an 8-row bitmap (list of 8 ints, each 8 bits)."""
    img = Image.new('1', (16, 16), 0)
    draw = ImageDraw.Draw(img)
    draw.text((0, 0), ch, font=font, fill=1)
    rows = []
    for y in range(8):
        val = 0
        for x in range(8):
            if img.getpixel((x, y)):
                val |= (0x80 >> x)
        rows.append(val)
    return rows

# ── 2bpp conversion ──────────────────────────────────────────────────────────
def bitmap_to_2bpp(rows):
    """Convert 8-row bitmap to 16-byte 2bpp GB tile data."""
    data = []
    for b in rows:
        data.append(b)  # lo plane
        data.append(b)  # hi plane (same = color 3 for set pixels)
    return data

# ── Generate header ──────────────────────────────────────────────────────────
def generate_header():
    if not os.path.isfile(FONT_PATH):
        raise RuntimeError(
            f"PKMN font not found: {FONT_PATH}\n"
            "Run `python tools/fetch_pkmnfont.py` first."
        )
    font = ImageFont.truetype(FONT_PATH, 8)
    gbr_path = GBR_PATH

    all_tiles = []  # (label, 2bpp_data)

    # Group 1: base hiragana (tiles 117-162, 46 chars)
    assert len(BASE_HIRA) == 46
    for i, ch in enumerate(BASE_HIRA):
        bm = render_char(font, ch)
        data = bitmap_to_2bpp(bm)
        all_tiles.append((f"{ch} (tile {117+i}, enc 0x{0x80+i:02X})", data))

    # Group 2: small hiragana (tiles 163-171, 9 chars)
    assert len(SMALL_HIRA) == 9
    for i, ch in enumerate(SMALL_HIRA):
        bm = render_char(font, ch)
        data = bitmap_to_2bpp(bm)
        all_tiles.append((f"{ch} (tile {163+i}, enc 0x{0x04+i:02X})", data))

    # Group 3: base katakana (tiles 172-217, 46 chars)
    assert len(BASE_KATA) == 46
    for i, ch in enumerate(BASE_KATA):
        bm = render_char(font, ch)
        data = bitmap_to_2bpp(bm)
        all_tiles.append((f"{ch} (tile {172+i}, enc 0x{0xB0+i:02X})", data))

    # Group 4: small katakana (tiles 218-226, 9 chars)
    assert len(SMALL_KATA) == 9
    for i, ch in enumerate(SMALL_KATA):
        bm = render_char(font, ch)
        data = bitmap_to_2bpp(bm)
        all_tiles.append((f"{ch} (tile {218+i}, enc 0x{0x0D+i:02X})", data))

    # Group 5: ー (tile 227, enc 0x03)
    bm = render_char(font, 'ー')
    all_tiles.append(("ー (tile 227, enc 0x03)", bitmap_to_2bpp(bm)))

    # Group 6: ゛ dakuten mark (tile 228, enc 0x01)
    # From assets/ui/gbs_player.gbr tile 20 (hand-designed)
    all_tiles.append(("゛ (tile 228, enc 0x01)", load_gbr_tile(gbr_path, 20)))

    # Group 7: ゜ handakuten mark (tile 229, enc 0x02)
    # From assets/ui/gbs_player.gbr tile 21 (hand-designed)
    all_tiles.append(("゜ (tile 229, enc 0x02)", load_gbr_tile(gbr_path, 21)))

    total = len(all_tiles)  # 46+9+46+9+1+1+1 = 113

    lines = []
    lines.append("// Auto-generated by tools/gen_jp_font.py  --  DO NOT EDIT")
    lines.append("// Pokemon Strict font, rendered from pkmn_s.ttf (2bpp, 8x8)")
    lines.append("//")
    lines.append("// Tile layout:")
    lines.append("//   117-162: base hiragana (46: あ-ん)")
    lines.append("//   163-171: small hiragana (9: ぁぃぅぇぉゃゅょっ)")
    lines.append("//   172-217: base katakana (46: ア-ン)")
    lines.append("//   218-226: small katakana (9: ァィゥェォャュョッ)")
    lines.append("//   227: ー, 228: ゛, 229: ゜")
    lines.append("//")
    lines.append("// Dakuten/handakuten are separate characters (1 tile each).")
    lines.append("// e.g. ガ = カ tile + ゛ tile (2 tiles)")
    lines.append("#ifndef JP_FONT_H")
    lines.append("#define JP_FONT_H")
    lines.append("")
    lines.append(f"#define JP_TILES_COUNT  {total}")
    lines.append(f"#define JP_TILES_START  117")
    lines.append(f"#define JP_HIRA_START   117")
    lines.append(f"#define JP_SMALL_HIRA_START 163")
    lines.append(f"#define JP_KATA_START   172")
    lines.append(f"#define JP_SMALL_KATA_START 218")
    lines.append(f"#define JP_LONG_VOWEL   227")
    lines.append(f"#define JP_DAKUTEN      228")
    lines.append(f"#define JP_HANDAKUTEN   229")
    lines.append("")
    lines.append("static const UINT8 jp_font_tiles[] = {")

    prev_section = ""
    sections = [
        (0,   46, "Base Hiragana (tiles 117-162)"),
        (46,  55, "Small Hiragana (tiles 163-171)"),
        (55, 101, "Base Katakana (tiles 172-217)"),
        (101, 110, "Small Katakana (tiles 218-226)"),
        (110, 113, "Special (ー ゛ ゜, tiles 227-229)"),
    ]
    sec_idx = 0
    for i, (label, data) in enumerate(all_tiles):
        if sec_idx < len(sections) and i == sections[sec_idx][0]:
            lines.append(f"    // === {sections[sec_idx][2]} ===")
            sec_idx += 1
        hex_str = ",".join(f"0x{b:02X}" for b in data)
        lines.append(f"    {hex_str}, // {label}")

    lines.append("};")
    lines.append("")
    lines.append("#endif // JP_FONT_H")
    lines.append("")

    out_path = os.path.join(os.path.dirname(__file__), "..", "src", "player", "jp_font.h")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[gen_jp_font] Written {out_path}: {total} tiles ({total*16} bytes)")

if __name__ == "__main__":
    generate_header()
