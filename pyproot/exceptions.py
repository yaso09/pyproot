"""Custom exceptions for pyproot."""


class ProotError(Exception):
    """Base exception for all pyproot errors."""


class ProotNotFoundError(ProotError):
    """Raised when no proot binary is available for the current platform."""


class ProotBinaryError(ProotError):
    """Raised when the proot binary cannot be executed (corrupt, wrong perms, etc.)."""


class ProotExecutionError(ProotError):
    """Raised when proot exits with a non-zero return code (and check=True)."""

    def __init__(self, message, returncode=None, stdout=None, stderr=None):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        base = super().__str__()
        if self.returncode is not None:
            base += f" (exit code {self.returncode})"
        if self.stderr:
            base += f"\nstderr: {self.stderr.strip()}"
        return base
