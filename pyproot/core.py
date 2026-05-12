"""
Core PRoot class.

This module provides the PRoot class that wraps the proot binary
with a Pythonic builder-style API.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Sequence

from .binary import get_proot_binary
from .exceptions import ProotExecutionError

logger = logging.getLogger(__name__)


class PRoot:
    """
    Pythonic wrapper around the proot binary.

    PRoot lets unprivileged users run programs inside a different root
    filesystem (like chroot, but without root privileges).

    Builder-style API — methods return ``self`` so they can be chained:

    .. code-block:: python

        from pyproot import PRoot

        result = (
            PRoot(rootfs="/opt/alpine")
            .bind("/proc", "/proc")
            .bind("/sys",  "/sys")
            .bind("/dev",  "/dev")
            .env("TERM", "xterm-256color")
            .run(["/bin/sh", "-c", "cat /etc/os-release"])
        )
        print(result.stdout)

    Context-manager support:

    .. code-block:: python

        with PRoot(rootfs="/opt/alpine") as pr:
            pr.bind("/proc").bind("/sys")
            pr.run(["/bin/sh"])
    """

    def __init__(
        self,
        rootfs: str | Path | None = None,
        *,
        cwd: str | None = None,
        qemu: str | None = None,
        proot_binary: str | Path | None = None,
        mix_rootfs: bool = False,
        kill_on_exit: bool = False,
        link2symlink: bool = False,
        no_seccomp: bool = False,
        verbose: int = 0,
    ):
        """
        Initialise a PRoot session configuration.

        Args:
            rootfs: Guest root filesystem path (``-r`` / ``--rootfs``).
            cwd: Initial working directory inside the guest (``-w``).
            qemu: QEMU user-mode binary for foreign-arch emulation (``-q``).
                  Examples: ``"qemu-arm"``, ``"qemu-aarch64"``.
            proot_binary: Explicit path to the proot binary.
                          Defaults to auto-resolution via :func:`get_proot_binary`.
            mix_rootfs: Allow the host filesystem to be visible through
                        the guest rootfs (``--mixed-mode``).
            kill_on_exit: Kill all sub-processes when the main one exits (``-k``).
            link2symlink: Emulate hard-links with symlinks (``--link2symlink``).
            no_seccomp: Disable seccomp acceleration (``--no-seccomp``).
            verbose: Verbosity level passed to proot (``-v <n>``).
        """
        self.rootfs: Path | None = Path(rootfs) if rootfs else None
        self.cwd: str | None = cwd
        self.qemu: str | None = qemu
        self.mix_rootfs: bool = mix_rootfs
        self.kill_on_exit: bool = kill_on_exit
        self.link2symlink: bool = link2symlink
        self.no_seccomp: bool = no_seccomp
        self.verbose: int = verbose

        # Bind mounts: list of (host_path, guest_path) tuples.
        # guest_path may be None → same as host_path.
        self._binds: list[tuple[str, str | None]] = []

        # Extra environment variables to inject into the guest.
        self._env_vars: dict[str, str] = {}

        # Override the auto-resolved binary path.
        self._proot_binary: Path | None = Path(proot_binary) if proot_binary else None

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def rootfs_path(self, path: str | Path) -> "PRoot":
        """Set (or update) the guest root filesystem path."""
        self.rootfs = Path(path)
        return self

    def bind(self, host: str | Path, guest: str | Path | None = None) -> "PRoot":
        """
        Add a bind mount.

        Args:
            host:  Path on the host to bind.
            guest: Mount point inside the guest.
                   Defaults to the same path as *host*.

        Example:
            pr.bind("/proc").bind("/dev", "/dev").bind("/tmp/mydata", "/data")
        """
        self._binds.append((str(host), str(guest) if guest else None))
        return self

    def env(self, key: str, value: str) -> "PRoot":
        """Set an environment variable visible inside the guest."""
        self._env_vars[key] = value
        return self

    def workdir(self, path: str) -> "PRoot":
        """Set the working directory inside the guest."""
        self.cwd = path
        return self

    def use_qemu(self, binary: str) -> "PRoot":
        """Enable QEMU user-mode emulation."""
        self.qemu = binary
        return self

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def build_argv(self, command: Sequence[str] | str) -> list[str]:
        """
        Build the full argv list that will be passed to ``subprocess``.

        Useful for debugging or for integrating with other subprocess
        launchers (asyncio, etc.).

        Args:
            command: The command to execute inside the guest.

        Returns:
            Full argument list starting with the proot binary path.
        """
        binary = self._resolve_binary()
        argv: list[str] = [str(binary)]

        if self.verbose:
            argv += ["-v", str(self.verbose)]

        if self.rootfs:
            argv += ["-r", str(self.rootfs)]

        if self.cwd:
            argv += ["-w", self.cwd]

        if self.qemu:
            argv += ["-q", self.qemu]

        if self.mix_rootfs:
            argv.append("--mixed-mode")

        if self.kill_on_exit:
            argv.append("-k")

        if self.link2symlink:
            argv.append("--link2symlink")

        if self.no_seccomp:
            argv.append("--no-seccomp")

        for host, guest in self._binds:
            if guest:
                argv += ["-b", f"{host}:{guest}"]
            else:
                argv += ["-b", host]

        # Append the guest command
        if isinstance(command, str):
            argv += shlex.split(command)
        else:
            argv += list(command)

        return argv

    def run(
        self,
        command: Sequence[str] | str,
        *,
        env: dict | None = None,
        timeout: float | None = None,
        capture_output: bool = True,
        check: bool = False,
        stdin=None,
        text: bool = True,
        encoding: str = "utf-8",
        errors: str = "replace",
    ) -> subprocess.CompletedProcess:
        """
        Run *command* inside proot and return a ``CompletedProcess``.

        Args:
            command: Command (list or shell string) to run inside the guest.
            env: Extra environment variables merged into the current process
                 environment (on top of any set via :meth:`env`).
            timeout: Kill the process after this many seconds.
            capture_output: Capture stdout/stderr (default ``True``).
                            Set to ``False`` to inherit the terminal.
            check: Raise :exc:`ProotExecutionError` on non-zero exit code.
            stdin: Passed directly to ``subprocess.run``.
            text: Decode output as text (default ``True``).
            encoding: Text encoding (default ``"utf-8"``).
            errors: Encoding error handler (default ``"replace"``).

        Returns:
            :class:`subprocess.CompletedProcess`

        Raises:
            :exc:`ProotExecutionError`: If *check* is True and proot exits != 0.
        """
        argv = self.build_argv(command)

        # Merge environment variables
        process_env = os.environ.copy()
        process_env.update(self._env_vars)
        if env:
            process_env.update(env)

        logger.debug("proot argv: %s", argv)

        kwargs: dict = dict(
            env=process_env,
            timeout=timeout,
            stdin=stdin,
            text=text,
            encoding=encoding,
            errors=errors,
        )
        if capture_output:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.PIPE

        result = subprocess.run(argv, **kwargs)

        if check and result.returncode != 0:
            raise ProotExecutionError(
                f"proot command failed: {' '.join(shlex.quote(a) for a in argv)}",
                returncode=result.returncode,
                stdout=result.stdout if capture_output else None,
                stderr=result.stderr if capture_output else None,
            )

        return result

    def popen(
        self,
        command: Sequence[str] | str,
        *,
        env: dict | None = None,
        stdin=None,
        stdout=None,
        stderr=None,
        text: bool = True,
        encoding: str = "utf-8",
    ) -> subprocess.Popen:
        """
        Launch *command* inside proot and return a :class:`subprocess.Popen` object.

        Useful for interactive or streaming use-cases.

        Example:
            proc = pr.popen(["/bin/bash"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            stdout, _ = proc.communicate(b"echo hello\\n")
        """
        argv = self.build_argv(command)

        process_env = os.environ.copy()
        process_env.update(self._env_vars)
        if env:
            process_env.update(env)

        logger.debug("proot popen argv: %s", argv)

        return subprocess.Popen(
            argv,
            env=process_env,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            text=text,
            encoding=encoding,
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "PRoot":
        return self

    def __exit__(self, *args) -> None:
        pass  # Nothing to clean up for now; hook point for future resource mgmt.

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def version(self) -> str:
        """Return the proot binary version string."""
        result = self._run_proot(["--version"], capture_output=True, check=False)
        return (result.stdout or result.stderr or "").strip()

    def __repr__(self) -> str:
        parts = []
        if self.rootfs:
            parts.append(f"rootfs={self.rootfs!r}")
        if self.cwd:
            parts.append(f"cwd={self.cwd!r}")
        if self.qemu:
            parts.append(f"qemu={self.qemu!r}")
        if self._binds:
            parts.append(f"binds={self._binds!r}")
        return f"PRoot({', '.join(parts)})"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_binary(self) -> Path:
        if self._proot_binary:
            return self._proot_binary
        return get_proot_binary()

    def _run_proot(self, extra_args: list[str], **kwargs) -> subprocess.CompletedProcess:
        binary = self._resolve_binary()
        return subprocess.run([str(binary)] + extra_args, **kwargs)
