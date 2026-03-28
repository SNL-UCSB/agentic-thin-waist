from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import IPerf3Result


class IPerf3Error(RuntimeError):
    """Base exception for iperf3 client failures."""


class IPerf3BinaryNotFoundError(IPerf3Error):
    """Raised when the iperf3 binary cannot be found."""


class IPerf3ProcessError(IPerf3Error):
    """Raised when iperf3 exits with a non-zero status or reports an error."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        result: "IPerf3Result | None" = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.result = result
