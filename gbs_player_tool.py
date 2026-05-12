#!/usr/bin/env python3
"""
GBS Player SAV Editor — Windows GUI tool for editing GBS Player save files.

Usage:
  python sav_editor.py
"""
import os
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox, ttk

try:
    import windnd
except Exception:
    windnd = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = None
    TkinterDnD = None


APP_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(APP_DIR, "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
ANDROID_APP_DIR = os.path.join(APP_DIR, "apps", "android")
CONFIG_FILENAME = "sav_editor_config.json"
LEGACY_CONFIG_PATH = os.path.join(APP_DIR, "build", CONFIG_FILENAME)

ANDROID_PACKAGE = "io.github.kleusbalut.gbsplayer.android"

BUILD_SETTING_LINKS = {
    "gbdk_path": ("gbdk_link", "https://github.com/gbdk-2020/gbdk-2020/releases"),
    "msys_bash_path": ("msys_link", "https://www.msys2.org/"),
    "java_home_path": ("android_studio_link", "https://developer.android.com/studio"),
    "adb_path": ("platform_tools_link", "https://developer.android.com/tools/releases/platform-tools"),
}


HIRAGANA = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
KATAKANA = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
SMALL_HIRA = "ぁぃぅぇぉゃゅょっ"
SMALL_KATA = "ァィゥェォャュョッ"

DAKUTEN_DECOMP = {}
for _c, _b in [
    ("が", "か"), ("ぎ", "き"), ("ぐ", "く"), ("げ", "け"), ("ご", "こ"),
    ("ざ", "さ"), ("じ", "し"), ("ず", "す"), ("ぜ", "せ"), ("ぞ", "そ"),
    ("だ", "た"), ("ぢ", "ち"), ("づ", "つ"), ("で", "て"), ("ど", "と"),
    ("ば", "は"), ("び", "ひ"), ("ぶ", "ふ"), ("べ", "へ"), ("ぼ", "ほ"),
    ("ゔ", "う"),
    ("ガ", "カ"), ("ギ", "キ"), ("グ", "ク"), ("ゲ", "ケ"), ("ゴ", "コ"),
    ("ザ", "サ"), ("ジ", "シ"), ("ズ", "ス"), ("ゼ", "セ"), ("ゾ", "ソ"),
    ("ダ", "タ"), ("ヂ", "チ"), ("ヅ", "ツ"), ("デ", "テ"), ("ド", "ト"),
    ("バ", "ハ"), ("ビ", "ヒ"), ("ブ", "フ"), ("ベ", "ヘ"), ("ボ", "ホ"),
    ("ヴ", "ウ"),
]:
    DAKUTEN_DECOMP[_c] = _b

HANDAKUTEN_DECOMP = {}
for _c, _b in [
    ("ぱ", "は"), ("ぴ", "ひ"), ("ぷ", "ふ"), ("ぺ", "へ"), ("ぽ", "ほ"),
    ("パ", "ハ"), ("ピ", "ヒ"), ("プ", "フ"), ("ペ", "ヘ"), ("ポ", "ホ"),
]:
    HANDAKUTEN_DECOMP[_c] = _b

_DAKUTEN_COMPOSE = {v: k for k, v in DAKUTEN_DECOMP.items()}
_HANDAKUTEN_COMPOSE = {v: k for k, v in HANDAKUTEN_DECOMP.items()}

SRAM_MAGIC = 0x4748
NAME_MAGIC = 0x4E4D
MAX_PL = 20
MAX_NAME = 32
SUPPORTED_SOURCE_EXTS = (".gbs", ".gbc", ".gb")
GENERIC_SOURCE_TITLES = {"Wrapped GB/GBC ROM", "Unknown Title", "Unknown"}
GENERIC_SOURCE_AUTHORS = {"Unknown Author", "Unknown"}

TRACK_TIME_LABELS = ["90s", "OFF", "30s", "1m", "2m", "3m", "5m"]
FADE_TIME_LABELS = ["OFF", "2s", "3s", "4s"]
REPEAT_LABELS = ["OFF", "ONE", "ALL"]
SILENCE_LABELS = ["5s", "OFF", "2s", "3s"]

LANG_JA = "ja"
LANG_EN = "en"

STRINGS = {
    "app_title": {"ja": "GBS Player ツール", "en": "GBS Player Tool"},
    "menu_file": {"ja": "ファイル", "en": "File"},
    "menu_lang": {"ja": "言語", "en": "Language"},
    "menu_build": {"ja": "ビルド", "en": "Build"},
    "open_gbs": {"ja": "GB/GBS/GBCを開く...", "en": "Open GB/GBS/GBC..."},
    "add_source": {"ja": "ソースを追加...", "en": "Add Source..."},
    "add_source_short": {"ja": "追加", "en": "Add"},
    "remove_source": {"ja": "ソースを一覧から削除", "en": "Remove Source"},
    "reload_sources": {"ja": "前回のソースを再読み込み", "en": "Reload Previous Sources"},
    "open_sav": {"ja": "SAVを開く...", "en": "Open SAV..."},
    "save_sav": {"ja": "SAVを保存", "en": "Save SAV"},
    "save_sav_as": {"ja": "SAVを別名保存...", "en": "Save SAV As..."},
    "import_names": {"ja": "曲名リストを読み込む...", "en": "Import Song List..."},
    "export_names": {"ja": "曲名リストを書き出す...", "en": "Export Song List..."},
    "exit": {"ja": "終了", "en": "Exit"},
    "lang_ja": {"ja": "日本語", "en": "Japanese"},
    "lang_en": {"ja": "英語", "en": "English"},
    "status_initial": {"ja": "GBSファイルを読み込んで開始してください", "en": "Load a GBS file to start"},
    "log": {"ja": "ログ", "en": "Log"},
    "songs": {"ja": "曲リスト", "en": "Songs"},
    "sources": {"ja": "ソース", "en": "Sources"},
    "build_log": {"ja": "ビルドログ", "en": "Build Log"},
    "playlist": {"ja": "プレイリスト", "en": "Playlist"},
    "settings": {"ja": "再生設定", "en": "Player Settings"},
    "edit_song": {"ja": "曲編集", "en": "Edit Song"},
    "title": {"ja": "タイトル:", "en": "Title:"},
    "author": {"ja": "作曲者:", "en": "Author:"},
    "col_num": {"ja": "#", "en": "#"},
    "col_name": {"ja": "曲名", "en": "Song Name"},
    "col_time": {"ja": "長さ", "en": "Time"},
    "col_song": {"ja": "曲#", "en": "Song#"},
    "name": {"ja": "曲名:", "en": "Name:"},
    "time": {"ja": "長さ:", "en": "Time:"},
    "set": {"ja": "設定", "en": "Set"},
    "add": {"ja": "ADD →", "en": "ADD →"},
    "del": {"ja": "← DEL", "en": "← DEL"},
    "up": {"ja": "上へ", "en": "Up"},
    "down": {"ja": "下へ", "en": "Down"},
    "remove": {"ja": "削除", "en": "Remove"},
    "clear": {"ja": "全消去", "en": "Clear"},
    "repeat": {"ja": "リピート:", "en": "Repeat:"},
    "fade": {"ja": "フェード:", "en": "Fade:"},
    "silence": {"ja": "無音検出:", "en": "Silence:"},
    "output": {"ja": "出力:", "en": "Output:"},
    "stereo": {"ja": "ステレオ", "en": "Stereo"},
    "mono": {"ja": "モノラル", "en": "Mono"},
    "unsaved_title": {"ja": "未保存の変更", "en": "Unsaved Changes"},
    "unsaved_msg": {
        "ja": "未保存の変更があります。終了前に保存しますか？",
        "en": "There are unsaved changes. Save before closing?",
    },
    "info": {"ja": "情報", "en": "Info"},
    "warning": {"ja": "警告", "en": "Warning"},
    "error": {"ja": "エラー", "en": "Error"},
    "confirm": {"ja": "確認", "en": "Confirm"},
    "load_gbs_first": {"ja": "曲数を取得するため、先にGBSファイルを読み込んでください。", "en": "Load a GBS file first to get song count."},
    "load_file_first": {"ja": "先にGBSファイルを読み込んでください。", "en": "Load a GBS file first."},
    "open_gbs_title": {"ja": "GB/GBS/GBCファイルを開く", "en": "Open GB/GBS/GBC file"},
    "open_sav_title": {"ja": "SAVファイルを開く", "en": "Open SAV file"},
    "save_sav_title": {"ja": "SAVファイルを保存", "en": "Save SAV file"},
    "import_names_title": {"ja": "曲名リストを読み込む", "en": "Import Song List"},
    "export_names_title": {"ja": "曲名リストを書き出す", "en": "Export Song List"},
    "no_companion_gbs": {
        "ja": "対応する .gbs ファイルが見つかりません。\n曲数取得のため .gbs を直接開いてください。",
        "en": "No companion .gbs file found.\nPlease open the .gbs file directly to get song count info.",
    },
    "playlist_full": {
        "ja": f"プレイリストは上限です (最大 {MAX_PL} 曲)",
        "en": f"Playlist is full (max {MAX_PL} songs)",
    },
    "clear_playlist": {"ja": "プレイリストを全消去しますか？", "en": "Clear the entire playlist?"},
    "imported_names": {"ja": "{count}曲の情報を読み込みました", "en": "Imported {count} song entries"},
    "exported_to": {"ja": "書き出し: {path}", "en": "Exported to {path}"},
    "song_names_loaded": {"ja": "曲名リストを読み込みました: {name}", "en": "Song list loaded: {name}"},
    "saved": {"ja": "保存: {path}", "en": "Saved: {path}"},
    "sav_loaded": {"ja": "SAV読込: {name}", "en": "SAV loaded: {name}"},
    "sav_auto_loaded": {"ja": "SAV自動読込: {name}", "en": "Auto-loaded SAV: {name}"},
    "using_rom_defaults": {"ja": "ROM既定値を使用: {name}", "en": "Using ROM defaults: {name}"},
    "build_selected": {"ja": "選択ソースをGBCビルド", "en": "Build Selected GBC"},
    "build_selected_short": {"ja": "ビルド", "en": "Build"},
    "build_selected_short_tip": {
        "ja": "選択中のソースのファイルをプレイヤーROMとして個別にビルドして保存場所を開きます。",
        "en": "Build the selected source file individually as a player ROM and open its output folder.",
    },
    "build_all": {"ja": "全ソースをGBCビルド", "en": "Build All GBC"},
    "android_assets_selected": {"ja": "選択ソースをAndroid assetsへ反映", "en": "Update Selected Android Assets"},
    "android_assets_all": {"ja": "全ソースをAndroid assetsへ反映", "en": "Update All Android Assets"},
    "android_apk": {"ja": "Android APKをビルド", "en": "Build Android APK"},
    "android_install": {"ja": "Android APKを実機へ転送", "en": "Install Android APK to Device"},
    "android_build_install": {"ja": "Android APKをビルドして実機へ転送", "en": "Build and Install Android APK"},
    "android_build_install_tip": {
        "ja": "AndroidPlayerのみをビルドして、すでにビルド済みのプレイヤーROMを梱包して実機へ転送します。",
        "en": "Build only AndroidPlayer, package the already-built player ROM, and transfer it to the device.",
    },
    "android_build_install_all": {"ja": "すべてをビルドしてインストール", "en": "Build All and Install"},
    "android_build_install_all_tip": {
        "ja": "プレイヤーROM及びAndroidPlayerをすべてビルドして実機へ転送します。",
        "en": "Build all player ROMs and AndroidPlayer, then transfer them to the device.",
    },
    "android_pull_sav": {"ja": "端末から読込", "en": "Pull Device SAV"},
    "android_push_sav": {"ja": "端末へ反映", "en": "Push SAV to Device"},
    "android_sync_missing": {
        "ja": "端末上のSAVが見つかりません。Androidアプリで対象ROMを一度起動してから再実行してください。",
        "en": "Device SAV was not found. Launch this ROM once in the Android app, then try again.",
    },
    "android_sync_pull_done": {"ja": "端末SAVを読み込みました: {rom_id}", "en": "Pulled device SAV: {rom_id}"},
    "android_sync_push_done": {"ja": "端末へSAVを反映しました: {rom_id}", "en": "Pushed SAV to device: {rom_id}"},
    "save_sync": {"ja": "セーブデータ同期", "en": "Save Sync"},
    "auto_sync": {"ja": "自動同期", "en": "Auto Sync"},
    "overwrite_save": {"ja": "セーブデータ上書き", "en": "Overwrite Save"},
    "auto_sync_tip": {
        "ja": "チェック時、起動時に端末SAVを自動的に読み込みます。動作は「端末SAVを読込」と同じです。",
        "en": "When checked, device SAV is pulled automatically on startup. Same behavior as Pull Device SAV.",
    },
    "overwrite_save_tip": {
        "ja": "チェック時、APKインストール時に端末SAVを自動的に上書きします。動作は「端末へSAV反映」と同じです。",
        "en": "When checked, device SAV is overwritten automatically during APK install. Same behavior as Push SAV to Device.",
    },
    "adb_device": {"ja": "インストール先:", "en": "Install to:"},
    "adb_no_device": {
        "ja": "デバイスが見つかりません。 ケーブル接続やデバッグ端末登録を確認して、Unityなど、Android向けビルドができるツールを終了してから「更新」を押してデバイスを選択してください。",
        "en": "No device found. Check the cable and device connection. Close Unity or other Android build tools, then press Refresh and select a device.",
    },
    "refresh_adb": {"ja": "更新", "en": "Refresh"},
    "build_paths": {"ja": "ビルド設定", "en": "Build Settings"},
    "browse": {"ja": "参照", "en": "Browse"},
    "gbdk_path": {"ja": "GBDK:", "en": "GBDK:"},
    "msys_bash_path": {"ja": "MSYS2 bash:", "en": "MSYS2 bash:"},
    "java_home_path": {"ja": "JAVA_HOME:", "en": "JAVA_HOME:"},
    "adb_path": {"ja": "ADB:", "en": "ADB:"},
    "close": {"ja": "閉じる", "en": "Close"},
    "gbdk_desc": {"ja": "GB/GBC ROMをビルドするGBDK-2020のルートフォルダです。", "en": "Root folder of GBDK-2020 used to build GB/GBC ROMs."},
    "msys_bash_desc": {"ja": "任意設定です。GBDKに /c/... 形式のMSYS2パスを指定した場合だけ、このbash.exe経由でmakeします。未設定または C:/... 形式では通常のWindows makeを使います。", "en": "Optional. Used only when GBDK is an MSYS2-style /c/... path. Empty or C:/... paths use normal Windows make."},
    "java_home_desc": {"ja": "Android APKビルドに使うJDK/JBRです。Android Studio同梱JBRを推奨します。", "en": "JDK/JBR for Android APK builds. Android Studio bundled JBR is recommended."},
    "adb_desc": {"ja": "実機へAPKを転送するadb.exeです。Android SDK Platform-Toolsに含まれます。", "en": "adb.exe used to install APKs to devices. Included in Android SDK Platform-Tools."},
    "gbdk_link": {"ja": "GBDK-2020 Releases", "en": "GBDK-2020 Releases"},
    "msys_link": {"ja": "MSYS2 Download", "en": "MSYS2 Download"},
    "android_studio_link": {"ja": "Android Studio Download", "en": "Android Studio Download"},
    "platform_tools_link": {"ja": "SDK Platform-Tools", "en": "SDK Platform-Tools"},
    "build_settings": {"ja": "ビルド設定...", "en": "Build Settings..."},
    "build_started": {"ja": "ビルド開始: {name}", "en": "Build started: {name}"},
    "build_done": {"ja": "ビルド完了: {path}", "en": "Build done: {path}"},
    "build_failed": {"ja": "ビルド失敗: {name}", "en": "Build failed: {name}"},
    "no_source_selected": {"ja": "ソースを選択してください。", "en": "Select a source first."},
    "gbdk_prompt": {"ja": "GBDKパスを入力してください", "en": "Enter GBDK path"},
    "java_home_prompt": {"ja": "Android Studio JBR/JDKのJAVA_HOMEを入力してください", "en": "Enter JAVA_HOME for Android build"},
    "msys_bash_prompt": {"ja": "MSYS2 bash.exe のパスを入力してください", "en": "Enter MSYS2 bash.exe path"},
    "adb_prompt": {"ja": "adb.exe のパスを入力してください", "en": "Enter adb.exe path"},
    "status_loaded": {
        "ja": "{title} / {author} | {num}曲 | load=0x{load:04X}{sav}",
        "en": "{title} by {author} | {num} songs | load=0x{load:04X}{sav}",
    },
    "status_sav_suffix": {"ja": " | SAV: {name}", "en": " | SAV: {name}"},
    "hint_song_list": {
        "ja": "曲名リストは `曲名<TAB>長さ` 形式に対応します。旧来の1行1曲名も読めます。",
        "en": "Song list supports `name<TAB>time`. Legacy one-name-per-line files still work.",
    },
}


def android_rom_id_from_path(path):
    name = os.path.splitext(os.path.basename(path))[0]
    rom_id = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return rom_id or "gbs_player"


def utf8_to_custom(text, max_len=31):
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
                result.append(0x02)
        elif ch in DAKUTEN_DECOMP:
            base = DAKUTEN_DECOMP[ch]
            if base in HIRAGANA:
                result.append(0x80 + HIRAGANA.index(base))
            elif base in KATAKANA:
                result.append(0xB0 + KATAKANA.index(base))
            if len(result) < max_len:
                result.append(0x01)
        elif ch == "\u3099" or ch == "\u309B" or ch == "\uFF9E":
            result.append(0x01)
        elif ch == "\u309A" or ch == "\u309C" or ch == "\uFF9F":
            result.append(0x02)
        elif ch == "ー" or ch == "\uFF70":
            result.append(0x03)
        elif ch in SMALL_HIRA:
            result.append(0x04 + SMALL_HIRA.index(ch))
        elif ch in SMALL_KATA:
            result.append(0x0D + SMALL_KATA.index(ch))
        elif ch in HIRAGANA:
            result.append(0x80 + HIRAGANA.index(ch))
        elif ch in KATAKANA:
            result.append(0xB0 + KATAKANA.index(ch))
    while len(result) < max_len + 1:
        result.append(0)
    return result[:max_len + 1]


def custom_encoded_len(encoded):
    count = 0
    for b in encoded:
        if b == 0:
            break
        count += 1
    return count


def sanitize_song_name(text, max_len=31):
    result = []
    for ch in text:
        encoded = utf8_to_custom(ch, max_len)
        if encoded and encoded[0] != 0:
            trial = "".join(result) + ch
            if custom_encoded_len(utf8_to_custom(trial, max_len)) <= max_len:
                result.append(ch)
    return "".join(result)


def _byte_to_base_char(b):
    if 0x80 <= b <= 0xAD:
        idx = b - 0x80
        return HIRAGANA[idx] if idx < len(HIRAGANA) else None
    if 0xB0 <= b <= 0xDD:
        idx = b - 0xB0
        return KATAKANA[idx] if idx < len(KATAKANA) else None
    return None


def custom_to_utf8(data):
    result = []
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0:
            break
        next_b = data[i + 1] if i + 1 < len(data) else 0
        if next_b == 0x01:
            ch = _byte_to_base_char(b)
            if ch and ch in _DAKUTEN_COMPOSE:
                result.append(_DAKUTEN_COMPOSE[ch])
                i += 2
                continue
        elif next_b == 0x02:
            ch = _byte_to_base_char(b)
            if ch and ch in _HANDAKUTEN_COMPOSE:
                result.append(_HANDAKUTEN_COMPOSE[ch])
                i += 2
                continue
        if 0x20 <= b <= 0x7E:
            result.append(chr(b))
        elif b == 0x01:
            result.append("\u309B")
        elif b == 0x02:
            result.append("\u309C")
        elif b == 0x03:
            result.append("ー")
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


def parse_gbs(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:3] != b"GBS":
        raise ValueError(f"{path} is not a GBS file")
    h = struct.unpack_from("<BBBHHHHBB", raw, 3)
    ver, num, first, load, init, play, stack, tmod, tctl = h

    def s(off):
        return raw[off:off + 32].rstrip(b"\x00").decode("ascii", errors="replace")

    return {
        "num_songs": num,
        "first_song": first,
        "load_addr": load,
        "init_addr": init,
        "play_addr": play,
        "stack_ptr": stack,
        "timer_mod": tmod,
        "timer_ctl": tctl,
        "title": s(0x10),
        "author": s(0x30),
        "copyright": s(0x50),
    }


def parse_source_info(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".gbs":
        info = parse_gbs(path)
        info["source_path"] = path
        return info

    if ext in (".gb", ".gbc"):
        try:
            import build as build_helper
            info = build_helper.parse_gbs(path)
            info["source_path"] = path
            return info
        except SystemExit as e:
            raise ValueError(str(e))

    raise ValueError(f"Unsupported source file: {path}")


def safe_id_from_path(path):
    name = os.path.splitext(os.path.basename(path))[0]
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", name).strip("._-")
    digest = hashlib.sha1(os.path.abspath(path).encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"{safe or 'source'}-{digest}"


def source_fallback_title(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem or os.path.basename(path)


def source_default_title(entry):
    title = entry.gbs_info.get("title") if entry else ""
    if not title or title in GENERIC_SOURCE_TITLES:
        return source_fallback_title(entry.source_path) if entry else ""
    return title


def source_default_author(entry):
    author = entry.gbs_info.get("author") if entry else ""
    if not author or author in GENERIC_SOURCE_AUTHORS:
        return ""
    return author


def source_display_title(entry):
    if entry and entry.sav and entry.sav.custom_title:
        return entry.sav.custom_title
    return source_default_title(entry)


def source_display_author(entry):
    if entry and entry.sav and entry.sav.custom_author:
        return entry.sav.custom_author
    return source_default_author(entry)


def win_to_msys_path(path):
    path = os.path.abspath(path).replace("\\", "/")
    if len(path) >= 2 and path[1] == ":":
        return "/" + path[0].lower() + path[2:]
    return path


def quote_sh(text):
    return "'" + text.replace("'", "'\"'\"'") + "'"


def parse_song_list_line(line):
    text = line.rstrip("\r\n")
    stripped = text.strip()
    if not stripped:
        return "", None
    parts = text.split("\t", 1)
    if len(parts) == 2 and parts[1].strip() in TRACK_TIME_LABELS:
        return parts[0].strip(), TRACK_TIME_LABELS.index(parts[1].strip())
    return text.strip(), None


def parse_track_time_value(text):
    value = str(text).strip()
    if value in TRACK_TIME_LABELS:
        return TRACK_TIME_LABELS.index(value)
    lower = value.lower()
    if lower == "off":
        return TRACK_TIME_LABELS.index("OFF")
    if not lower:
        return None
    explicit_seconds = lower.endswith("s")
    if explicit_seconds:
        lower = lower[:-1]
    multiplier = 1
    if lower.endswith("m"):
        multiplier = 60
        lower = lower[:-1]
    try:
        number = int(lower)
        if not explicit_seconds and multiplier == 1:
            if number == 0:
                return TRACK_TIME_LABELS.index("OFF")
            if number in (1, 2, 3, 5):
                multiplier = 60
        seconds = number * multiplier
    except ValueError:
        return None
    seconds_to_label = {
        30: "30s",
        60: "1m",
        90: "90s",
        120: "2m",
        180: "3m",
        300: "5m",
    }
    label = seconds_to_label.get(seconds)
    if label:
        return TRACK_TIME_LABELS.index(label)
    return None


def parse_drop_files(data):
    if isinstance(data, (list, tuple)):
        return [str(item) for item in data]
    text = str(data)
    paths = []
    current = []
    in_brace = False
    for ch in text:
        if ch == "{":
            in_brace = True
            current = []
        elif ch == "}" and in_brace:
            in_brace = False
            paths.append("".join(current))
            current = []
        elif ch.isspace() and not in_brace:
            if current:
                paths.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        paths.append("".join(current))
    return paths


def user_config_dir():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        if base:
            return os.path.join(base, "GBS Player Tool")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "GBS Player Tool")
    base = os.environ.get("XDG_CONFIG_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "gbs-player-tool")


def config_file_path():
    return os.path.join(user_config_dir(), CONFIG_FILENAME)


def source_path_key(path):
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def load_song_list(path, num_songs):
    names = [""] * num_songs
    times = [None] * num_songs
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    song_index = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            key_value = stripped[1:].split(":", 1)
            if len(key_value) == 2 and key_value[0].strip().lower() in ("title", "author", "copyright"):
                continue
        if song_index >= num_songs:
            break
        names[song_index], times[song_index] = parse_song_list_line(line)
        song_index += 1
    return names, times, lines


class SaveData:
    def __init__(self, num_songs=1):
        self.num_songs = num_songs
        self.magic = SRAM_MAGIC
        self.count = 0
        self.tracks = [0] * MAX_PL
        self.repeat = 0
        self.fade_time = 2
        self.mono = 0
        self.silence = 0
        self.track_time = [0] * num_songs
        self.name_magic = 0
        self.song_names = [""] * num_songs
        self.custom_title = ""
        self.custom_author = ""

    def _normalize(self):
        self.count = max(0, min(self.count, MAX_PL))
        self.repeat = self.repeat if 0 <= self.repeat < len(REPEAT_LABELS) else 0
        self.fade_time = self.fade_time if 0 <= self.fade_time < len(FADE_TIME_LABELS) else 2
        self.mono = 1 if self.mono else 0
        self.silence = self.silence if 0 <= self.silence < len(SILENCE_LABELS) else 0
        self.tracks = [(t if 0 <= t < self.num_songs else 0) for t in self.tracks[:MAX_PL]]
        while len(self.tracks) < MAX_PL:
            self.tracks.append(0)
        self.track_time = [(t if 0 <= t < len(TRACK_TIME_LABELS) else 0) for t in self.track_time[:self.num_songs]]
        while len(self.track_time) < self.num_songs:
            self.track_time.append(0)

    def load(self, path):
        with open(path, "rb") as f:
            raw = f.read()
        if len(raw) < 26:
            raise ValueError("SAV file too small")
        off = 0
        self.magic = struct.unpack_from("<H", raw, off)[0]
        off += 2
        self.count = raw[off]
        off += 1
        self.tracks = list(raw[off:off + MAX_PL])
        off += MAX_PL
        self.repeat = raw[off]
        off += 1
        self.fade_time = raw[off]
        off += 1
        self.mono = raw[off]
        off += 1
        self.silence = raw[off] if off < len(raw) else 0
        off += 1
        n = min(self.num_songs, len(raw) - off)
        self.track_time = list(raw[off:off + n])
        while len(self.track_time) < self.num_songs:
            self.track_time.append(0)
        off += self.num_songs
        self.name_magic = 0
        self.song_names = [""] * self.num_songs
        self.custom_title = ""
        self.custom_author = ""
        if off + 2 <= len(raw):
            nm = struct.unpack_from("<H", raw, off)[0]
            off += 2
            if nm == NAME_MAGIC:
                self.name_magic = NAME_MAGIC
                for i in range(self.num_songs):
                    if off + MAX_NAME <= len(raw):
                        self.song_names[i] = custom_to_utf8(raw[off:off + MAX_NAME])
                        off += MAX_NAME
                if off + 32 <= len(raw):
                    self.custom_title = custom_to_utf8(raw[off:off + 32])
                    off += 32
                if off + 32 <= len(raw):
                    self.custom_author = custom_to_utf8(raw[off:off + 32])
                    off += 32
        self._normalize()

    def save(self, path):
        data = bytearray()
        data += struct.pack("<H", SRAM_MAGIC)
        data.append(self.count)
        for i in range(MAX_PL):
            data.append(self.tracks[i] if i < len(self.tracks) else 0)
        data.append(self.repeat)
        data.append(self.fade_time)
        data.append(self.mono)
        data.append(self.silence)
        for i in range(self.num_songs):
            data.append(self.track_time[i] if i < len(self.track_time) else 0)
        has_names = any(n != "" for n in self.song_names) or self.custom_title or self.custom_author
        if has_names:
            data += struct.pack("<H", NAME_MAGIC)
            for i in range(self.num_songs):
                data += bytes(utf8_to_custom(self.song_names[i] if i < len(self.song_names) else "", 31))
            data += bytes(utf8_to_custom(self.custom_title, 31))
            data += bytes(utf8_to_custom(self.custom_author, 31))
        else:
            data += struct.pack("<H", 0)
        while len(data) < 8192:
            data.append(0)
        with open(path, "wb") as f:
            f.write(data[:8192])

    def state_tuple(self):
        return (
            self.count,
            tuple(self.tracks[:MAX_PL]),
            self.repeat,
            self.fade_time,
            self.mono,
            self.silence,
            tuple(self.track_time[:self.num_songs]),
            self.name_magic,
            tuple(self.song_names[:self.num_songs]),
            self.custom_title,
            self.custom_author,
        )


@dataclass
class SourceEntry:
    source_path: str
    gbs_info: dict
    sav: SaveData
    sav_path: str = None
    dirty: bool = False
    last_selected_track: int = 0
    build_output: str = None
    metadata_output: str = None
    source_id: str = ""
    messages: list = field(default_factory=list)

    @property
    def display_name(self):
        title = source_display_title(self)
        return f"{title} ({os.path.basename(self.source_path)})"


class ToolTip:
    def __init__(self, widget, text_func):
        self.widget = widget
        self.text_func = text_func
        self.window = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _show(self, event=None):
        self._hide()
        text = self.text_func() if callable(self.text_func) else str(self.text_func)
        if not text:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.window, text=text, justify=tk.LEFT, relief=tk.SOLID, borderwidth=1, padding=(6, 3), wraplength=360)
        label.pack()

    def _hide(self, event=None):
        if self.window is not None:
            self.window.destroy()
            self.window = None


class SavEditorApp:
    def __init__(self, root):
        self.root = root
        self.lang = LANG_JA
        self.gbs_info = None
        self.sav = None
        self.sav_path = None
        self.gbs_path = None
        self.entries = []
        self.current_index = None
        self.config_path = config_file_path()
        self.legacy_config_path = LEGACY_CONFIG_PATH
        self._loaded_config_path = None
        self.config = self._load_config()
        self.gbdk_path = self.config.get("gbdk_path", "C:/dev/gbdk")
        self.msys_bash_path = self.config.get("msys_bash_path", "")
        self.java_home = self.config.get("java_home", "C:/Program Files/Android/Android Studio/jbr")
        self.adb_path = self.config.get("adb_path", "adb")
        self.adb_device_serial = self.config.get("adb_device_serial", "")
        self.adb_devices = []
        self.adb_device_choices = {}
        self._startup_auto_sync_done = False
        self.gbdk_var = tk.StringVar(value=self.gbdk_path)
        self.msys_bash_var = tk.StringVar(value=self.msys_bash_path)
        self.java_home_var = tk.StringVar(value=self.java_home)
        self.adb_path_var = tk.StringVar(value=self.adb_path)
        self.auto_sync_var = tk.BooleanVar(value=bool(self.config.get("auto_sync_sav", False)))
        self.overwrite_save_var = tk.BooleanVar(value=bool(self.config.get("overwrite_device_sav", False)))
        self._settings_window = None
        self._settings_path_rows = []
        self._build_running = False
        self._dirty = False
        self._edit_entry = None
        self._edit_item = None
        self._edit_column = None
        self._last_selected = None
        self._pl_drag_from = None
        self._pl_drag_to = None
        self._song_drag_index = None
        self._source_drag_from = None
        self._source_drag_to = None
        self._drag_label = None
        self._drag_label_var = tk.StringVar()
        self._status_base_text = ""

        self._i18n_vars = {}
        self._static_labels = []
        self._lang_menu = None
        self._lang_var = tk.StringVar(value=self.lang)
        self._loading_settings = False

        self.root.geometry("1180x720")
        self.root.minsize(1080, 620)

        self._build_menu()
        self._build_ui()
        self._apply_language()
        self._update_state()
        self._restore_previous_sources()
        if self._loaded_config_path == self.legacy_config_path:
            self._save_config()
        self.root.after(300, self._refresh_adb_devices)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_config(self):
        for path in (self.config_path, self.legacy_config_path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._loaded_config_path = path
                    return data
            except Exception:
                pass
        return {}

    def _save_config(self):
        self._sync_build_settings_vars()
        data = dict(self.config)
        data["gbdk_path"] = self.gbdk_path
        data["msys_bash_path"] = self.msys_bash_path
        data["java_home"] = self.java_home
        data["adb_path"] = self.adb_path
        data["adb_device_serial"] = self.adb_device_serial
        if threading.current_thread() is threading.main_thread():
            data["auto_sync_sav"] = bool(self.auto_sync_var.get())
            data["overwrite_device_sav"] = bool(self.overwrite_save_var.get())
        data["open_sources"] = [
            {
                "source": e.source_path,
                "sav": e.sav_path,
                "last_selected_track": e.last_selected_track,
            }
            for e in self.entries
        ]
        if self.current_index is not None and 0 <= self.current_index < len(self.entries):
            data["last_active_source"] = self.entries[self.current_index].source_path
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.config = data
        except Exception:
            pass

    def tr(self, key, **kwargs):
        value = STRINGS[key][self.lang]
        return value.format(**kwargs) if kwargs else value

    def _tvar(self, key):
        var = tk.StringVar()
        self._i18n_vars[key] = var
        return var

    def _add_label(self, widget, key):
        self._static_labels.append((widget, key))

    def _set_status(self, text, remember=True):
        if remember:
            self._status_base_text = text
        self.status_var.set(text)

    def _post_status(self, text, remember=True):
        self.root.after(0, lambda: self._set_status(text, remember=remember))

    def _status_loaded_text(self):
        if not self.gbs_info:
            return self.tr("status_initial")
        info = self.gbs_info
        entry = self._current_entry()
        sav_suffix = ""
        if self.sav_path:
            sav_suffix = self.tr("status_sav_suffix", name=os.path.basename(self.sav_path))
        return self.tr(
            "status_loaded",
            title=source_display_title(entry) if entry else info["title"],
            author=source_display_author(entry) if entry else info["author"],
            num=info["num_songs"],
            load=info["load_addr"],
            sav=sav_suffix,
        )

    def _mark_dirty(self):
        self._dirty = True
        if self.current_index is not None and 0 <= self.current_index < len(self.entries):
            self.entries[self.current_index].dirty = True
            self._refresh_sources()

    def _on_metadata_change(self, *_args):
        if self._loading_settings or not self.sav:
            return
        if self._sync_metadata_fields():
            self._mark_dirty()
        self._set_status(self._status_loaded_text())

    def _on_close(self):
        self._store_active_entry()
        if self._dirty and self.sav:
            ans = messagebox.askyesnocancel(self.tr("unsaved_title"), self.tr("unsaved_msg"))
            if ans is None:
                return
            if ans:
                self._save_sav()
        self._save_config()
        self.root.destroy()

    def _build_menu(self):
        self.menubar = tk.Menu(self.root)
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.file_menu.add_command(label=self.tr("open_gbs"), command=self._open_gbs, accelerator="Ctrl+O")
        self.file_menu.add_command(label=self.tr("add_source"), command=self._open_gbs)
        self.file_menu.add_command(label=self.tr("remove_source"), command=self._remove_current_source)
        self.file_menu.add_command(label=self.tr("reload_sources"), command=self._restore_previous_sources)
        self.file_menu.add_command(label=self.tr("open_sav"), command=self._open_sav)
        self.file_menu.add_command(label=self.tr("save_sav"), command=self._save_sav, accelerator="Ctrl+S")
        self.file_menu.add_command(label=self.tr("save_sav_as"), command=self._save_sav_as)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self.tr("import_names"), command=self._import_names)
        self.file_menu.add_command(label=self.tr("export_names"), command=self._export_names)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self.tr("exit"), command=self._on_close)
        self.menubar.add_cascade(label=self.tr("menu_file"), menu=self.file_menu)

        self.build_menu = tk.Menu(self.menubar, tearoff=0)
        self.build_menu.add_command(label=self.tr("build_settings"), command=self._edit_build_settings)
        self.build_menu.add_separator()
        self.build_menu.add_command(label=self.tr("build_selected"), command=lambda: self._build_sources([self._current_entry()], android_assets=False))
        self.build_menu.add_command(label=self.tr("build_all"), command=lambda: self._build_sources(self.entries, android_assets=False))
        self.build_menu.add_separator()
        self.build_menu.add_command(label=self.tr("android_assets_selected"), command=lambda: self._build_sources([self._current_entry()], android_assets=True))
        self.build_menu.add_command(label=self.tr("android_assets_all"), command=lambda: self._build_sources(self.entries, android_assets=True))
        self.build_menu.add_separator()
        self.build_menu.add_command(label=self.tr("android_apk"), command=self._build_android_apk)
        self.build_menu.add_command(label=self.tr("android_install"), command=self._install_android_apk)
        self.build_menu.add_command(label=self.tr("android_build_install"), command=lambda: self._build_android_apk(install_after=True))
        self.build_menu.add_command(label=self.tr("android_build_install_all"), command=self._build_all_and_install)
        self.build_menu.add_separator()
        self.build_menu.add_command(label=self.tr("android_pull_sav"), command=self._pull_android_sav)
        self.build_menu.add_command(label=self.tr("android_push_sav"), command=self._push_android_sav)
        self.menubar.add_cascade(label=self.tr("menu_build"), menu=self.build_menu)

        self._lang_menu = tk.Menu(self.menubar, tearoff=0)
        self._lang_menu.add_radiobutton(label=self.tr("lang_ja"), variable=self._lang_var, value=LANG_JA, command=lambda: self._set_language(LANG_JA))
        self._lang_menu.add_radiobutton(label=self.tr("lang_en"), variable=self._lang_var, value=LANG_EN, command=lambda: self._set_language(LANG_EN))
        self.menubar.add_cascade(label=self.tr("menu_lang"), menu=self._lang_menu)

        self.root.config(menu=self.menubar)
        self.root.bind("<Control-o>", lambda e: self._open_gbs())
        self.root.bind("<Control-s>", lambda e: self._save_sav())

    def _build_ui(self):
        self.status_var = tk.StringVar()

        status_frame = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        status_frame.columnconfigure(0, weight=1)
        status = ttk.Label(status_frame, textvariable=self.status_var, anchor=tk.W)
        status.grid(row=0, column=0, sticky="ew", padx=(2, 6))
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, maximum=100, length=180)
        self.progress_bar.grid(row=0, column=1, sticky="e", padx=(0, 4), pady=1)

        log_area = ttk.Frame(self.root)
        log_area.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(0, 5))
        log_area.columnconfigure(0, weight=1)
        log_area.columnconfigure(1, weight=0)

        self.log_notebook = ttk.Notebook(log_area)
        self.log_notebook.grid(row=0, column=0, sticky="ew")
        self.general_log_frame = ttk.Frame(self.log_notebook)
        self.build_log_frame = ttk.Frame(self.log_notebook)
        self.log_notebook.add(self.general_log_frame, text=self.tr("log"))
        self.log_notebook.add(self.build_log_frame, text=self.tr("build_log"))
        for frame in (self.general_log_frame, self.build_log_frame):
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
        self.general_log_text = tk.Text(self.general_log_frame, height=5, wrap="word", state="disabled")
        self.general_log_text.grid(row=0, column=0, sticky="nsew")
        general_scroll = ttk.Scrollbar(self.general_log_frame, orient=tk.VERTICAL, command=self.general_log_text.yview)
        self.general_log_text.configure(yscrollcommand=general_scroll.set)
        general_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text = tk.Text(self.build_log_frame, height=5, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(self.build_log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.grid(row=0, column=1, sticky="ns")

        android_panel = ttk.Frame(log_area)
        android_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        android_panel.columnconfigure(0, weight=1)
        adb_frame = ttk.Frame(android_panel)
        adb_frame.grid(row=0, column=0, sticky="ew")
        adb_frame.columnconfigure(1, weight=1)
        self.adb_device_label = ttk.Label(adb_frame, textvariable=self._tvar("adb_device"))
        self.adb_device_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 4))
        self.adb_device_var = tk.StringVar(value=self.adb_device_serial)
        self.adb_device_combo = ttk.Combobox(adb_frame, textvariable=self.adb_device_var, state="readonly", width=22)
        self.adb_device_combo.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.adb_device_combo.bind("<<ComboboxSelected>>", self._on_adb_device_selected)
        self.refresh_adb_btn = ttk.Button(adb_frame, command=self._refresh_adb_devices, width=6)
        self.refresh_adb_btn.grid(row=0, column=2, sticky="e")

        install_btns = ttk.Frame(android_panel)
        install_btns.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        install_btns.columnconfigure(0, weight=1)
        self.build_source_btn = ttk.Button(install_btns, command=lambda: self._build_sources([self._current_entry()], android_assets=False, open_folder=True))
        self.build_source_btn.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        ToolTip(self.build_source_btn, lambda: self.tr("build_selected_short_tip"))
        self.build_install_btn = ttk.Button(install_btns, command=lambda: self._build_android_apk(install_after=True))
        self.build_install_btn.grid(row=1, column=0, sticky="ew", pady=(0, 3))
        ToolTip(self.build_install_btn, lambda: self.tr("android_build_install_tip"))
        self.build_install_all_btn = ttk.Button(install_btns, command=self._build_all_and_install)
        self.build_install_all_btn.grid(row=2, column=0, sticky="ew")
        ToolTip(self.build_install_all_btn, lambda: self.tr("android_build_install_all_tip"))

        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        main_frame.columnconfigure(0, weight=0)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        sources_frame = ttk.LabelFrame(main_frame)
        sources_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.sources_frame = sources_frame
        sources_frame.rowconfigure(0, weight=1)
        sources_frame.columnconfigure(0, weight=1)
        self.source_list = tk.Listbox(sources_frame, exportselection=False, width=30)
        self.source_list.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 2))
        source_scroll = ttk.Scrollbar(sources_frame, orient=tk.VERTICAL, command=self.source_list.yview)
        self.source_list.configure(yscrollcommand=source_scroll.set)
        source_scroll.grid(row=0, column=1, sticky="ns", pady=(5, 2))
        self.source_list.bind("<<ListboxSelect>>", self._on_source_select)
        self.source_list.bind("<ButtonPress-1>", self._on_source_press)
        self.source_list.bind("<B1-Motion>", self._on_source_drag)
        self.source_list.bind("<ButtonRelease-1>", self._on_source_drop)
        self._setup_source_drop()

        source_btns = ttk.Frame(sources_frame)
        source_btns.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=(2, 5))
        for col in range(2):
            source_btns.columnconfigure(col, weight=1, uniform="source_btn")
        self.add_source_btn = ttk.Button(source_btns, command=self._open_gbs)
        self.add_source_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.remove_source_btn = ttk.Button(source_btns, command=self._remove_current_source)
        self.remove_source_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        sync_frame = ttk.LabelFrame(sources_frame)
        sync_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(2, 5))
        self.sync_frame = sync_frame
        sync_frame.columnconfigure(0, weight=1)
        sync_frame.columnconfigure(1, weight=1)
        self.auto_sync_check = ttk.Checkbutton(sync_frame, variable=self.auto_sync_var, command=self._on_sync_option_change)
        self.auto_sync_check.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 2))
        ToolTip(self.auto_sync_check, lambda: self.tr("auto_sync_tip"))
        self.overwrite_save_check = ttk.Checkbutton(sync_frame, variable=self.overwrite_save_var, command=self._on_sync_option_change)
        self.overwrite_save_check.grid(row=0, column=1, sticky="w", padx=5, pady=(5, 2))
        ToolTip(self.overwrite_save_check, lambda: self.tr("overwrite_save_tip"))
        self.pull_android_sav_btn = ttk.Button(sync_frame, command=self._pull_android_sav)
        self.pull_android_sav_btn.grid(row=1, column=0, sticky="ew", padx=(5, 3), pady=(3, 5))
        self.push_android_sav_btn = ttk.Button(sync_frame, command=self._push_android_sav)
        self.push_android_sav_btn.grid(row=1, column=1, sticky="ew", padx=(3, 5), pady=(3, 5))

        left_frame = ttk.LabelFrame(main_frame)
        left_frame.grid(row=0, column=1, sticky="nsew")
        self.left_frame = left_frame

        meta_frame = ttk.Frame(left_frame)
        meta_frame.pack(fill=tk.X, padx=5, pady=2)
        lbl = ttk.Label(meta_frame, textvariable=self._tvar("title"))
        lbl.grid(row=0, column=0, sticky=tk.W)
        self.title_label = lbl
        self.title_var = tk.StringVar()
        self.title_var.trace_add("write", self._on_metadata_change)
        ttk.Entry(meta_frame, textvariable=self.title_var, width=30).grid(row=0, column=1, sticky=tk.EW, padx=2)
        lbl = ttk.Label(meta_frame, textvariable=self._tvar("author"))
        lbl.grid(row=1, column=0, sticky=tk.W)
        self.author_label = lbl
        self.author_var = tk.StringVar()
        self.author_var.trace_add("write", self._on_metadata_change)
        ttk.Entry(meta_frame, textvariable=self.author_var, width=30).grid(row=1, column=1, sticky=tk.EW, padx=2)
        meta_frame.columnconfigure(1, weight=1)

        content_frame = ttk.Frame(left_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        content_frame.columnconfigure(0, weight=11)
        content_frame.columnconfigure(1, weight=0)
        content_frame.columnconfigure(2, weight=9)
        content_frame.rowconfigure(0, weight=1)
        content_frame.rowconfigure(1, weight=0)

        list_frame = ttk.Frame(content_frame)
        list_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        cols = ("#", "Name", "Time")
        self.song_tree = ttk.Treeview(list_frame, columns=cols, show="headings", selectmode="browse")
        self.song_tree.heading("#", anchor=tk.W)
        self.song_tree.heading("Name", anchor=tk.W)
        self.song_tree.heading("Time", anchor=tk.W)
        self.song_tree.column("#", width=35, minwidth=35, stretch=False)
        self.song_tree.column("Name", width=280, minwidth=140)
        self.song_tree.column("Time", width=55, minwidth=55, stretch=False)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.song_tree.yview)
        self.song_tree.configure(yscrollcommand=scroll.set)
        self.song_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        middle_frame = ttk.Frame(content_frame)
        middle_frame.grid(row=0, column=1, sticky="ns", padx=10)
        self.add_btn = ttk.Button(middle_frame, command=self._add_to_pl, width=8)
        self.add_btn.pack(pady=(100, 8))
        self.del_btn = ttk.Button(middle_frame, command=self._remove_selected_song_from_playlist, width=8)
        self.del_btn.pack(pady=8)

        pl_frame = ttk.LabelFrame(content_frame)
        pl_frame.grid(row=0, column=2, sticky="nsew")
        self.pl_frame = pl_frame
        pl_cols = ("#", "Song", "Name")
        self.pl_tree = ttk.Treeview(pl_frame, columns=pl_cols, show="headings", selectmode="browse")
        self.pl_tree.heading("#", anchor=tk.W)
        self.pl_tree.heading("Song", anchor=tk.W)
        self.pl_tree.heading("Name", anchor=tk.W)
        self.pl_tree.column("#", width=30, minwidth=30, stretch=False)
        self.pl_tree.column("Song", width=50, minwidth=45, stretch=False)
        self.pl_tree.column("Name", width=210, minwidth=120)
        pl_scroll = ttk.Scrollbar(pl_frame, orient=tk.VERTICAL, command=self.pl_tree.yview)
        self.pl_tree.configure(yscrollcommand=pl_scroll.set)
        self.pl_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pl_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.song_tree.bind("<<TreeviewSelect>>", self._on_song_select)
        self.song_tree.bind("<Double-1>", self._on_song_dblclick)
        self.song_tree.bind("<F2>", self._on_song_f2)
        self.song_tree.bind("<ButtonPress-1>", self._on_song_press)
        self.song_tree.bind("<B1-Motion>", self._on_song_drag)
        self.song_tree.bind("<ButtonRelease-1>", self._on_song_click)
        self.song_tree.bind("<ButtonRelease-1>", self._on_song_release, add="+")
        self.pl_tree.bind("<ButtonPress-1>", self._on_pl_press)
        self.pl_tree.bind("<B1-Motion>", self._on_pl_drag)
        self.pl_tree.bind("<ButtonRelease-1>", self._on_pl_drop)

        playlist_bottom = ttk.Frame(content_frame)
        playlist_bottom.grid(row=1, column=2, sticky="ew", pady=(8, 0))
        btn_frame = ttk.Frame(playlist_bottom)
        btn_frame.grid(row=0, column=0, sticky="w")
        self.up_btn = ttk.Button(btn_frame, command=self._pl_up, width=6)
        self.up_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.down_btn = ttk.Button(btn_frame, command=self._pl_down, width=6)
        self.down_btn.pack(side=tk.LEFT, padx=4)
        self.clear_btn = ttk.Button(btn_frame, command=self._pl_clear, width=8)
        self.clear_btn.pack(side=tk.LEFT, padx=(4, 0))

        settings_frame = ttk.LabelFrame(playlist_bottom)
        settings_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.settings_frame = settings_frame
        for col in range(6):
            settings_frame.columnconfigure(col, weight=0)
        ttk.Label(settings_frame, textvariable=self._tvar("repeat")).grid(row=0, column=0, sticky=tk.W, padx=5, pady=(6, 4))
        self.repeat_var = tk.StringVar()
        self.repeat_combo = ttk.Combobox(settings_frame, textvariable=self.repeat_var, values=REPEAT_LABELS, state="readonly", width=8)
        self.repeat_combo.grid(row=0, column=1, sticky=tk.W, padx=2, pady=(6, 4))
        self.repeat_combo.bind("<<ComboboxSelected>>", self._on_setting_change)
        ttk.Label(settings_frame, textvariable=self._tvar("fade")).grid(row=0, column=2, sticky=tk.W, padx=(12, 5), pady=(6, 4))
        self.fade_var = tk.StringVar()
        self.fade_combo = ttk.Combobox(settings_frame, textvariable=self.fade_var, values=FADE_TIME_LABELS, state="readonly", width=8)
        self.fade_combo.grid(row=0, column=3, sticky=tk.W, padx=2, pady=(6, 4))
        self.fade_combo.bind("<<ComboboxSelected>>", self._on_setting_change)
        ttk.Label(settings_frame, textvariable=self._tvar("silence")).grid(row=0, column=4, sticky=tk.W, padx=(12, 5), pady=(6, 4))
        self.silence_var = tk.StringVar()
        self.silence_combo = ttk.Combobox(settings_frame, textvariable=self.silence_var, values=SILENCE_LABELS, state="readonly", width=8)
        self.silence_combo.grid(row=0, column=5, sticky=tk.W, padx=(2, 8), pady=(6, 4))
        self.silence_combo.bind("<<ComboboxSelected>>", self._on_setting_change)
        ttk.Label(settings_frame, textvariable=self._tvar("output")).grid(row=1, column=0, sticky=tk.W, padx=5, pady=(2, 8))
        self.mono_var = tk.StringVar()
        self.mono_combo = ttk.Combobox(settings_frame, textvariable=self.mono_var, state="readonly", width=8)
        self.mono_combo.grid(row=1, column=1, sticky=tk.W, padx=2, pady=(2, 8))
        self.mono_combo.bind("<<ComboboxSelected>>", self._on_setting_change)

    def _open_url(self, url):
        webbrowser.open(url)

    def _add_path_row(self, parent, row, label_key, var, browse_command, rows=None, desc_key=None):
        label = ttk.Label(parent, text=self.tr(label_key))
        label.grid(row=row, column=0, sticky=tk.W, padx=5, pady=(6, 2))
        entry = ttk.Entry(parent, textvariable=var, width=52)
        entry.grid(row=row, column=1, sticky="ew", padx=2, pady=(6, 2))
        button = ttk.Button(parent, text=self.tr("browse"), command=browse_command, width=6)
        button.grid(row=row, column=2, sticky="e", padx=(4, 5), pady=(6, 2))
        if desc_key:
            desc_frame = ttk.Frame(parent)
            desc_frame.grid(row=row + 1, column=1, columnspan=2, sticky="ew", padx=2, pady=(0, 5))
            ttk.Label(desc_frame, text=self.tr(desc_key), foreground="#555555", wraplength=430).pack(side=tk.LEFT)
            link = BUILD_SETTING_LINKS.get(label_key)
            if link:
                link_key, url = link
                link_label = ttk.Label(desc_frame, text=self.tr(link_key), foreground="#0066cc", cursor="hand2")
                link_label.pack(side=tk.LEFT, padx=(8, 0))
                link_label.bind("<Button-1>", lambda _e, u=url: self._open_url(u))
        if rows is not None:
            rows.append((entry, button))
        return entry, button

    def _apply_language(self):
        for key, var in self._i18n_vars.items():
            var.set(self.tr(key))
        self.root.title(self.tr("app_title"))
        self._set_status(self._status_loaded_text() if self.gbs_info else self.tr("status_initial"))
        self.left_frame.configure(text=self.tr("songs"))
        self.sources_frame.configure(text=self.tr("sources"))
        self.sync_frame.configure(text=self.tr("save_sync"))
        self.log_notebook.tab(self.general_log_frame, text=self.tr("log"))
        self.log_notebook.tab(self.build_log_frame, text=self.tr("build_log"))
        self.pl_frame.configure(text=self.tr("playlist"))
        self.settings_frame.configure(text=self.tr("settings"))
        self.song_tree.heading("#", text=self.tr("col_num"))
        self.song_tree.heading("Name", text=self.tr("col_name"))
        self.song_tree.heading("Time", text=self.tr("col_time"))
        self.pl_tree.heading("#", text=self.tr("col_num"))
        self.pl_tree.heading("Song", text=self.tr("col_song"))
        self.pl_tree.heading("Name", text=self.tr("col_name"))
        self.add_btn.configure(text=self.tr("add"))
        self.del_btn.configure(text=self.tr("del"))
        self.add_source_btn.configure(text=self.tr("add_source_short"))
        self.remove_source_btn.configure(text=self.tr("remove"))
        self.build_source_btn.configure(text=self.tr("build_selected_short"))
        self.refresh_adb_btn.configure(text=self.tr("refresh_adb"))
        self.build_install_btn.configure(text=self.tr("android_build_install"))
        self.build_install_all_btn.configure(text=self.tr("android_build_install_all"))
        self.auto_sync_check.configure(text=self.tr("auto_sync"))
        self.overwrite_save_check.configure(text=self.tr("overwrite_save"))
        self.pull_android_sav_btn.configure(text=self.tr("android_pull_sav"))
        self.push_android_sav_btn.configure(text=self.tr("android_push_sav"))
        for _entry, button in self._settings_path_rows:
            button.configure(text=self.tr("browse"))
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.title(self.tr("build_paths"))
            self.settings_close_btn.configure(text=self.tr("close"))
        self.up_btn.configure(text=self.tr("up"))
        self.down_btn.configure(text=self.tr("down"))
        self.clear_btn.configure(text=self.tr("clear"))
        self.mono_combo.configure(values=[self.tr("stereo"), self.tr("mono")])
        if self.sav:
            self._refresh_settings()

    def _setup_source_drop(self):
        widgets = [self.root, self.source_list, self.sources_frame]
        if windnd is not None:
            def on_drop(files):
                paths = []
                for item in files:
                    if isinstance(item, bytes):
                        paths.append(os.fsdecode(item))
                    else:
                        paths.append(str(item))
                self._add_source_paths(paths)
            for widget in widgets:
                windnd.hook_dropfiles(widget, func=on_drop)
            return
        if DND_FILES is not None:
            for widget in widgets:
                if hasattr(widget, "drop_target_register"):
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind("<<Drop>>", lambda event: self._add_source_paths(parse_drop_files(event.data)))
            return
        self._log_event("Drag and drop support requires tkinterdnd2 or windnd.")

    def _set_language(self, lang):
        self.lang = lang
        self._lang_var.set(lang)
        self._apply_language()

    def _on_sync_option_change(self):
        self._save_config()

    def _update_state(self):
        loaded = self.gbs_info is not None
        idle = not self._build_running
        has_adb_device = any(serial for serial, _name in self.adb_devices)
        adb_ready = idle and has_adb_device
        btn_state = "normal" if self.sav and idle else "disabled"
        for btn in (self.add_btn, self.del_btn, self.up_btn, self.down_btn, self.clear_btn):
            btn.configure(state=btn_state)
        if hasattr(self, "add_source_btn"):
            self.add_source_btn.configure(state="normal" if idle else "disabled")
        if hasattr(self, "build_source_btn"):
            self.build_source_btn.configure(state="normal" if self.sav and idle else "disabled")
        if hasattr(self, "remove_source_btn"):
            self.remove_source_btn.configure(state="normal" if self.entries and idle else "disabled")
        if hasattr(self, "refresh_adb_btn"):
            self.refresh_adb_btn.configure(state="normal" if idle else "disabled")
        if hasattr(self, "adb_device_combo"):
            self.adb_device_combo.configure(state="readonly" if idle else "disabled")
        if hasattr(self, "build_install_btn"):
            self.build_install_btn.configure(state="normal" if adb_ready else "disabled")
        if hasattr(self, "build_install_all_btn"):
            self.build_install_all_btn.configure(state="normal" if self.entries and adb_ready else "disabled")
        if hasattr(self, "pull_android_sav_btn"):
            self.pull_android_sav_btn.configure(state="normal" if self.sav and adb_ready else "disabled")
        if hasattr(self, "push_android_sav_btn"):
            self.push_android_sav_btn.configure(state="normal" if self.sav and adb_ready else "disabled")
        if hasattr(self, "auto_sync_check"):
            self.auto_sync_check.configure(state="normal" if idle else "disabled")
        if hasattr(self, "overwrite_save_check"):
            self.overwrite_save_check.configure(state="normal" if idle else "disabled")
        if hasattr(self, "_settings_path_rows"):
            for entry, button in self._settings_path_rows:
                entry.configure(state="normal" if idle else "disabled")
                button.configure(state="normal" if idle else "disabled")
        if hasattr(self, "build_menu"):
            menu_states = {
                self.tr("build_settings"): idle,
                self.tr("build_selected"): bool(self.sav) and idle,
                self.tr("build_all"): bool(self.entries) and idle,
                self.tr("android_assets_selected"): bool(self.sav) and idle,
                self.tr("android_assets_all"): bool(self.entries) and idle,
                self.tr("android_apk"): idle,
                self.tr("android_install"): adb_ready,
                self.tr("android_build_install"): adb_ready,
                self.tr("android_build_install_all"): bool(self.entries) and adb_ready,
                self.tr("android_pull_sav"): bool(self.sav) and adb_ready,
                self.tr("android_push_sav"): bool(self.sav) and adb_ready,
            }
            for label, enabled in menu_states.items():
                try:
                    self.build_menu.entryconfigure(label, state="normal" if enabled else "disabled")
                except tk.TclError:
                    pass

    def _refresh_songs(self):
        self.song_tree.delete(*self.song_tree.get_children())
        if not self.sav:
            return
        for i in range(self.sav.num_songs):
            name = self.sav.song_names[i] if i < len(self.sav.song_names) else ""
            time_idx = self.sav.track_time[i] if i < len(self.sav.track_time) else 0
            if time_idx < 0 or time_idx >= len(TRACK_TIME_LABELS):
                time_idx = 0
            time_str = TRACK_TIME_LABELS[time_idx]
            self.song_tree.insert("", tk.END, iid=str(i), values=(i + 1, name, time_str))

    def _refresh_playlist(self):
        self.pl_tree.delete(*self.pl_tree.get_children())
        if not self.sav:
            return
        for i in range(self.sav.count):
            song_idx = self.sav.tracks[i]
            name = self.sav.song_names[song_idx] if song_idx < len(self.sav.song_names) else ""
            self.pl_tree.insert("", tk.END, iid=f"pl_{i}", values=(i + 1, song_idx + 1, name))

    def _playlist_drop_index(self, y_root):
        rel_y = y_root - self.pl_tree.winfo_rooty()
        item = self.pl_tree.identify_row(rel_y)
        if item:
            return int(item.replace("pl_", ""))
        return self.sav.count if self.sav else 0

    def _song_drag_text(self, song_idx):
        if not self.sav or song_idx < 0 or song_idx >= self.sav.num_songs:
            return ""
        name = self.sav.song_names[song_idx] if song_idx < len(self.sav.song_names) else ""
        return f"{song_idx + 1}: {name or self.tr('col_name')}"

    def _show_drag_label(self, text, x_root, y_root):
        if not text:
            return
        if self._drag_label is None:
            self._drag_label = tk.Toplevel(self.root)
            self._drag_label.wm_overrideredirect(True)
            self._drag_label.attributes("-topmost", True)
            label = ttk.Label(self._drag_label, textvariable=self._drag_label_var, relief=tk.SOLID, borderwidth=1, padding=(8, 4))
            label.pack()
        self._drag_label_var.set(text)
        self._drag_label.wm_geometry(f"+{x_root + 14}+{y_root + 14}")

    def _hide_drag_label(self):
        if self._drag_label is not None:
            self._drag_label.destroy()
            self._drag_label = None
        self._drag_label_var.set("")

    def _refresh_settings(self):
        if not self.sav:
            return
        self._loading_settings = True
        entry = self._current_entry()
        try:
            if entry:
                self.title_var.set(source_display_title(entry))
                self.author_var.set(source_display_author(entry))
            else:
                title = self.gbs_info.get("title", "") if self.gbs_info else ""
                author = self.gbs_info.get("author", "") if self.gbs_info else ""
                self.title_var.set(self.sav.custom_title or ("" if title in GENERIC_SOURCE_TITLES else title))
                self.author_var.set(self.sav.custom_author or ("" if author in GENERIC_SOURCE_AUTHORS else author))
        finally:
            self._loading_settings = False
        repeat_idx = self.sav.repeat if 0 <= self.sav.repeat < len(REPEAT_LABELS) else 0
        fade_idx = self.sav.fade_time if 0 <= self.sav.fade_time < len(FADE_TIME_LABELS) else 2
        self.repeat_combo.set(REPEAT_LABELS[repeat_idx])
        self.fade_combo.set(FADE_TIME_LABELS[fade_idx])
        self.mono_combo.set(self.tr("mono") if self.sav.mono else self.tr("stereo"))
        silence_idx = self.sav.silence if 0 <= self.sav.silence < len(SILENCE_LABELS) else 0
        self.silence_combo.set(SILENCE_LABELS[silence_idx])

    def _apply_loaded_state(self):
        self._refresh_songs()
        self._refresh_playlist()
        self._refresh_settings()
        self._update_state()
        self.root.update_idletasks()

    def _current_entry(self):
        if self.current_index is None or not (0 <= self.current_index < len(self.entries)):
            return None
        return self.entries[self.current_index]

    def _sync_metadata_fields(self):
        entry = self._current_entry()
        if not entry or not self.sav or not hasattr(self, "title_var") or not hasattr(self, "author_var"):
            return False
        title = self.title_var.get().strip()
        author = self.author_var.get().strip()
        custom_title = title if title != source_default_title(entry) else ""
        custom_author = author if author != source_default_author(entry) else ""
        changed = self.sav.custom_title != custom_title or self.sav.custom_author != custom_author
        self.sav.custom_title = custom_title
        self.sav.custom_author = custom_author
        return changed

    def _store_active_entry(self):
        entry = self._current_entry()
        if not entry:
            return
        self._sync_metadata_fields()
        entry.gbs_info = self.gbs_info
        entry.sav = self.sav
        entry.sav_path = self.sav_path
        entry.dirty = self._dirty
        try:
            sel = self.song_tree.selection()
            if sel:
                entry.last_selected_track = int(sel[0])
        except Exception:
            pass

    def _activate_entry(self, index):
        if not (0 <= index < len(self.entries)):
            return
        self._store_active_entry()
        self.current_index = index
        entry = self.entries[index]
        self.gbs_info = entry.gbs_info
        self.sav = entry.sav
        self.sav_path = entry.sav_path
        self.gbs_path = entry.source_path
        self._dirty = entry.dirty
        self._apply_loaded_state()
        self.source_list.selection_clear(0, tk.END)
        self.source_list.selection_set(index)
        self.source_list.see(index)
        if 0 <= entry.last_selected_track < self.sav.num_songs:
            iid = str(entry.last_selected_track)
            if self.song_tree.exists(iid):
                self.song_tree.selection_set(iid)
                self.song_tree.see(iid)
        self._set_status(self._status_loaded_text())
        self._save_config()

    def _refresh_sources(self):
        self.source_list.delete(0, tk.END)
        for entry in self.entries:
            marker = "*" if entry.dirty else " "
            self.source_list.insert(tk.END, f"{marker} {entry.display_name}")
        if self.current_index is not None and 0 <= self.current_index < len(self.entries):
            self.source_list.selection_set(self.current_index)

    def _on_source_select(self, event=None):
        if self._source_drag_from is not None:
            return
        sel = self.source_list.curselection()
        if not sel:
            return
        index = int(sel[0])
        if index != self.current_index:
            self._activate_entry(index)

    def _source_index_at(self, y):
        if not self.entries:
            return None
        idx = self.source_list.nearest(y)
        if idx < 0:
            idx = 0
        if idx >= len(self.entries):
            idx = len(self.entries) - 1
        return idx

    def _on_source_press(self, event):
        if self._build_running:
            self._source_drag_from = None
            self._source_drag_to = None
            self._hide_drag_label()
            return
        idx = self._source_index_at(event.y)
        self._source_drag_from = idx
        self._source_drag_to = idx

    def _on_source_drag(self, event):
        if self._source_drag_from is None:
            return
        idx = self._source_index_at(event.y)
        if idx is None:
            return
        if 0 <= self._source_drag_from < len(self.entries):
            self._show_drag_label(self.entries[self._source_drag_from].display_name, event.x_root, event.y_root)
        self._source_drag_to = idx
        self.source_list.selection_clear(0, tk.END)
        self.source_list.selection_set(idx)
        self.source_list.see(idx)

    def _on_source_drop(self, event):
        if self._source_drag_from is None:
            return
        src = self._source_drag_from
        dst = self._source_drag_to
        self._source_drag_from = None
        self._source_drag_to = None
        self._hide_drag_label()
        if dst is None or src == dst or not (0 <= src < len(self.entries)) or not (0 <= dst < len(self.entries)):
            sel = self.source_list.curselection()
            if sel:
                idx = int(sel[0])
                if idx != self.current_index:
                    self._activate_entry(idx)
            return
        moved = self.entries.pop(src)
        self.entries.insert(dst, moved)
        if self.current_index is None:
            self.current_index = dst
        elif self.current_index == src:
            self.current_index = dst
        elif src < self.current_index <= dst:
            self.current_index -= 1
        elif dst <= self.current_index < src:
            self.current_index += 1
        self._refresh_sources()
        self.source_list.see(self.current_index)
        self._save_config()

    def _create_entry_from_source(self, path, sav_path=None, last_selected_track=0):
        info = parse_source_info(path)
        sav = SaveData(info["num_songs"])
        loaded_sav = None
        candidates = []
        if sav_path:
            candidates.append(sav_path)
        candidates.append(os.path.splitext(path)[0] + ".sav")
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                try:
                    sav.load(candidate)
                    loaded_sav = candidate
                    break
                except Exception:
                    pass
        entry = SourceEntry(
            source_path=path,
            gbs_info=info,
            sav=sav,
            sav_path=loaded_sav,
            dirty=False,
            last_selected_track=last_selected_track,
            source_id=safe_id_from_path(path),
        )
        self.entries.append(entry)
        self.gbs_info = info
        self.sav = sav
        self.sav_path = loaded_sav
        self.gbs_path = path
        if not any(n != "" for n in sav.song_names) and not any(v != 0 for v in sav.track_time):
            self._auto_load_song_names()
        elif not any(n != "" for n in sav.song_names):
            self._auto_load_song_names(load_times=False)
        entry.sav = sav
        entry.sav_path = self.sav_path
        return entry

    def _add_source_paths(self, paths):
        added = 0
        first_added = None
        existing = {source_path_key(entry.source_path) for entry in self.entries}
        for path in paths:
            path = os.path.abspath(str(path).strip().strip('"'))
            if not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() not in SUPPORTED_SOURCE_EXTS:
                continue
            key = source_path_key(path)
            if key in existing:
                continue
            try:
                self._create_entry_from_source(path)
                existing.add(key)
                added += 1
                if first_added is None:
                    first_added = len(self.entries) - 1
            except Exception as e:
                self._log_event(f"{os.path.basename(path)}: ERROR: {e}")
        if added:
            self._refresh_sources()
            self._activate_entry(first_added)
            self._save_config()

    def _restore_previous_sources(self):
        sources = self.config.get("open_sources", [])
        if not sources:
            return
        if self.entries:
            return
        last_active = self.config.get("last_active_source")
        existing = set()
        active_index = 0
        for item in sources:
            path = item.get("source")
            if not path or not os.path.isfile(path):
                continue
            key = source_path_key(path)
            if key in existing:
                continue
            try:
                entry = self._create_entry_from_source(
                    path,
                    sav_path=item.get("sav"),
                    last_selected_track=int(item.get("last_selected_track", 0) or 0),
                )
                existing.add(key)
                if last_active and source_path_key(path) == source_path_key(last_active):
                    active_index = len(self.entries) - 1
            except Exception as e:
                self._append_log(f"reload skipped: {path}\n{e}\n")
        self._refresh_sources()
        if self.entries:
            self._activate_entry(active_index)

    def _remove_current_source(self):
        if self.current_index is None:
            return
        del self.entries[self.current_index]
        self.current_index = None
        if self.entries:
            self._activate_entry(min(len(self.entries) - 1, 0))
        else:
            self.gbs_info = None
            self.sav = None
            self.sav_path = None
            self.gbs_path = None
            self._dirty = False
            self._apply_loaded_state()
            self._set_status(self.tr("status_initial"))
        self._refresh_sources()
        self._save_config()

    def _open_gbs(self):
        path = filedialog.askopenfilename(
            title=self.tr("open_gbs_title"),
            filetypes=[("Supported source files", "*.gbs *.gbc *.gb"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            existing = None
            for i, entry in enumerate(self.entries):
                if os.path.abspath(entry.source_path) == os.path.abspath(path):
                    existing = i
                    break
            if existing is not None:
                self._activate_entry(existing)
                return
        except Exception as e:
            messagebox.showerror(self.tr("error"), str(e))
            return
        before = len(self.entries)
        self._add_source_paths([path])
        if len(self.entries) == before:
            messagebox.showerror(self.tr("error"), f"Unsupported source file: {path}")

    def _open_sav(self):
        if not self.sav:
            messagebox.showinfo(self.tr("info"), self.tr("load_gbs_first"))
            return
        path = filedialog.askopenfilename(title=self.tr("open_sav_title"), filetypes=[("SAV files", "*.sav"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.sav.load(path)
            self.sav_path = path
        except Exception as e:
            messagebox.showerror(self.tr("error"), str(e))
            return
        self._apply_loaded_state()
        self._dirty = False
        entry = self._current_entry()
        if entry:
            entry.sav = self.sav
            entry.sav_path = path
            entry.dirty = False
            self._refresh_sources()
            self._save_config()
        self._set_status(self.tr("sav_loaded", name=os.path.basename(path)))

    def _save_sav(self):
        if not self.sav:
            return
        self._sync_metadata_fields()
        if not self.sav_path:
            self._save_sav_as()
            return
        try:
            self.sav.save(self.sav_path)
            self._dirty = False
            entry = self._current_entry()
            if entry:
                entry.sav_path = self.sav_path
                entry.dirty = False
                self._refresh_sources()
                self._save_config()
            self._set_status(self.tr("saved", path=self.sav_path))
        except Exception as e:
            messagebox.showerror(self.tr("error"), str(e))

    def _save_sav_as(self):
        if not self.sav:
            return
        self._sync_metadata_fields()
        path = filedialog.asksaveasfilename(
            title=self.tr("save_sav_title"),
            defaultextension=".sav",
            initialfile="gbs_player.sav",
            filetypes=[("SAV files", "*.sav"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.sav.save(path)
            self.sav_path = path
            self._dirty = False
            entry = self._current_entry()
            if entry:
                entry.sav_path = path
                entry.dirty = False
                self._refresh_sources()
                self._save_config()
            self._set_status(self.tr("saved", path=path))
        except Exception as e:
            messagebox.showerror(self.tr("error"), str(e))

    def _import_names(self):
        if not self.sav:
            messagebox.showinfo(self.tr("info"), self.tr("load_file_first"))
            return
        path = filedialog.askopenfilename(title=self.tr("import_names_title"), filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            names, times, lines = load_song_list(path, self.sav.num_songs)
            for i in range(self.sav.num_songs):
                self.sav.song_names[i] = names[i]
                if times[i] is not None:
                    self.sav.track_time[i] = times[i]
            self.sav.name_magic = NAME_MAGIC
            self._mark_dirty()
            self._refresh_songs()
            self._refresh_playlist()
            self._set_status(self.tr("imported_names", count=min(len(lines), self.sav.num_songs)))
        except Exception as e:
            messagebox.showerror(self.tr("error"), str(e))

    def _export_names(self):
        if not self.sav:
            return
        initial_name = "songnames.txt"
        if self.gbs_path:
            initial_name = os.path.basename(os.path.splitext(self.gbs_path)[0] + ".names.txt")
        path = filedialog.asksaveasfilename(
            title=self.tr("export_names_title"),
            defaultextension=".txt",
            initialfile=initial_name,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for i, name in enumerate(self.sav.song_names):
                    f.write(f"{name}\t{TRACK_TIME_LABELS[self.sav.track_time[i]]}\n")
            self._set_status(self.tr("exported_to", path=path))
        except Exception as e:
            messagebox.showerror(self.tr("error"), str(e))

    def _auto_load_song_names(self, load_times=True):
        if not self.gbs_path or not self.sav:
            return
        base = os.path.splitext(self.gbs_path)[0]
        candidates = [base + ".names.txt", os.path.join(os.path.dirname(self.gbs_path) or ".", "songnames.txt")]
        for path in candidates:
            if os.path.isfile(path):
                try:
                    names, times, _ = load_song_list(path, self.sav.num_songs)
                    for i in range(self.sav.num_songs):
                        self.sav.song_names[i] = names[i]
                        if load_times and times[i] is not None:
                            self.sav.track_time[i] = times[i]
                    self.sav.name_magic = NAME_MAGIC
                    self._set_status(self.tr("song_names_loaded", name=os.path.basename(path)))
                except Exception:
                    pass
                return

    def _start_inplace_edit(self, item_id, column="Name"):
        if not self.sav or self._edit_entry:
            return
        tree_column = "Time" if column == "Time" else "Name"
        bbox = self.song_tree.bbox(item_id, tree_column)
        if not bbox:
            self.song_tree.see(item_id)
            self.song_tree.update_idletasks()
            bbox = self.song_tree.bbox(item_id, tree_column)
            if not bbox:
                return
        x, y, w, h = bbox
        idx = int(item_id)
        closed = {"value": False}

        def close_editor():
            if closed["value"]:
                return
            closed["value"] = True
            widget = self._edit_entry
            if widget is not None:
                widget.destroy()
            self._edit_entry = None
            self._edit_item = None
            self._edit_column = None

        def refresh_after_edit():
            self._refresh_songs()
            self._refresh_playlist()
            self.song_tree.selection_set(str(idx))
            self.song_tree.see(str(idx))

        if tree_column == "Time":
            current = TRACK_TIME_LABELS[self.sav.track_time[idx]]
            var = tk.StringVar(value=current)
            editor = ttk.Combobox(self.song_tree, textvariable=var, values=TRACK_TIME_LABELS, state="normal", width=1)
            editor.place(x=x, y=y, width=w, height=h)

            def commit(event=None, next_name=False):
                parsed = parse_track_time_value(var.get())
                if parsed is not None and idx < len(self.sav.track_time) and self.sav.track_time[idx] != parsed:
                    self.sav.track_time[idx] = parsed
                    self._mark_dirty()
                close_editor()
                refresh_after_edit()
                if next_name and idx + 1 < self.sav.num_songs:
                    self.root.after(20, lambda: self._start_inplace_edit(str(idx + 1), "Name"))
                return "break"

            editor.bind("<Return>", lambda e: commit(e, next_name=True))
            editor.bind("<Escape>", lambda e: (close_editor(), "break")[1])
            editor.bind("<FocusOut>", commit)
            editor.bind("<<ComboboxSelected>>", commit)
        else:
            cur_name = self.sav.song_names[idx] if idx < len(self.sav.song_names) else ""
            editor = tk.Entry(self.song_tree, width=1)
            editor.place(x=x, y=y, width=w, height=h)
            editor.insert(0, cur_name)
            editor.select_range(0, tk.END)

            def commit(event=None, next_action=None):
                if idx < len(self.sav.song_names):
                    raw_name = editor.get().strip()
                    name = sanitize_song_name(raw_name, 31)
                    if name != raw_name:
                        self._log_event(f"曲名に使用できない文字を削除しました: {idx + 1}: {name}")
                    if self.sav.song_names[idx] != name:
                        self.sav.song_names[idx] = name
                        self.sav.name_magic = NAME_MAGIC
                        self._mark_dirty()
                close_editor()
                refresh_after_edit()
                if next_action == "time":
                    self.root.after(20, lambda: self._start_inplace_edit(str(idx), "Time"))
                elif next_action == "next" and idx + 1 < self.sav.num_songs:
                    self.root.after(20, lambda: self._start_inplace_edit(str(idx + 1), "Name"))
                return "break"

            editor.bind("<Return>", lambda e: commit(e, next_action="next"))
            editor.bind("<Tab>", lambda e: commit(e, next_action="time"))
            editor.bind("<Escape>", lambda e: (close_editor(), "break")[1])
            editor.bind("<FocusOut>", commit)

        editor.focus_set()
        self._edit_entry = editor
        self._edit_item = item_id
        self._edit_column = tree_column

    def _on_song_f2(self, event):
        sel = self.song_tree.selection()
        if sel:
            self._start_inplace_edit(sel[0], "Name")

    def _on_song_click(self, event):
        sel = self.song_tree.selection()
        if not sel:
            self._last_selected = None
            return
        item = sel[0]
        region = self.song_tree.identify_region(event.x, event.y)
        col = self.song_tree.identify_column(event.x)
        if region == "cell" and col in ("#2", "#3") and item == self._last_selected:
            edit_column = "Time" if col == "#3" else "Name"
            self.root.after(50, lambda: self._start_inplace_edit(item, edit_column))
        else:
            self._last_selected = item

    def _on_song_select(self, event):
        return

    def _on_song_dblclick(self, event):
        item = self.song_tree.identify_row(event.y)
        col = self.song_tree.identify_column(event.x)
        if item:
            self._start_inplace_edit(item, "Time" if col == "#3" else "Name")

    def _on_song_press(self, event):
        item = self.song_tree.identify_row(event.y)
        self._song_drag_index = int(item) if item else None

    def _on_song_drag(self, event):
        if self._song_drag_index is None or not self.sav:
            return
        self._show_drag_label(self._song_drag_text(self._song_drag_index), event.x_root, event.y_root)

    def _on_song_release(self, event):
        if self._song_drag_index is None or not self.sav:
            self._hide_drag_label()
            return
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        if widget is self.pl_tree:
            if self.sav.count >= MAX_PL:
                messagebox.showwarning(self.tr("warning"), self.tr("playlist_full"))
            else:
                target = self._playlist_drop_index(event.y_root)
                self._insert_song_to_playlist(self._song_drag_index, target)
        self._song_drag_index = None
        self._hide_drag_label()

    def _apply_edit_song(self):
        if self._edit_entry is not None:
            self._edit_entry.event_generate("<Return>")

    def _on_setting_change(self, event):
        if not self.sav:
            return
        self.sav.repeat = REPEAT_LABELS.index(self.repeat_var.get())
        self.sav.fade_time = FADE_TIME_LABELS.index(self.fade_var.get())
        self.sav.mono = 1 if self.mono_var.get() == self.tr("mono") else 0
        sil = self.silence_var.get()
        self.sav.silence = SILENCE_LABELS.index(sil) if sil in SILENCE_LABELS else 0
        self._mark_dirty()

    def _add_to_pl(self):
        sel = self.song_tree.selection()
        if not sel or not self.sav:
            return
        if self.sav.count >= MAX_PL:
            messagebox.showwarning(self.tr("warning"), self.tr("playlist_full"))
            return
        idx = int(sel[0])
        target = self._playlist_insert_index()
        self._insert_song_to_playlist(idx, target)

    def _insert_song_to_playlist(self, song_idx, target):
        if not self.sav or self.sav.count >= MAX_PL:
            return
        if target < 0:
            target = 0
        if target > self.sav.count:
            target = self.sav.count
        for i in range(self.sav.count, target, -1):
            self.sav.tracks[i] = self.sav.tracks[i - 1]
        self.sav.tracks[target] = song_idx
        self.sav.count += 1
        self._mark_dirty()
        self._refresh_playlist()
        self.pl_tree.selection_set(f"pl_{target}")
        self.pl_tree.see(f"pl_{target}")

    def _playlist_insert_index(self):
        sel = self.pl_tree.selection()
        if sel:
            return int(sel[0].replace("pl_", ""))
        return self.sav.count if self.sav else 0

    def _remove_selected_song_from_playlist(self):
        if not self.sav:
            return
        self._pl_remove()

    def _pl_up(self):
        sel = self.pl_tree.selection()
        if not sel or not self.sav:
            return
        idx = int(sel[0].replace("pl_", ""))
        if idx <= 0:
            return
        self.sav.tracks[idx], self.sav.tracks[idx - 1] = self.sav.tracks[idx - 1], self.sav.tracks[idx]
        self._mark_dirty()
        self._refresh_playlist()
        self.pl_tree.selection_set(f"pl_{idx - 1}")

    def _pl_down(self):
        sel = self.pl_tree.selection()
        if not sel or not self.sav:
            return
        idx = int(sel[0].replace("pl_", ""))
        if idx >= self.sav.count - 1:
            return
        self.sav.tracks[idx], self.sav.tracks[idx + 1] = self.sav.tracks[idx + 1], self.sav.tracks[idx]
        self._mark_dirty()
        self._refresh_playlist()
        self.pl_tree.selection_set(f"pl_{idx + 1}")

    def _pl_remove(self):
        sel = self.pl_tree.selection()
        if not sel or not self.sav:
            return
        idx = int(sel[0].replace("pl_", ""))
        for i in range(idx, self.sav.count - 1):
            self.sav.tracks[i] = self.sav.tracks[i + 1]
        self.sav.count -= 1
        if self.sav.count < 0:
            self.sav.count = 0
        self._mark_dirty()
        self._refresh_playlist()

    def _pl_clear(self):
        if not self.sav or self.sav.count == 0:
            return
        if messagebox.askyesno(self.tr("confirm"), self.tr("clear_playlist")):
            self.sav.count = 0
            self._mark_dirty()
            self._refresh_playlist()

    def _on_pl_press(self, event):
        item = self.pl_tree.identify_row(event.y)
        if not item:
            self._pl_drag_from = None
            return
        self._pl_drag_from = int(item.replace("pl_", ""))
        self._pl_drag_to = self._pl_drag_from

    def _on_pl_drag(self, event):
        if self._pl_drag_from is None or not self.sav:
            return
        track = self.sav.tracks[self._pl_drag_from] if self._pl_drag_from < self.sav.count else -1
        self._show_drag_label(self._song_drag_text(track), event.x_root, event.y_root)
        item = self.pl_tree.identify_row(event.y)
        if item:
            idx = int(item.replace("pl_", ""))
        else:
            idx = self.sav.count - 1
        self._pl_drag_to = idx
        self.pl_tree.selection_set(f"pl_{idx}")

    def _on_pl_drop(self, event):
        if self._pl_drag_from is None or self._pl_drag_to is None or not self.sav:
            self._pl_drag_from = None
            self._pl_drag_to = None
            self._hide_drag_label()
            return
        src = self._pl_drag_from
        dst = self._pl_drag_to
        self._pl_drag_from = None
        self._pl_drag_to = None
        self._hide_drag_label()
        if src == dst or src >= self.sav.count or dst >= self.sav.count:
            return
        track = self.sav.tracks[src]
        if src < dst:
            for i in range(src, dst):
                self.sav.tracks[i] = self.sav.tracks[i + 1]
        else:
            for i in range(src, dst, -1):
                self.sav.tracks[i] = self.sav.tracks[i - 1]
        self.sav.tracks[dst] = track
        self._mark_dirty()
        self._refresh_playlist()
        self.pl_tree.selection_set(f"pl_{dst}")
        self.pl_tree.see(f"pl_{dst}")

    def _append_log(self, text):
        def write():
            self.log_text.configure(state="normal")
            self.log_text.insert(tk.END, text)
            self.log_text.see(tk.END)
            self.log_text.configure(state="disabled")
        if threading.current_thread() is threading.main_thread():
            write()
        else:
            self.root.after(0, write)

    def _append_general_log(self, text):
        def write():
            if not hasattr(self, "general_log_text"):
                return
            self.general_log_text.configure(state="normal")
            self.general_log_text.insert(tk.END, text)
            self.general_log_text.see(tk.END)
            self.general_log_text.configure(state="disabled")
        if threading.current_thread() is threading.main_thread():
            write()
        else:
            self.root.after(0, write)

    def _set_progress(self, value=None, maximum=None):
        def apply():
            if maximum is not None:
                self.progress_bar.configure(maximum=maximum)
            if value is not None:
                self.progress_var.set(value)
        if threading.current_thread() is threading.main_thread():
            apply()
        else:
            self.root.after(0, apply)

    def _log_event(self, text):
        self._append_general_log(text.rstrip() + "\n")

    def _sync_build_settings_vars(self):
        if threading.current_thread() is not threading.main_thread():
            return
        if hasattr(self, "gbdk_var"):
            self.gbdk_path = self.gbdk_var.get().strip() or self.gbdk_path
            self.msys_bash_path = self.msys_bash_var.get().strip() or self.msys_bash_path
            self.java_home = self.java_home_var.get().strip() or self.java_home
            new_adb = self.adb_path_var.get().strip() or self.adb_path
            if new_adb != self.adb_path:
                self.adb_path = new_adb
                self.adb_device_serial = ""
                self.adb_device_choices = {}

    def _browse_path_var(self, var, directory=False, filetypes=None, refresh_adb=False):
        if directory:
            path = filedialog.askdirectory(initialdir=var.get() or APP_DIR)
        else:
            path = filedialog.askopenfilename(initialdir=os.path.dirname(var.get()) or APP_DIR, filetypes=filetypes or [("All files", "*.*")])
        if not path:
            return
        var.set(path)
        self._sync_build_settings_vars()
        self._save_config()
        if refresh_adb:
            self._refresh_adb_devices()

    def _edit_build_settings(self):
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.lift()
            self._settings_window.focus_force()
            return

        self._sync_build_settings_vars()
        win = tk.Toplevel(self.root)
        self._settings_window = win
        self._settings_path_rows = []
        win.title(self.tr("build_paths"))
        win.transient(self.root)
        win.resizable(True, False)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame.columnconfigure(1, weight=1)

        self._add_path_row(frame, 0, "gbdk_path", self.gbdk_var, lambda: self._browse_path_var(self.gbdk_var, directory=True), rows=self._settings_path_rows, desc_key="gbdk_desc")
        self._add_path_row(frame, 2, "msys_bash_path", self.msys_bash_var, lambda: self._browse_path_var(self.msys_bash_var, filetypes=[("bash.exe", "bash.exe"), ("Executables", "*.exe"), ("All files", "*.*")]), rows=self._settings_path_rows, desc_key="msys_bash_desc")
        self._add_path_row(frame, 4, "java_home_path", self.java_home_var, lambda: self._browse_path_var(self.java_home_var, directory=True), rows=self._settings_path_rows, desc_key="java_home_desc")
        self._add_path_row(frame, 6, "adb_path", self.adb_path_var, lambda: self._browse_path_var(self.adb_path_var, filetypes=[("adb.exe", "adb.exe"), ("Executables", "*.exe"), ("All files", "*.*")], refresh_adb=True), rows=self._settings_path_rows, desc_key="adb_desc")

        btns = ttk.Frame(frame)
        btns.grid(row=8, column=0, columnspan=3, sticky="e", pady=(10, 0))
        self.settings_close_btn = ttk.Button(btns, text=self.tr("close"), command=self._close_build_settings)
        self.settings_close_btn.pack(side=tk.RIGHT)

        def on_close():
            self._close_build_settings()

        win.protocol("WM_DELETE_WINDOW", on_close)
        self._update_state()

    def _close_build_settings(self):
        self._sync_build_settings_vars()
        self._save_config()
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.destroy()
        self._settings_window = None
        self._settings_path_rows = []

    def _on_adb_device_selected(self, event=None):
        value = self.adb_device_var.get()
        self.adb_device_serial = self.adb_device_choices.get(value, "")
        self._save_config()

    def _set_adb_device_values(self, devices):
        self.adb_devices = devices
        counts = {}
        for _serial, name in devices:
            counts[name] = counts.get(name, 0) + 1
        choices = {}
        values = []
        for serial, name in devices:
            label = name
            if counts.get(name, 0) > 1:
                label = f"{name} [{serial}]"
            choices[label] = serial
            values.append(label)
        if not values:
            choices = {"(default)": ""}
            values = ["(default)"]
            self.adb_device_serial = ""
        self.adb_device_choices = choices
        if self.adb_device_serial and self.adb_device_serial not in choices.values():
            self.adb_device_serial = ""
        self.adb_device_combo.configure(values=values)
        if self.adb_device_serial:
            for label, serial in choices.items():
                if serial == self.adb_device_serial:
                    self.adb_device_var.set(label)
                    break
        else:
            self.adb_device_var.set(values[0])
        self._update_state()

    def _list_adb_devices_sync(self):
        self._sync_build_settings_vars()
        cmd = [self.adb_path, "devices", "-l"]
        self._append_log("$ " + " ".join(cmd) + "\n")
        proc = subprocess.run(
            cmd,
            cwd=APP_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._append_log(proc.stdout)
        if proc.returncode != 0:
            raise RuntimeError(f"command failed with exit code {proc.returncode}")
        devices = []
        for line in proc.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                model = ""
                product = ""
                device_name = ""
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.split(":", 1)[1]
                    elif part.startswith("product:"):
                        product = part.split(":", 1)[1]
                    elif part.startswith("device:"):
                        device_name = part.split(":", 1)[1]
                display_name = model or device_name or product or parts[0]
                devices.append((parts[0], display_name))
        return devices

    def _refresh_adb_devices(self):
        if self._build_running:
            return
        self._build_running = True
        self._log_event(self.tr("refresh_adb"))
        self._update_state()

        def worker():
            try:
                devices = self._list_adb_devices_sync()
                self.root.after(0, lambda: self._set_adb_device_values(devices))
                if devices:
                    self._log_event(f"{self.tr('refresh_adb')}: {len(devices)} device(s)")
                else:
                    msg = self.tr("adb_no_device")
                    self._log_event(msg)
                    self._post_status(msg)
            except Exception as e:
                self._append_log(f"ERROR: {e}\n")
                self._log_event(f"{self.tr('refresh_adb')}: ERROR: {e}")
            finally:
                def finish():
                    self._build_running = False
                    self._update_state()
                    self._save_config()
                    self._maybe_auto_sync_on_start()
                self.root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def _maybe_auto_sync_on_start(self):
        if self._startup_auto_sync_done:
            return
        if not self.auto_sync_var.get() or not self.sav:
            return
        if not any(serial for serial, _name in self.adb_devices):
            return
        self._startup_auto_sync_done = True
        self._log_event(self.tr("auto_sync"))
        self.root.after(100, self._pull_android_sav)

    def _run_logged(self, args, cwd=None, shell=False):
        self._append_log(f"$ {' '.join(args) if isinstance(args, list) else args}\n")
        proc = subprocess.Popen(
            args,
            cwd=cwd or APP_DIR,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in proc.stdout:
            self._append_log(line)
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"command failed with exit code {code}")

    def _make_command(self, target, source_path, sav_path=None):
        self._sync_build_settings_vars()
        source_abs = os.path.abspath(source_path)
        sav_abs = os.path.abspath(sav_path) if sav_path else None
        gbdk = self.gbdk_path.replace("\\", "/")
        use_msys = gbdk.startswith("/") and os.path.isfile(self.msys_bash_path)
        if use_msys:
            repo = quote_sh(win_to_msys_path(APP_DIR))
            src = quote_sh(win_to_msys_path(source_abs))
            target_part = f" {target}" if target else ""
            sav_part = f" SAV={quote_sh(win_to_msys_path(sav_abs))}" if sav_abs and target == "android-assets" else ""
            script = f"cd {repo} && make -B{target_part} GBDK={quote_sh(gbdk)} GBS={src}{sav_part}"
            return [self.msys_bash_path, "-lc", script]
        cmd = ["make", "-B"]
        if target:
            cmd.append(target)
        cmd.extend([f"GBDK={self.gbdk_path}", f"GBS={source_abs}"])
        if sav_abs and target == "android-assets":
            cmd.append(f"SAV={sav_abs}")
        return cmd

    def _build_output_dir(self, entry):
        out_dir = os.path.join(APP_DIR, "build", "roms", entry.source_id or safe_id_from_path(entry.source_path))
        os.makedirs(out_dir, exist_ok=True)
        return out_dir

    def _copy_build_outputs(self, entry, metadata_source=None):
        out_dir = self._build_output_dir(entry)
        rom_src = os.path.join(APP_DIR, "build", "gbs_player.gbc")
        if os.path.isfile(rom_src):
            rom_dst = os.path.join(out_dir, "gbs_player.gbc")
            shutil.copy2(rom_src, rom_dst)
            entry.build_output = rom_dst
        metadata_dst = os.path.join(out_dir, "metadata.json")
        self._run_logged([sys.executable, os.path.join("tools", "build.py"), "metadata", metadata_source or entry.source_path, metadata_dst], cwd=APP_DIR)
        entry.metadata_output = metadata_dst
        if entry.sav_path and os.path.isfile(entry.sav_path):
            shutil.copy2(entry.sav_path, os.path.join(out_dir, "gbs_player.sav"))
        return entry.build_output or out_dir

    def _open_build_folder(self, path):
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda p=path: self._open_build_folder(p))
            return
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if not folder or not os.path.isdir(folder):
            return
        try:
            os.startfile(folder)
        except Exception as e:
            self._log_event(f"Explorer open failed: {e}")

    def _sync_current_song_edit(self):
        if self._edit_entry is not None:
            self._edit_entry.event_generate("<Return>")

    def _write_staged_song_list(self, entry, path):
        sav = entry.sav
        if not sav:
            return
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            title = source_display_title(entry)
            author = source_display_author(entry)
            if title:
                f.write(f"# title: {title}\n")
            if author:
                f.write(f"# author: {author}\n")
            for i in range(sav.num_songs):
                name = sav.song_names[i] if i < len(sav.song_names) else ""
                time_idx = sav.track_time[i] if i < len(sav.track_time) else 0
                if time_idx < 0 or time_idx >= len(TRACK_TIME_LABELS):
                    time_idx = 0
                if name or time_idx != 0:
                    f.write(f"{name}\t{TRACK_TIME_LABELS[time_idx]}\n")
                else:
                    f.write("\n")

    def _staged_source_for_build(self, entry):
        src = os.path.abspath(entry.source_path)
        ext = os.path.splitext(src)[1].lower()
        stage_dir = os.path.join(APP_DIR, "build", "source_inputs")
        os.makedirs(stage_dir, exist_ok=True)
        staged = os.path.join(stage_dir, (entry.source_id or safe_id_from_path(src)) + ext)
        shutil.copy2(src, staged)

        base = os.path.splitext(src)[0]
        staged_base = os.path.splitext(staged)[0]
        names_src = base + ".names.txt"
        staged_names = staged_base + ".names.txt"
        has_editor_names = (
            entry.sav
            and (
                entry.sav.name_magic == NAME_MAGIC
                or entry.sav.custom_title
                or entry.sav.custom_author
                or any(n != "" for n in entry.sav.song_names)
                or any(t != 0 for t in entry.sav.track_time)
            )
        )
        if has_editor_names:
            self._write_staged_song_list(entry, staged_names)
        elif os.path.isfile(names_src):
            shutil.copy2(names_src, staged_base + ".names.txt")
        else:
            songnames = os.path.join(os.path.dirname(src) or ".", "songnames.txt")
            if os.path.isfile(songnames):
                shutil.copy2(songnames, staged_names)
        return staged

    def _build_sources(self, entries, android_assets=False, open_folder=False):
        entries = [e for e in entries if e]
        if not entries:
            messagebox.showinfo(self.tr("info"), self.tr("no_source_selected"))
            self._log_event(self.tr("no_source_selected"))
            return
        if self._build_running:
            return
        self._sync_build_settings_vars()
        self._sync_current_song_edit()
        self._store_active_entry()
        self._build_running = True
        self._set_progress(0, max(1, len(entries)))
        if len(entries) > 1:
            label = self.tr("android_assets_all" if android_assets else "build_all")
        else:
            label = self.tr("android_assets_selected" if android_assets else "build_selected")
        self._log_event(f"{label} ({len(entries)})")
        self._update_state()

        def worker():
            try:
                self._build_entries_sync(entries, android_assets=android_assets, open_folder=open_folder)
            except Exception:
                pass
            def finish():
                self._build_running = False
                self._refresh_sources()
                self._set_progress(0, 100)
                self._update_state()
                self._save_config()
            self.root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def _build_entries_sync(self, entries, android_assets=False, open_folder=False):
        last_output = None
        for index, entry in enumerate(entries):
            try:
                self._post_status(self.tr("build_started", name=entry.display_name))
                self._log_event(self.tr("build_started", name=entry.display_name))
                self._append_log(f"\n== {entry.display_name} ==\n")
                if entry.dirty:
                    if not entry.sav_path:
                        entry.sav_path = os.path.splitext(entry.source_path)[0] + ".sav"
                    entry.sav.save(entry.sav_path)
                    entry.dirty = False
                target = "android-assets" if android_assets else ""
                build_source = self._staged_source_for_build(entry)
                self._run_logged(self._make_command(target, build_source, entry.sav_path), cwd=APP_DIR)
                output = self._copy_build_outputs(entry, metadata_source=build_source)
                last_output = output
                self._append_log(f"output: {output}\n")
                self._set_progress(index + 1)
                self._log_event(self.tr("build_done", path=output))
                self._post_status(self.tr("build_done", path=output))
            except Exception as e:
                self._append_log(f"ERROR: {e}\n")
                self._log_event(f"{self.tr('build_failed', name=entry.display_name)}: {e}")
                self._post_status(self.tr("build_failed", name=entry.display_name))
                raise
        if open_folder and last_output:
            self._open_build_folder(last_output)

    def _android_apk_path(self):
        apk_dir = os.path.join(ANDROID_APP_DIR, "app", "build", "outputs", "apk", "debug")
        preferred = os.path.join(apk_dir, "gbs-player.apk")
        if os.path.isfile(preferred):
            return preferred
        return os.path.join(apk_dir, "app-debug.apk")

    def _adb_install_command(self, apk):
        self._sync_build_settings_vars()
        cmd = [self.adb_path]
        serial = self.adb_device_serial.strip()
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["install", "-r", apk])
        return cmd

    def _adb_base_command(self):
        self._sync_build_settings_vars()
        cmd = [self.adb_path]
        serial = self.adb_device_serial.strip()
        if serial:
            cmd.extend(["-s", serial])
        return cmd

    def _resolve_adb_device_serial_sync(self):
        self._sync_build_settings_vars()
        if threading.current_thread() is threading.main_thread():
            selected = self.adb_device_choices.get(self.adb_device_var.get(), "").strip()
            if selected:
                self.adb_device_serial = selected
                self._save_config()
                return selected
        if self.adb_device_serial.strip():
            return self.adb_device_serial.strip()
        devices = self._list_adb_devices_sync()
        self.root.after(0, lambda: self._set_adb_device_values(devices))
        if len(devices) == 1:
            self.adb_device_serial = devices[0][0]
            self._save_config()
            return self.adb_device_serial
        if len(devices) > 1:
            raise RuntimeError("Multiple ADB devices found. Select a target from the ADB dropdown.")
        raise RuntimeError(self.tr("adb_no_device"))

    def _selected_android_rom_ids(self):
        entry = self._current_entry()
        if not entry:
            raise RuntimeError(self.tr("no_source_selected"))
        return self._android_rom_ids_for_entry(entry)

    def _android_rom_ids_for_entry(self, entry):
        candidates = []
        for value in (entry.source_id, android_rom_id_from_path(entry.source_path)):
            if value and value not in candidates:
                candidates.append(value)
        return candidates

    def _android_sav_device_path(self, rom_id):
        return f"/data/data/{ANDROID_PACKAGE}/files/rom/bundled_v5/{rom_id}/gbs_player.sav"

    def _android_rom_root_path(self):
        return f"/data/data/{ANDROID_PACKAGE}/files/rom"

    def _android_sync_dir(self):
        path = os.path.join(APP_DIR, "build", "android_sync")
        os.makedirs(path, exist_ok=True)
        return path

    def _run_adb_bytes(self, args, input_bytes=None, log_stdout=True):
        cmd = self._adb_base_command() + args
        self._append_log("$ " + " ".join(cmd) + "\n")
        try:
            proc = subprocess.run(
                cmd,
                cwd=APP_DIR,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("ADB command timed out")
        if proc.stdout and log_stdout:
            try:
                self._append_log(proc.stdout.decode("utf-8", errors="replace"))
            except Exception:
                self._append_log(f"<{len(proc.stdout)} bytes>\n")
        if proc.stderr:
            self._append_log(proc.stderr.decode("utf-8", errors="replace"))
        if proc.returncode != 0:
            raise RuntimeError(f"command failed with exit code {proc.returncode}")
        return proc.stdout

    def _run_adb_logged_sync(self, args, timeout=60):
        cmd = self._adb_base_command() + args
        self._append_log("$ " + " ".join(cmd) + "\n")
        try:
            proc = subprocess.run(
                cmd,
                cwd=APP_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("ADB command timed out")
        if proc.stdout:
            self._append_log(proc.stdout)
        if proc.returncode != 0:
            raise RuntimeError(f"command failed with exit code {proc.returncode}")
        return proc.stdout

    def _list_android_sav_paths_sync(self):
        root = self._android_rom_root_path()
        script = f"find {quote_sh(root)} -type f -name gbs_player.sav 2>/dev/null"
        try:
            raw = self._run_adb_bytes(["exec-out", "run-as", ANDROID_PACKAGE, "sh", "-c", script], log_stdout=False)
        except Exception:
            return []
        paths = []
        for line in raw.decode("utf-8", errors="replace").splitlines():
            path = line.strip()
            if path and path not in paths:
                paths.append(path)
        return paths

    def _read_android_sav_path_sync(self, device_path):
        raw = self._run_adb_bytes(["exec-out", "run-as", ANDROID_PACKAGE, "cat", device_path], log_stdout=False)
        if len(raw) < 26:
            raise RuntimeError(self.tr("android_sync_missing"))
        magic = struct.unpack_from("<H", raw, 0)[0]
        if magic != SRAM_MAGIC:
            preview = raw[:80].decode("utf-8", errors="replace").strip()
            raise RuntimeError(preview or self.tr("android_sync_missing"))
        return raw

    def _pull_android_sav_sync(self, rom_ids):
        self._resolve_adb_device_serial_sync()
        last_error = None
        device_paths = []
        for rom_id in rom_ids:
            path = self._android_sav_device_path(rom_id)
            if path not in device_paths:
                device_paths.append(path)

        for device_path in device_paths:
            try:
                raw = self._read_android_sav_path_sync(device_path)
            except Exception as e:
                last_error = str(e)
                continue
            break
        else:
            tried = ", ".join(device_paths)
            if last_error:
                raise RuntimeError(f"{self.tr('android_sync_missing')} ({last_error}; tried: {tried})")
            raise RuntimeError(f"{self.tr('android_sync_missing')} (tried: {tried})")
        rom_id = os.path.basename(os.path.dirname(device_path)) or "device"
        local_name = re.sub(r"[^0-9A-Za-z._-]+", "_", rom_id).strip("._-") or "device"
        local_path = os.path.join(self._android_sync_dir(), f"{local_name}.device.sav")
        with open(local_path, "wb") as f:
            f.write(raw)
        pulled = SaveData(self.sav.num_songs)
        pulled.load(local_path)
        return rom_id, pulled

    def _android_sav_exists_sync(self, rom_id):
        device_path = self._android_sav_device_path(rom_id)
        script = f"if [ -e {quote_sh(device_path)} ]; then echo yes; fi"
        try:
            raw = self._run_adb_bytes(["exec-out", "run-as", ANDROID_PACKAGE, "sh", "-c", script], log_stdout=False)
        except Exception:
            return False
        return raw.strip() == b"yes"

    def _push_android_sav_sync(self, rom_ids, sav_data=None):
        target_sav = sav_data or self.sav
        if not target_sav:
            raise RuntimeError(self.tr("load_file_first"))
        self._resolve_adb_device_serial_sync()
        self._run_adb_logged_sync(["shell", "am", "force-stop", ANDROID_PACKAGE])
        existing_paths = self._list_android_sav_paths_sync()
        selected_paths = [self._android_sav_device_path(candidate) for candidate in rom_ids]
        device_path = next((path for path in selected_paths if path in existing_paths), None)
        if device_path is None:
            device_path = selected_paths[0]
        rom_id = os.path.basename(os.path.dirname(device_path)) or rom_ids[0]
        local_path = os.path.join(self._android_sync_dir(), f"{rom_id}.upload.sav")
        target_sav.save(local_path)
        device_dir = os.path.dirname(device_path).replace("\\", "/")
        tmp_path = f"/data/local/tmp/{ANDROID_PACKAGE}.gbs_player.sav"
        self._run_adb_logged_sync(["push", local_path, tmp_path])
        self._run_adb_logged_sync(["shell", "chmod", "644", tmp_path])
        self._run_adb_logged_sync(["shell", "run-as", ANDROID_PACKAGE, "mkdir", "-p", device_dir])
        self._run_adb_logged_sync(["shell", "run-as", ANDROID_PACKAGE, "cp", tmp_path, device_path])
        return rom_id

    def _push_entries_android_sav_sync(self, entries):
        pushed = []
        self._resolve_adb_device_serial_sync()
        self._run_adb_logged_sync(["shell", "am", "force-stop", ANDROID_PACKAGE])
        for entry in entries:
            if not entry or not entry.sav:
                continue
            rom_id = self._push_android_sav_sync(self._android_rom_ids_for_entry(entry), sav_data=entry.sav)
            pushed.append(rom_id)
        return pushed

    def _pull_android_sav(self):
        if self._build_running:
            return
        if not self.sav:
            messagebox.showinfo(self.tr("info"), self.tr("load_file_first"))
            return
        if not any(serial for serial, _name in self.adb_devices):
            msg = self.tr("adb_no_device")
            self._set_status(msg)
            self._log_event(msg)
            self._update_state()
            return
        self._on_adb_device_selected()
        self._build_running = True
        self._set_progress(0, 1)
        self._log_event(self.tr("android_pull_sav"))
        self._update_state()
        try:
            rom_ids = self._selected_android_rom_ids()
        except Exception as e:
            self._build_running = False
            self._set_progress(0, 100)
            self._update_state()
            messagebox.showinfo(self.tr("info"), str(e))
            return

        def worker():
            try:
                pulled_rom_id, pulled = self._pull_android_sav_sync(rom_ids)

                def apply():
                    pulled.song_names = list(self.sav.song_names)
                    pulled.name_magic = self.sav.name_magic
                    pulled.custom_title = self.sav.custom_title
                    pulled.custom_author = self.sav.custom_author
                    changed = pulled.state_tuple() != self.sav.state_tuple()
                    self.sav = pulled
                    entry = self._current_entry()
                    if changed:
                        self._mark_dirty()
                    if entry:
                        entry.sav = pulled
                        if changed:
                            entry.dirty = True
                    self._apply_loaded_state()
                    self._set_progress(1, 1)
                    msg = self.tr("android_sync_pull_done", rom_id=pulled_rom_id)
                    self._set_status(msg)
                    self._log_event(msg)
                self.root.after(0, apply)
            except Exception as e:
                self._append_log(f"ERROR: {e}\n")
                self._log_event(f"{self.tr('android_pull_sav')}: ERROR: {e}")
                self._post_status(str(e))
            finally:
                def finish():
                    self._build_running = False
                    self._set_progress(0, 100)
                    self._update_state()
                self.root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def _push_android_sav(self):
        if self._build_running:
            return
        if not self.sav:
            messagebox.showinfo(self.tr("info"), self.tr("load_file_first"))
            return
        if not any(serial for serial, _name in self.adb_devices):
            msg = self.tr("adb_no_device")
            self._set_status(msg)
            self._log_event(msg)
            self._update_state()
            return
        self._on_adb_device_selected()
        self._sync_current_song_edit()
        self._sync_metadata_fields()
        self._store_active_entry()
        self._build_running = True
        self._set_progress(0, 1)
        self._log_event(self.tr("android_push_sav"))
        self._update_state()
        try:
            rom_ids = self._selected_android_rom_ids()
        except Exception as e:
            self._build_running = False
            self._set_progress(0, 100)
            self._update_state()
            messagebox.showinfo(self.tr("info"), str(e))
            return

        def worker():
            try:
                pushed_rom_id = self._push_android_sav_sync(rom_ids)
                self._set_progress(1, 1)
                msg = self.tr("android_sync_push_done", rom_id=pushed_rom_id)
                self._log_event(msg)
                self._post_status(msg)
            except Exception as e:
                self._append_log(f"ERROR: {e}\n")
                self._log_event(f"{self.tr('android_push_sav')}: ERROR: {e}")
                self._post_status(str(e))
            finally:
                def finish():
                    self._build_running = False
                    self._set_progress(0, 100)
                    self._update_state()
                self.root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def _install_android_apk_sync(self, overwrite_save=False, overwrite_entries=None):
        apk = self._android_apk_path()
        if not os.path.isfile(apk):
            raise FileNotFoundError(apk)
        self._resolve_adb_device_serial_sync()
        self._run_adb_logged_sync(["install", "-r", apk], timeout=180)
        if overwrite_save:
            entries = [entry for entry in (overwrite_entries or [self._current_entry()]) if entry and entry.sav]
            if entries:
                self._push_entries_android_sav_sync(entries)
        return apk

    def _install_android_apk(self):
        if self._build_running:
            return
        if not any(serial for serial, _name in self.adb_devices):
            msg = self.tr("adb_no_device")
            self._set_status(msg)
            self._log_event(msg)
            self._update_state()
            return
        self._on_adb_device_selected()
        self._sync_build_settings_vars()
        overwrite_save = bool(self.overwrite_save_var.get())
        if overwrite_save and self.sav:
            self._sync_current_song_edit()
            self._sync_metadata_fields()
            self._store_active_entry()
        overwrite_entries = [self._current_entry()] if overwrite_save else None
        self._build_running = True
        self._set_progress(0, 1)
        self._log_event(self.tr("android_install"))
        self._update_state()

        def worker():
            try:
                apk = self._install_android_apk_sync(overwrite_save=overwrite_save, overwrite_entries=overwrite_entries)
                self._set_progress(1, 1)
                self._log_event(self.tr("build_done", path=apk))
                self._post_status(self.tr("build_done", path=apk))
            except Exception as e:
                self._append_log(f"ERROR: {e}\n")
                self._log_event(f"{self.tr('build_failed', name='Android install')}: {e}")
                self._post_status(self.tr("build_failed", name="Android install"))
            finally:
                def finish():
                    self._build_running = False
                    self._set_progress(0, 100)
                    self._update_state()
                self.root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def _build_android_apk_sync(self):
        self._sync_build_settings_vars()
        command = (
            f"$env:JAVA_HOME={self.java_home!r}; "
            f"$env:Path=\"$env:JAVA_HOME\\bin;$env:Path\"; "
            ".\\gradlew.bat assembleDebug"
        )
        self._run_logged(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], cwd=ANDROID_APP_DIR)
        return self._android_apk_path()

    def _build_android_apk(self, install_after=False):
        if self._build_running:
            return
        if install_after and not any(serial for serial, _name in self.adb_devices):
            msg = self.tr("adb_no_device")
            self._set_status(msg)
            self._log_event(msg)
            self._update_state()
            return
        if install_after:
            self._on_adb_device_selected()
        self._sync_build_settings_vars()
        overwrite_save = bool(self.overwrite_save_var.get()) if install_after else False
        if overwrite_save and self.sav:
            self._sync_current_song_edit()
            self._sync_metadata_fields()
            self._store_active_entry()
        overwrite_entries = [self._current_entry()] if overwrite_save else None
        self._build_running = True
        self._set_progress(0, 2 if install_after else 1)
        self._log_event(self.tr("android_build_install") if install_after else self.tr("android_apk"))
        self._update_state()

        def worker():
            try:
                apk = self._build_android_apk_sync()
                self._set_progress(1, 2 if install_after else 1)
                if install_after:
                    self._log_event(self.tr("android_install"))
                    self._post_status(self.tr("android_install"))
                    self._install_android_apk_sync(overwrite_save=overwrite_save, overwrite_entries=overwrite_entries)
                    self._set_progress(2, 2)
                self._log_event(self.tr("build_done", path=apk))
                self._post_status(self.tr("build_done", path=apk))
            except Exception as e:
                self._append_log(f"ERROR: {e}\n")
                self._log_event(f"{self.tr('build_failed', name='Android APK')}: {e}")
                self._post_status(self.tr("build_failed", name="Android APK"))
            finally:
                def finish():
                    self._build_running = False
                    self._set_progress(0, 100)
                    self._update_state()
                self.root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def _build_all_and_install(self):
        if not self.entries:
            messagebox.showinfo(self.tr("info"), self.tr("no_source_selected"))
            self._log_event(self.tr("no_source_selected"))
            return
        if self._build_running:
            return
        if not any(serial for serial, _name in self.adb_devices):
            msg = self.tr("adb_no_device")
            self._set_status(msg)
            self._log_event(msg)
            self._update_state()
            return
        self._on_adb_device_selected()
        self._sync_build_settings_vars()
        overwrite_save = bool(self.overwrite_save_var.get())
        if overwrite_save and self.sav:
            self._sync_current_song_edit()
            self._sync_metadata_fields()
            self._store_active_entry()
        self._sync_current_song_edit()
        self._store_active_entry()
        overwrite_entries = list(self.entries) if overwrite_save else None
        self._build_running = True
        self._set_progress(0, len(self.entries) + 2)
        self._log_event(self.tr("android_build_install_all"))
        self._update_state()

        def worker():
            try:
                self._build_entries_sync(self.entries, android_assets=True)
                apk = self._build_android_apk_sync()
                self._set_progress(len(self.entries) + 1, len(self.entries) + 2)
                self._log_event(self.tr("android_install"))
                self._post_status(self.tr("android_install"))
                self._install_android_apk_sync(overwrite_save=overwrite_save, overwrite_entries=overwrite_entries)
                self._set_progress(len(self.entries) + 2, len(self.entries) + 2)
                self._log_event(self.tr("build_done", path=apk))
                self._post_status(self.tr("build_done", path=apk))
            except Exception as e:
                self._append_log(f"ERROR: {e}\n")
                self._log_event(f"{self.tr('build_failed', name=self.tr('android_build_install_all'))}: {e}")
                self._post_status(self.tr("build_failed", name=self.tr("android_build_install_all")))
            finally:
                def finish():
                    self._build_running = False
                    self._refresh_sources()
                    self._set_progress(0, 100)
                    self._update_state()
                    self._save_config()
                self.root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()


def main():
    try:
        root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    except Exception:
        root = tk.Tk()
    SavEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
