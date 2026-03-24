from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from netgent.client.ndt.client import NDT7Result


class NDT7Error(RuntimeError):
    """Base exception for ndt7 client failures."""


class NDT7BinaryNotFoundError(NDT7Error):
    """Raised when the ndt7 client binary cannot be found."""


class NDT7ProcessError(NDT7Error):
    """Raised when the ndt7 client exits with a non-zero status."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        result: "NDT7Result | None" = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.result = result
