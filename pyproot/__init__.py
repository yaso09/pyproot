"""
pyproot - Python wrapper for proot with bundled binaries.

PRoot is a user-space implementation of chroot, mount --bind, and binfmt_misc.
This library bundles proot binaries and exposes a clean Python API.

Basic usage:
    from pyproot import PRoot

    pr = PRoot(rootfs="/path/to/rootfs")
    result = pr.run(["/bin/sh", "-c", "echo hello"])
    print(result.stdout)

    # Context manager
    with PRoot(rootfs="/path/to/rootfs") as pr:
        pr.bind("/proc", "/proc")
        pr.bind("/sys", "/sys")
        result = pr.run(["/bin/bash"])
"""

from .core import PRoot
from .binary import get_proot_binary, download_proot
from .exceptions import (
    ProotError,
    ProotNotFoundError,
    ProotBinaryError,
    ProotExecutionError,
)

__version__ = "0.1.0"
__author__ = "Ben"
__all__ = [
    "PRoot",
    "get_proot_binary",
    "download_proot",
    "ProotError",
    "ProotNotFoundError",
    "ProotBinaryError",
    "ProotExecutionError",
]


def run(
    command,
    rootfs=None,
    binds=None,
    cwd=None,
    env=None,
    qemu=None,
    timeout=None,
    capture_output=True,
):
    """
    Convenience function: run a command inside proot in one call.

    Args:
        command (list[str] | str): Command to execute.
        rootfs (str | Path, optional): Guest root filesystem path.
        binds (list[str], optional): Bind mounts in "host:guest" or "host" format.
        cwd (str, optional): Working directory inside the guest.
        env (dict, optional): Environment variables for the command.
        qemu (str, optional): QEMU binary for foreign-arch emulation (e.g. "qemu-arm").
        timeout (float, optional): Seconds before the process is killed.
        capture_output (bool): Capture stdout/stderr (default True).

    Returns:
        subprocess.CompletedProcess

    Example:
        import pyproot
        result = pyproot.run(
            ["/bin/sh", "-c", "uname -a"],
            rootfs="/path/to/alpine",
            binds=["/proc", "/sys", "/dev"],
        )
        print(result.stdout)
    """
    pr = PRoot(rootfs=rootfs, cwd=cwd, qemu=qemu)
    if binds:
        for b in binds:
            if ":" in b:
                host, guest = b.split(":", 1)
                pr.bind(host, guest)
            else:
                pr.bind(b)
    return pr.run(command, env=env, timeout=timeout, capture_output=capture_output)
