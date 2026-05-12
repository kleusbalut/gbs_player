#!/usr/bin/env python3
"""
Package the built GBS player ROM and metadata into the Android app assets.

Usage:
  python tools/package_android.py --gbs samples/gbs/music.gbs
  python tools/package_android.py --gbs samples/gbs/music.gbs --rom build/gbs_player.gbc --sav path/to/seed.sav
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import re


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gbs", required=True, help="Source .gbs file used to build the ROM")
    parser.add_argument("--rom", default=os.path.join("build", "gbs_player.gbc"))
    parser.add_argument("--sav", default=None, help="Optional ROM-specific seed .sav to bundle")
    parser.add_argument("--assets-dir", default=os.path.join("apps", "android", "app", "src", "main", "assets", "game"))
    args = parser.parse_args()

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    rom_path = os.path.join(root, args.rom)
    sav_path = os.path.join(root, args.sav) if args.sav else None
    gbs_path = os.path.join(root, args.gbs)
    assets_dir = os.path.join(root, args.assets_dir)
    rom_id = make_rom_id(os.path.splitext(os.path.basename(gbs_path))[0])
    rom_assets_dir = os.path.join(assets_dir, "roms", rom_id)
    metadata_path = os.path.join(rom_assets_dir, "metadata.json")
    out_rom = os.path.join(rom_assets_dir, "rom.gbc")
    out_sav = os.path.join(rom_assets_dir, "seed.sav")
    manifest_path = os.path.join(assets_dir, "manifest.json")

    if not os.path.isfile(rom_path):
        raise SystemExit(f"ROM not found: {rom_path}")
    if not os.path.isfile(gbs_path):
        raise SystemExit(f"GBS not found: {gbs_path}")

    os.makedirs(rom_assets_dir, exist_ok=True)
    shutil.copyfile(rom_path, out_rom)
    if sav_path and os.path.isfile(sav_path):
        shutil.copyfile(sav_path, out_sav)

    subprocess.check_call(
        [sys.executable, os.path.join(root, "tools", "build.py"), "metadata", gbs_path, metadata_path],
        cwd=root,
    )
    update_manifest(manifest_path, rom_id, metadata_path, include_seed=sav_path is not None and os.path.isfile(out_sav))

    # Keep the legacy single-ROM asset paths populated for older APKs and simple inspection.
    shutil.copyfile(out_rom, os.path.join(assets_dir, "rom.gbc"))
    shutil.copyfile(metadata_path, os.path.join(assets_dir, "metadata.json"))
    if sav_path and os.path.isfile(out_sav):
        shutil.copyfile(out_sav, os.path.join(assets_dir, "seed.sav"))

    print(f"[package_android.py] bundled ROM updated: {rom_id}")


def make_rom_id(name):
    rom_id = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return rom_id or "gbs_player"


def update_manifest(manifest_path, rom_id, metadata_path, include_seed):
    manifest = {"roms": []}
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    entry = {
        "id": rom_id,
        "title": metadata.get("title") or rom_id,
        "author": metadata.get("author") or "Unknown Author",
        "rom": f"roms/{rom_id}/rom.gbc",
        "metadata": f"roms/{rom_id}/metadata.json",
    }
    if include_seed:
        entry["seed"] = f"roms/{rom_id}/seed.sav"

    roms = [rom for rom in manifest.get("roms", []) if rom.get("id") != rom_id]
    roms.append(entry)
    roms.sort(key=lambda rom: rom.get("title", rom.get("id", "")))
    manifest["roms"] = roms

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
