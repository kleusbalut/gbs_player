#!/usr/bin/env python3
"""Fetch the SameBoy source tree required by the Android JNI build."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


SAMEBOY_VERSION = "v1.0.2"
SAMEBOY_URL = (
    "https://github.com/LIJI32/SameBoy/archive/refs/tags/"
    f"{SAMEBOY_VERSION}.zip"
)
REQUIRED_FILES = (
    "Core/apu.c",
    "Core/gb.c",
    "Core/gb.h",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def verify_sameboy(path: Path) -> bool:
    return all((path / item).is_file() for item in REQUIRED_FILES)


def fetch_sameboy(force: bool) -> Path:
    root = repo_root()
    vendor_dir = root / "vendor"
    target_dir = vendor_dir / "sameboy"

    if target_dir.exists() and verify_sameboy(target_dir) and not force:
        print(f"SameBoy already exists: {target_dir}")
        return target_dir

    if target_dir.exists() and not force:
        raise SystemExit(
            f"{target_dir} exists but is incomplete. Re-run with --force to replace it."
        )

    vendor_dir.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="sameboy-") as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / "sameboy.zip"
        extract_dir = tmp_dir / "extract"

        print(f"Downloading {SAMEBOY_URL}")
        urllib.request.urlretrieve(SAMEBOY_URL, archive)

        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)

        extracted_roots = [p for p in extract_dir.iterdir() if p.is_dir()]
        if len(extracted_roots) != 1:
            raise SystemExit("Unexpected SameBoy archive layout")

        source_dir = extracted_roots[0]
        if not verify_sameboy(source_dir):
            raise SystemExit("Downloaded SameBoy archive is missing required Core files")

        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.move(str(source_dir), str(target_dir))

    print(f"Installed SameBoy {SAMEBOY_VERSION}: {target_dir}")
    return target_dir


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace vendor/sameboy even if it already exists",
    )
    args = parser.parse_args(argv)

    fetch_sameboy(args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
