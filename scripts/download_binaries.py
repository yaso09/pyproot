#!/usr/bin/env python3
"""
Download proot static binaries for all supported architectures
and place them in pyproot/binaries/ for bundling inside the wheel.

Usage:
    python scripts/download_binaries.py              # all arches
    python scripts/download_binaries.py x86_64       # specific arch(es)
    python scripts/download_binaries.py --check      # verify existing files
    python scripts/download_binaries.py --android    # use android binaries
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


def is_android() -> bool:
    return (
        os.path.exists("/system/build.prop")
        or "ANDROID_ROOT" in os.environ
        or "ANDROID_DATA" in os.environ
    )


def get_downloads(android: bool = False) -> dict[str, tuple[str, str | None]]:
    return ANDROID_DOWNLOADS if android else DESKTOP_DOWNLOADS


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_arch(arch: str, force: bool = False, android: bool = False) -> Path | None:
    downloads = get_downloads(android)

    if arch not in downloads:
        print(f"  [ERROR] No {'android' if android else 'desktop'} source for arch: {arch}", file=sys.stderr)
        return None

    url, expected = downloads[arch]
    dest = BINARIES_DIR / f"proot-{arch}"

    if dest.exists() and not force:
        print(f"  [skip] {dest.name} already exists (use --force to re-download)")
        return dest

    source_label = "android" if android else "desktop"
    print(f"  [download] {arch} ({source_label}): {url}")
    tmp = dest.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(url, tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        print(f"  [ERROR] Failed to download {arch} ({source_label}): {exc}", file=sys.stderr)

        # If desktop failed, fall back to android source (or vice versa)
        if not android and arch in ANDROID_DOWNLOADS:
            print(f"  [retry] Trying android source for {arch}...")
            return download_arch(arch, force=force, android=True)

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


def check_binaries(android: bool = False):
    downloads = get_downloads(android)
    print(f"Checking bundled binaries ({'android' if android else 'desktop'}):")
    all_ok = True
    for arch in downloads:
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
    parser.add_argument("--android", action="store_true",
                        help="Use Android portable binaries (auto-detected if not set)")
    args = parser.parse_args()

    # Auto-detect Android environment
    use_android = args.android or is_android()
    downloads = get_downloads(use_android)

    if use_android and not args.android:
        print("[*] Android environment detected, using Android binaries")

    BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    if args.check:
        ok = check_binaries(use_android)
        sys.exit(0 if ok else 1)

    arches = args.arches or list(downloads.keys())
    invalid = [a for a in arches if a not in downloads]
    if invalid:
        print(f"Unknown architectures: {invalid}. Valid: {list(downloads.keys())}", file=sys.stderr)
        sys.exit(1)

    print(f"Downloading proot {PROOT_VERSION} binaries to {BINARIES_DIR}/")
    print(f"Source: {'Android (skirsten)' if use_android else 'Desktop (proot.gitlab.io)'}")
    print(f"Architectures: {arches}\n")

    success = []
    failed = []
    for arch in arches:
        result = download_arch(arch, force=args.force, android=use_android)
        (success if result else failed).append(arch)

    print(f"\nDone. {len(success)} succeeded, {len(failed)} failed.")
    if failed:
        print(f"Failed: {failed}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()