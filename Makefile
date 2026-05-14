# ================================================================
# Makefile for GBS Player (GBDK-2020)
# Usage:
#   make GBDK=C:/dev/gbdk GBS=samples/gbs/music.gbs
#   make GBDK=C:/dev/gbdk GBS=samples/gbs/music.gb   # supported Game Freak GB/GBC ROMs
#
# Windows native Python + GNU make is supported. MSYS2 is optional.
# make clean sends generated files to the Windows Recycle Bin when possible.
#
# Requires:
#   - GBDK-2020  https://github.com/gbdk-2020/gbdk-2020
#   - make + python3
# ================================================================

GBDK    ?= C:/dev/gbdk
PY      ?= python

GBS     ?= samples/gbs/music.gbs
SAV     ?=
SRC      = src/player/main.c
HEADER   = src/player/gbs_info.h
BUILDDIR ?= build
PLAYER   = $(BUILDDIR)/player.gb
OUT      = $(BUILDDIR)/gbs_player.gbc
TMPDIR   = $(BUILDDIR)/tmp

CC       = $(GBDK)/bin/lcc

# sdldgb (Windows binary) が MSYS2 の /tmp パスを解決できない問題を回避。
# lcc の一時ファイルを build/tmp に生成させる。
export TMP  := $(TMPDIR)
export TEMP := $(TMPDIR)


CFLAGS   = -Wf--max-allocs-per-node200000 \
           -Wl-yt3 -Wl-ya2 -Wl-yo2 \
           -Wl-b_DATA=0xC2C8 \
           -msm83:gb

.PHONY: all header clean build_dir android-assets FORCE

all: $(OUT)

# Step 1 - generate gbs_info.h from GBS file
$(HEADER): FORCE
	$(PY) tools/build.py header "$(GBS)"

# Step 2 - compile player ROM
# lcc は player.ihx / .noi も出力先と同じディレクトリに生成する
$(PLAYER): $(SRC) $(HEADER) | build_dir
	$(CC) $(CFLAGS) -o $@ $<

# Order-only prerequisite: create build/ and temp dir if absent
build_dir:
	$(PY) tools/make_helpers.py mkdir $(BUILDDIR) $(TMPDIR)

# Step 3 - merge player + GBS payload into final ROM
# build/ フォルダが存在しても失敗しないよう order-only 依存関係を使用
$(OUT): $(PLAYER) | build_dir
	$(PY) tools/build.py merge $(PLAYER) "$(GBS)" $@
	@$(PY) -c "print('Done: $(OUT)')"

android-assets:
	$(MAKE) -B $(OUT) GBDK=$(GBDK) GBS="$(GBS)" PY=$(PY)
	$(PY) tools/package_android.py --gbs "$(GBS)" --rom $(OUT) $(if $(SAV),--sav "$(SAV)")

header: $(HEADER)

# 生成ROM/中間ファイルのみごみ箱へ移動。
# build/ フォルダ内の .sav (SRAMセーブ) 等は保持される。
clean:
	$(PY) tools/make_helpers.py clean $(OUT) $(PLAYER) $(BUILDDIR)/player.ihx $(BUILDDIR)/player.noi src/player/gbs_info.h
