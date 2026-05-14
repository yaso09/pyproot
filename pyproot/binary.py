"""
Binary management for pyproot.

Resolution order for the proot binary:
  1. User-specified path via PYPROOT_BINARY env var
  2. Bundled binary inside the package  (pyproot/binaries/proot-<arch>)
  3. System-installed proot (found via PATH)
  4. Auto-downloaded binary cached in ~/.cache/pyproot/
"""

import hashlib
import logging
import os
import platform
import shutil
import stat
import urllib.request
from pathlib import Path

from .exceptions import ProotBinaryError, ProotNotFoundError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Architecture mapping
# ---------------------------------------------------------------------------

_ARCH_MAP = {
    "x86_64": "x86_64",
    "amd64":  "x86_64",
    "aarch64": "aarch64",
    "arm64":  "aarch64",
    "armv7l": "armv7l",
    "armv6l": "armv6l",
    "i386":   "i386",
    "i686":   "i386",
    "x86":    "x86",
}

# Desktop/Linux — proot.gitlab.io
_DESKTOP_URLS: dict[tuple[str, str], tuple[str, str | None]] = {
    ("linux", "x86_64"): (
        "https://proot.gitlab.io/proot/bin/proot",
        None,
    ),
    ("linux", "aarch64"): (
        "https://proot.gitlab.io/proot/bin/proot-arm64",
        None,
    ),
    ("linux", "armv7l"): (
        "https://proot.gitlab.io/proot/bin/proot-arm",
        None,
    ),
}

# Android/Mobile — skirsten (Termux-based)
_ANDROID_URLS: dict[tuple[str, str], tuple[str, str | None]] = {
    ("linux", "x86_64"): (
        "https://skirsten.github.io/proot-portable-android-binaries/x86_64/proot",
        None,
    ),
    ("linux", "x86"): (
        "https://skirsten.github.io/proot-portable-android-binaries/x86/proot",
        None,
    ),
    ("linux", "aarch64"): (
        "https://skirsten.github.io/proot-portable-android-binaries/aarch64/proot",
        None,
    ),
    ("linux", "armv7l"): (
        "https://skirsten.github.io/proot-portable-android-binaries/armv7/proot",
        None,
    ),
}

_BUNDLED_DIR = Path(__file__).parent / "binaries"
_CACHE_DIR = Path.home() / ".cache" / "pyproot"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_android() -> bool:
    """Detect whether we are running on an Android device."""
    return (
        os.path.exists("/system/build.prop")
        or "ANDROID_ROOT" in os.environ
        or "ANDROID_DATA" in os.environ
    )


def get_proot_binary(prefer_system: bool = False) -> Path:
    """
    Return the path to a usable proot binary.

    Resolution order:
      1. ``PYPROOT_BINARY`` environment variable
      2. Bundled binary (shipped with the package)
      3. System PATH  (if ``prefer_system=True`` this becomes step 2)
      4. Cached downloaded binary
      5. Auto-download

    Args:
        prefer_system: If True, check PATH before the bundled binary.

    Returns:
        Path to the proot binary.

    Raises:
        ProotNotFoundError: When no binary can be located or downloaded.
        ProotBinaryError:   When a located binary is not executable.
    """
    # 1. Explicit env override
    env_path = os.environ.get("PYPROOT_BINARY")
    if env_path:
        p = Path(env_path)
        _assert_executable(p)
        return p

    resolvers = (
        [_bundled_binary, _system_binary]
        if not prefer_system
        else [_system_binary, _bundled_binary]
    )

    for resolver in resolvers:
        try:
            p = resolver()
            if p:
                return p
        except ProotBinaryError:
            raise
        except Exception:
            pass

    # 4. Cached download
    try:
        p = _cached_binary()
        if p:
            return p
    except Exception:
        pass

    # 5. Auto-download
    return download_proot()


