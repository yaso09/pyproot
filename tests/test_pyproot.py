"""
Tests for pyproot.

Most tests are unit-tests that do NOT require proot to actually be installed.
Tests that require a real proot binary are marked with @pytest.mark.integration
and are skipped by default.

Run only unit tests:
    pytest tests/

Run all tests (requires proot):
    pytest tests/ -m "integration"
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure the source tree is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyproot import PRoot, ProotExecutionError
from pyproot.core import PRoot
from pyproot.exceptions import ProotBinaryError, ProotNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_PROOT = Path(__file__).parent / "fixtures" / "fake_proot.sh"


def _has_proot() -> bool:
    import shutil
    return shutil.which("proot") is not None


# ---------------------------------------------------------------------------
# Unit tests — argv construction
# ---------------------------------------------------------------------------


class TestBuildArgv:
    """Test that PRoot.build_argv produces the correct command line."""

    def _pr(self, **kwargs) -> PRoot:
        """Create a PRoot instance with a fake binary to avoid auto-resolution."""
        pr = PRoot(**kwargs)
        pr._proot_binary = Path("/usr/bin/proot")  # patched; won't be executed
        return pr

    def test_minimal(self):
        pr = self._pr()
        argv = pr.build_argv(["/bin/sh"])
        assert argv == ["/usr/bin/proot", "/bin/sh"]

    def test_rootfs(self):
        pr = self._pr(rootfs="/opt/alpine")
        argv = pr.build_argv(["/bin/sh"])
        assert "-r" in argv
        assert "/opt/alpine" in argv

    def test_cwd(self):
        pr = self._pr(cwd="/home/user")
        argv = pr.build_argv(["/bin/sh"])
        assert "-w" in argv
        assert "/home/user" in argv

    def test_qemu(self):
        pr = self._pr(qemu="qemu-arm")
        argv = pr.build_argv(["/bin/bash"])
        assert "-q" in argv
        assert "qemu-arm" in argv

    def test_bind_no_guest(self):
        pr = self._pr()
        pr.bind("/proc")
        argv = pr.build_argv(["/bin/sh"])
        assert "-b" in argv
        idx = argv.index("-b")
        assert argv[idx + 1] == "/proc"

    def test_bind_with_guest(self):
        pr = self._pr()
        pr.bind("/tmp/mydata", "/data")
        argv = pr.build_argv(["/bin/sh"])
        assert "-b" in argv
        idx = argv.index("-b")
        assert argv[idx + 1] == "/tmp/mydata:/data"

    def test_multiple_binds(self):
        pr = self._pr()
        pr.bind("/proc").bind("/sys").bind("/dev")
        argv = pr.build_argv(["/bin/sh"])
        assert argv.count("-b") == 3

    def test_verbose(self):
        pr = self._pr(verbose=2)
        argv = pr.build_argv(["/bin/sh"])
        assert "-v" in argv
        assert "2" in argv

    def test_flags(self):
        pr = self._pr(link2symlink=True, no_seccomp=True, kill_on_exit=True)
        argv = pr.build_argv(["/bin/sh"])
        assert "--link2symlink" in argv
        assert "--no-seccomp" in argv
        assert "-k" in argv

    def test_string_command(self):
        pr = self._pr()
        argv = pr.build_argv("/bin/sh -c 'echo hello'")
        assert "/bin/sh" in argv
        assert "-c" in argv
        assert "echo hello" in argv

    def test_builder_chain(self):
        pr = PRoot()
        pr._proot_binary = Path("/usr/bin/proot")
        returned = pr.bind("/proc").env("TERM", "xterm").workdir("/root")
        assert returned is pr  # methods return self


# ---------------------------------------------------------------------------
# Unit tests — exceptions
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_execution_error_str(self):
        exc = ProotExecutionError("fail", returncode=1, stderr="no such file")
        assert "exit code 1" in str(exc)
        assert "no such file" in str(exc)

    def test_not_found_is_proot_error(self):
        from pyproot.exceptions import ProotError
        assert issubclass(ProotNotFoundError, ProotError)
        assert issubclass(ProotBinaryError, ProotError)
        assert issubclass(ProotExecutionError, ProotError)


# ---------------------------------------------------------------------------
# Unit tests — binary resolution
# ---------------------------------------------------------------------------


class TestBinaryResolution:
    def test_env_var_override(self, tmp_path, monkeypatch):
        fake = tmp_path / "proot"
        fake.write_bytes(b"#!/bin/sh\necho fake\n")
        fake.chmod(0o755)
        monkeypatch.setenv("PYPROOT_BINARY", str(fake))

        from pyproot.binary import get_proot_binary
        resolved = get_proot_binary()
        assert resolved == fake

    def test_env_var_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PYPROOT_BINARY", str(tmp_path / "nonexistent"))
        from pyproot.binary import get_proot_binary
        with pytest.raises(ProotBinaryError):
            get_proot_binary()


# ---------------------------------------------------------------------------
# Integration tests — require proot
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(not _has_proot(), reason="proot not installed")
class TestIntegration:
    def test_echo(self):
        pr = PRoot()
        result = pr.run(["/bin/sh", "-c", "echo hello"])
        assert "hello" in result.stdout

    def test_rootfs_uname(self):
        pr = PRoot()
        result = pr.run(["/bin/sh", "-c", "uname -s"])
        assert result.returncode == 0

    def test_check_raises_on_failure(self):
        pr = PRoot()
        with pytest.raises(ProotExecutionError):
            pr.run(["/bin/sh", "-c", "exit 42"], check=True)

    def test_context_manager(self):
        with PRoot() as pr:
            result = pr.run(["/bin/sh", "-c", "echo ctx"])
        assert "ctx" in result.stdout

    def test_env_injection(self):
        pr = PRoot()
        pr.env("MY_VAR", "hello_pyproot")
        result = pr.run(["/bin/sh", "-c", "echo $MY_VAR"])
        assert "hello_pyproot" in result.stdout

    def test_popen(self):
        pr = PRoot()
        proc = pr.popen(
            ["/bin/sh", "-c", "echo popen_test"],
            stdout=subprocess.PIPE,
        )
        stdout, _ = proc.communicate()
        assert "popen_test" in stdout
