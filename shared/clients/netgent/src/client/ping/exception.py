from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import PingResult


class PingError(RuntimeError):
    """Base exception for ping client failures."""


class PingBinaryNotFoundError(PingError):
    """Raised when the ping binary cannot be found."""


class PingProcessError(PingError):
    """Raised when ping exits with a non-zero status."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        result: "PingResult | None" = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.result = result
