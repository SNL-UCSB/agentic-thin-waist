from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import SpeedtestResult


class SpeedtestError(RuntimeError):
    """Base exception for speedtest client failures."""


class SpeedtestBinaryNotFoundError(SpeedtestError):
    """Raised when the speedtest-cli binary cannot be found."""


class SpeedtestProcessError(SpeedtestError):
    """Raised when speedtest-cli exits with a non-zero status."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        result: "SpeedtestResult | None" = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.result = result
