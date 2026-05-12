"""
Command-line interface for pyproot.

Usage:
    python -m pyproot [proot-options] -- <command> [args...]
    pyproot --info
    pyproot --version
    pyproot --download [arch ...]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .binary import download_proot, get_platform_info, get_proot_binary
from .core import PRoot
from .exceptions import ProotError


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pyproot",
        description="Run commands inside proot via the pyproot Python wrapper.",
        epilog=(
            "All unrecognised arguments after '--' are passed to proot as the guest command.\n\n"
            "Examples:\n"
            "  pyproot --info\n"
            "  pyproot --rootfs /opt/alpine -- /bin/sh -c 'uname -a'\n"
            "  pyproot --bind /proc --bind /dev --rootfs /opt/ubuntu -- /bin/bash\n"
            "  pyproot --download x86_64\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument("--version", action="store_true", help="Show pyproot version and exit.")
    p.add_argument("--info", action="store_true", help="Show platform/binary info as JSON.")
    p.add_argument(
        "--download",
        nargs="*",
        metavar="ARCH",
        help="Download proot binary to ~/.cache/pyproot/ (pass arch names or leave blank for current arch).",
    )

    # proot options
    p.add_argument("-r", "--rootfs", metavar="PATH", help="Guest root filesystem.")
    p.add_argument("-w", "--cwd", metavar="PATH", help="Initial working directory inside guest.")
    p.add_argument("-q", "--qemu", metavar="BINARY", help="QEMU binary for foreign-arch emulation.")
    p.add_argument(
        "-b", "--bind",
        metavar="HOST[:GUEST]",
        action="append",
        dest="binds",
        help="Bind mount (can be repeated).",
    )
    p.add_argument("--link2symlink", action="store_true", help="Emulate hard-links with symlinks.")
    p.add_argument("--no-seccomp", action="store_true", help="Disable seccomp acceleration.")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase proot verbosity.")

    p.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run inside proot (use '--' separator).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --version
    if args.version:
        print(f"pyproot {__version__}")
        return 0

    # --info
    if args.info:
        info = get_platform_info()
        info["pyproot_version"] = __version__
        try:
            binary = get_proot_binary()
            result = subprocess.run(
                [str(binary), "--version"],
                capture_output=True,
                text=True,
            )
            info["proot_version"] = (result.stdout or result.stderr).strip()
        except Exception as exc:
            info["proot_version"] = f"error: {exc}"
        print(json.dumps(info, indent=2))
        return 0

    # --download
    if args.download is not None:
        from scripts.download_binaries import DOWNLOADS, download_arch

        arches = args.download or [get_platform_info()["arch"]]
        for arch in arches:
            if arch not in DOWNLOADS:
                print(f"Unknown arch: {arch}. Valid: {list(DOWNLOADS)}", file=sys.stderr)
                return 1
            dest = download_arch(arch, force=True)
            if not dest:
                return 1
        return 0

    # Strip leading '--' separator if present
    command = args.command
    if command and command[0] == "--":
        command = command[1:]

    if not command:
        parser.print_help()
        return 1

    try:
        pr = PRoot(
            rootfs=args.rootfs,
            cwd=args.cwd,
            qemu=args.qemu,
            link2symlink=args.link2symlink,
            no_seccomp=args.no_seccomp,
            verbose=args.verbose,
        )

        for bind_spec in args.binds or []:
            if ":" in bind_spec:
                host, guest = bind_spec.split(":", 1)
                pr.bind(host, guest)
            else:
                pr.bind(bind_spec)

        result = pr.run(command, capture_output=False, check=False)
        return result.returncode

    except ProotError as exc:
        print(f"pyproot error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
