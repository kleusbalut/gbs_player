#!/usr/bin/env python3
"""Fetch PKMN font files required to regenerate src/player/jp_font.h."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


PKMNFONT_URL = "https://github.com/nue-of-k/pkmn/releases/latest/download/pkmnfont.zip"
REQUIRED_FILES = (
    "pkmn_r.ttf",
    "pkmn_s.ttf",
    "pkmn_w.ttf",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def verify_pkmnfont(path: Path) -> bool:
    return all((path / item).is_file() for item in REQUIRED_FILES)


def move_to_local_trash(path: Path) -> None:
    trash_dir = repo_root() / ".trash"
    trash_dir.mkdir(exist_ok=True)
    dst = trash_dir / path.name
    if dst.exists():
        i = 1
        while True:
            candidate = trash_dir / f"{path.name}.{i}"
            if not candidate.exists():
                dst = candidate
                break
            i += 1
    shutil.move(str(path), str(dst))


def fetch_pkmnfont(force: bool) -> Path:
    root = repo_root()
    target_dir = root / "assets" / "fonts" / "pkmnfont"

    if target_dir.exists() and verify_pkmnfont(target_dir) and not force:
        print(f"PKMN font already exists: {target_dir}")
        return target_dir

    if target_dir.exists() and not force:
        raise SystemExit(
            f"{target_dir} exists but is incomplete. Re-run with --force to replace it."
        )

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pkmnfont-") as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / "pkmnfont.zip"
        extract_dir = tmp_dir / "extract"

        print(f"Downloading {PKMNFONT_URL}")
        urllib.request.urlretrieve(PKMNFONT_URL, archive)

        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)

        candidates = [p for p in extract_dir.rglob("pkmn_s.ttf") if p.is_file()]
        if not candidates:
            raise SystemExit("Downloaded PKMN font archive is missing pkmn_s.ttf")

        source_dir = candidates[0].parent
        if not verify_pkmnfont(source_dir):
            raise SystemExit("Downloaded PKMN font archive is missing required TTF files")

        if target_dir.exists():
            move_to_local_trash(target_dir)
        shutil.copytree(source_dir, target_dir)

    print(f"Installed PKMN font: {target_dir}")
    return target_dir


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace assets/fonts/pkmnfont even if it already exists",
    )
    args = parser.parse_args(argv)

    fetch_pkmnfont(args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