def download_proot(
    dest_dir: Path | None = None,
    force: bool = False,
    android: bool | None = None,
) -> Path:
    """
    Download the proot binary for the current platform and cache it.

    Args:
        dest_dir: Directory to save the binary (default: ``~/.cache/pyproot``).
        force:    Re-download even if a cached copy exists.
        android:  Force Android binary selection. Auto-detected if None.

    Returns:
        Path to the downloaded binary.

    Raises:
        ProotNotFoundError: When no download URL is known for this platform.
        ProotBinaryError:   When the download fails or the file is not executable.
    """
    os_name, arch = _current_platform()
    key = (os_name, arch)

    use_android = is_android() if android is None else android

    # Pick URL — fall back to the other source if arch not found
    url, expected_sha256 = _resolve_url(key, use_android)

    dest_dir = Path(dest_dir) if dest_dir else _CACHE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / f"proot-{arch}"

    if dest.exists() and not force:
        logger.debug("Using cached proot binary at %s", dest)
        _assert_executable(dest)
        return dest

    logger.info("Downloading proot from %s ...", url)
    try:
        tmp = dest.with_suffix(".tmp")
        urllib.request.urlretrieve(url, tmp)

        if expected_sha256:
            actual = _sha256(tmp)
            if actual != expected_sha256:
                tmp.unlink(missing_ok=True)
                raise ProotBinaryError(
                    f"SHA-256 mismatch for downloaded proot binary.\n"
                    f"  expected: {expected_sha256}\n"
                    f"  actual:   {actual}"
                )

        tmp.rename(dest)
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        logger.info("proot saved to %s", dest)
        return dest

    except ProotBinaryError:
        raise
    except Exception as exc:
        raise ProotBinaryError(f"Failed to download proot: {exc}") from exc


def get_platform_info() -> dict:
    """Return a dict describing the current platform (for diagnostics)."""
    os_name, arch = _current_platform()
    android = is_android()
    return {
        "os": os_name,
        "arch": arch,
        "machine": platform.machine(),
        "system": platform.system(),
        "android": android,
        "source": "android (skirsten)" if android else "desktop (proot.gitlab.io)",
        "bundled_binary": str(_bundled_binary() or "not found"),
        "system_binary": str(_system_binary() or "not found"),
        "cached_binary": str(_cached_binary() or "not found"),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _current_platform() -> tuple[str, str]:
    os_name = platform.system().lower()
    raw_arch = platform.machine().lower()
    arch = _ARCH_MAP.get(raw_arch, raw_arch)
    return os_name, arch


def _resolve_url(
    key: tuple[str, str],
    android: bool,
) -> tuple[str, str | None]:
    """
    Resolve download URL for the given (os, arch) key.
    Tries the preferred source first, falls back to the other.
    """
    primary = _ANDROID_URLS if android else _DESKTOP_URLS
    fallback = _DESKTOP_URLS if android else _ANDROID_URLS

    if key in primary:
        return primary[key]

    if key in fallback:
        logger.warning(
            "No %s URL for %s/%s, falling back to %s source.",
            "android" if android else "desktop",
            *key,
            "desktop" if android else "android",
        )
        return fallback[key]

    raise ProotNotFoundError(
        f"No proot download URL registered for platform {key[0]}/{key[1]}. "
        "Set PYPROOT_BINARY to the path of a proot binary, "
        "or open an issue at https://github.com/yourname/pyproot."
    )


def _bundled_binary() -> Path | None:
    _, arch = _current_platform()
    candidate = _BUNDLED_DIR / f"proot-{arch}"
    if candidate.exists():
        _assert_executable(candidate)
        return candidate
    return None


def _system_binary() -> Path | None:
    p = shutil.which("proot")
    if p:
        return Path(p)
    return None


def _cached_binary() -> Path | None:
    _, arch = _current_platform()
    candidate = _CACHE_DIR / f"proot-{arch}"
    if candidate.exists():
        _assert_executable(candidate)
        return candidate
    return None


def _assert_executable(path: Path) -> None:
    if not path.exists():
        raise ProotBinaryError(f"proot binary not found at {path}")
    if not os.access(path, os.X_OK):
        try:
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        except OSError:
            raise ProotBinaryError(
                f"proot binary at {path} is not executable and permissions could not be fixed."
            )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()