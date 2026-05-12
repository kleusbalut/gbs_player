#!/usr/bin/env python3
"""Small portable helpers used by the project Makefile."""
import os
import sys


def mkdir(paths):
    for path in paths:
        if path:
            os.makedirs(path, exist_ok=True)


def _recycle_windows(paths):
    import ctypes
    from ctypes import wintypes

    existing = [os.path.abspath(path) for path in paths if os.path.exists(path)]
    if not existing:
        return

    FO_DELETE = 0x0003
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_NOERRORUI = 0x0400
    FOF_SILENT = 0x0004

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.UINT),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    p_from = ctypes.create_unicode_buffer("\0".join(existing) + "\0\0")
    op = SHFILEOPSTRUCTW(
        None,
        FO_DELETE,
        ctypes.cast(p_from, wintypes.LPCWSTR),
        None,
        FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT,
        False,
        None,
        None,
    )
    sh_file_operation = ctypes.windll.shell32.SHFileOperationW
    sh_file_operation.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
    sh_file_operation.restype = ctypes.c_int
    result = sh_file_operation(ctypes.byref(op))
    if result != 0:
        raise OSError(f"SHFileOperationW failed with code {result}")


def _move_to_local_trash(paths):
    trash_dir = ".trash"
    os.makedirs(trash_dir, exist_ok=True)
    for path in paths:
        if not os.path.exists(path):
            continue
        name = os.path.basename(path)
        dst = os.path.join(trash_dir, name)
        if os.path.exists(dst):
            base, ext = os.path.splitext(name)
            i = 1
            while os.path.exists(dst):
                dst = os.path.join(trash_dir, f"{base}.{i}{ext}")
                i += 1
        os.replace(path, dst)


def clean(paths):
    if os.name == "nt":
        try:
            _recycle_windows(paths)
            return
        except OSError as exc:
            print(f"warning: Windows Recycle Bin unavailable ({exc}); moving files to .trash")
    else:
        print("warning: Recycle Bin is Windows-only; moving files to .trash")
    _move_to_local_trash(paths)


def main(argv):
    if len(argv) < 2:
        raise SystemExit("usage: make_helpers.py <mkdir|clean> <paths...>")
    command, paths = argv[1], argv[2:]
    if command == "mkdir":
        mkdir(paths)
    elif command == "clean":
        clean(paths)
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main(sys.argv)
