#!/usr/bin/env python3
"""
Download proot static binaries for all supported architectures
and place them in pyproot/binaries/ for bundling inside the wheel.

Usage:
    python scripts/download_binaries.py              # all arches (desktop + android)
    python scripts/download_binaries.py x86_64       # specific arch(es)
    python scripts/download_binaries.py --check      # verify existing files
    python scripts/download_binaries.py --desktop    # desktop binaries only
    python scripts/download_binaries.py --android    # android binaries only
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

PROOT_VERSION = "latest"

# Desktop/Linux — proot.gitlab.io
DESKTOP_DOWNLOADS: dict[str, tuple[str, str | None]] = {
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

# Android/Mobile — skirsten (Termux-based)
ANDROID_DOWNLOADS: dict[str, tuple[str, str | None]] = {
    "x86_64": (
        "https://skirsten.github.io/proot-portable-android-binaries/x86_64/proot",
        None,
    ),
    "x86": (
        "https://skirsten.github.io/proot-portable-android-binaries/x86/proot",
        None,
    ),
    "aarch64": (
        "https://skirsten.github.io/proot-portable-android-binaries/aarch64/proot",
        None,
    ),
    "armv7l": (
        "https://skirsten.github.io/proot-portable-android-binaries/armv7/proot",
        None,
    ),
}

# All unique arches across both sources
ALL_ARCHES = sorted(set(DESKTOP_DOWNLOADS) | set(ANDROID_DOWNLOADS))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_binary(arch: str, url: str, dest: Path, expected: str | None, force: bool, label: str) -> Path | None:
    """Download a single binary from url to dest. Returns dest on success, None on failure."""
    if dest.exists() and not force:
        print(f"  [skip] {dest.name} already exists (use --force to re-download)")
        return dest

    print(f"  [download] {arch} ({label}): {url}")
    tmp = dest.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(url, tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        print(f"  [ERROR] Failed to download {arch} ({label}): {exc}", file=sys.stderr)
        return None

    if expected:
        actual = sha256(tmp)
        if actual != expected:
            tmp.unlink()
            print(f"  [ERROR] SHA-256 mismatch for {arch} ({label})", file=sys.stderr)
            print(f"          expected: {expected}", file=sys.stderr)
            print(f"          actual:   {actual}", file=sys.stderr)
            return None

    tmp.rename(dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  [ok] {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def download_arch(arch: str, force: bool = False, desktop: bool = True, android: bool = True) -> bool:
    """
    Download binaries for a single arch from all requested sources.
    Desktop binary  → proot-<arch>
    Android binary  → proot-<arch>-android
    Returns True if every requested source succeeded.
    """
    success = True

    if desktop:
        if arch in DESKTOP_DOWNLOADS:
            url, expected = DESKTOP_DOWNLOADS[arch]
            dest = BINARIES_DIR / f"proot-{arch}"
            if not download_binary(arch, url, dest, expected, force, "desktop"):
                success = False
        else:
            print(f"  [skip] {arch}: no desktop source available")

    if android:
        if arch in ANDROID_DOWNLOADS:
            url, expected = ANDROID_DOWNLOADS[arch]
            dest = BINARIES_DIR / f"proot-{arch}-android"
            if not download_binary(arch, url, dest, expected, force, "android"):
                success = False
        else:
            print(f"  [skip] {arch}: no android source available")

    return success


def check_binaries(desktop: bool = True, android: bool = True):
    print("Checking bundled binaries:")
    all_ok = True

    for arch in ALL_ARCHES:
        if desktop and arch in DESKTOP_DOWNLOADS:
            dest = BINARIES_DIR / f"proot-{arch}"
            all_ok &= _check_file(dest)

        if android and arch in ANDROID_DOWNLOADS:
            dest = BINARIES_DIR / f"proot-{arch}-android"
            all_ok &= _check_file(dest)

    return all_ok


def _check_file(dest: Path) -> bool:
    if dest.exists():
        executable = os.access(dest, os.X_OK)
        status = "ok" if executable else "NOT EXECUTABLE"
        print(f"  {dest.name}: {dest.stat().st_size:,} bytes [{status}]")
        return executable
    else:
        print(f"  {dest.name}: MISSING")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download proot binaries for bundling.")
    parser.add_argument("arches", nargs="*", help="Architectures to download (default: all)")
    parser.add_argument("--force", action="store_true", help="Re-download even if exists")
    parser.add_argument("--check", action="store_true", help="Check existing binaries only")
    parser.add_argument("--desktop", action="store_true", help="Download desktop binaries only")
    parser.add_argument("--android", action="store_true", help="Download android binaries only")
    args = parser.parse_args()

    # If neither flag is set, download both
    want_desktop = args.desktop or not args.android
    want_android = args.android or not args.desktop

    BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    if args.check:
        ok = check_binaries(desktop=want_desktop, android=want_android)
        sys.exit(0 if ok else 1)

    arches = args.arches or ALL_ARCHES
    invalid = [a for a in arches if a not in ALL_ARCHES]
    if invalid:
        print(f"Unknown architectures: {invalid}. Valid: {ALL_ARCHES}", file=sys.stderr)
        sys.exit(1)

    sources = []
    if want_desktop:
        sources.append("Desktop (proot.gitlab.io)")
    if want_android:
        sources.append("Android (skirsten)")

    print(f"Downloading proot {PROOT_VERSION} binaries to {BINARIES_DIR}/")
    print(f"Sources: {', '.join(sources)}")
    print(f"Architectures: {arches}\n")

    success = []
    failed = []
    for arch in arches:
        result = download_arch(arch, force=args.force, desktop=want_desktop, android=want_android)
        (success if result else failed).append(arch)

    print(f"\nDone. {len(success)} succeeded, {len(failed)} failed.")
    if failed:
        print(f"Failed: {failed}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()