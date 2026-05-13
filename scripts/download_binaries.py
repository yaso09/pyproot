#!/usr/bin/env python3
"""
Download proot static binaries for all supported architectures
and place them in pyproot/binaries/ for bundling inside the wheel.

Usage:
    python scripts/download_binaries.py              # all arches
    python scripts/download_binaries.py x86_64       # specific arch(es)
    python scripts/download_binaries.py --check      # verify existing files
"""

import argparse
import hashlib
import os
import stat
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BINARIES_DIR = REPO_ROOT / "pyproot" / "binaries"

# Resmi proot indirme URL'leri.
# Kaynak: https://proot.gitlab.io/proot/bin/
PROOT_VERSION = "latest"
DOWNLOADS: dict[str, tuple[str, str | None]] = {
    "x86_64": (
        "https://proot.gitlab.io/proot/bin/proot",
        None,
    ),
    "aarch64": (
        "https://proot.gitlab.io/proot/bin/proot-arm64",
        None,
    ),
    "armv7l": (
        "https://proot.gitlab.io/proot/bin/proot-arm",
        None,
    ),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_arch(arch: str, force: bool = False) -> Path:
    url, expected = DOWNLOADS[arch]
    dest = BINARIES_DIR / f"proot-{arch}"

    if dest.exists() and not force:
        print(f"  [skip] {dest.name} already exists (use --force to re-download)")
        return dest

    print(f"  [download] {arch}: {url}")
    tmp = dest.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(url, tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        print(f"  [ERROR] Failed to download {arch}: {exc}", file=sys.stderr)
        return None

    if expected:
        actual = sha256(tmp)
        if actual != expected:
            tmp.unlink()
            print(f"  [ERROR] SHA-256 mismatch for {arch}", file=sys.stderr)
            print(f"          expected: {expected}", file=sys.stderr)
            print(f"          actual:   {actual}", file=sys.stderr)
            return None

    tmp.rename(dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  [ok] {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def check_binaries():
    print("Checking bundled binaries:")
    all_ok = True
    for arch in DOWNLOADS:
        dest = BINARIES_DIR / f"proot-{arch}"
        if dest.exists():
            executable = os.access(dest, os.X_OK)
            status = "ok" if executable else "NOT EXECUTABLE"
            print(f"  {dest.name}: {dest.stat().st_size:,} bytes [{status}]")
            if not executable:
                all_ok = False
        else:
            print(f"  proot-{arch}: MISSING")
            all_ok = False
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Download proot binaries for bundling.")
    parser.add_argument("arches", nargs="*", help="Architectures to download (default: all)")
    parser.add_argument("--force", action="store_true", help="Re-download even if exists")
    parser.add_argument("--check", action="store_true", help="Check existing binaries only")
    args = parser.parse_args()

    BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    if args.check:
        ok = check_binaries()
        sys.exit(0 if ok else 1)

    arches = args.arches or list(DOWNLOADS.keys())
    invalid = [a for a in arches if a not in DOWNLOADS]
    if invalid:
        print(f"Unknown architectures: {invalid}. Valid: {list(DOWNLOADS.keys())}", file=sys.stderr)
        sys.exit(1)

    print(f"Downloading proot {PROOT_VERSION} binaries to {BINARIES_DIR}/")
    success = []
    failed = []
    for arch in arches:
        result = download_arch(arch, force=args.force)
        (success if result else failed).append(arch)

    print(f"\nDone. {len(success)} succeeded, {len(failed)} failed.")
    if failed:
        print(f"Failed: {failed}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
