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

    def __str__(self) -> str:
        parts = [super().__str__(), f"returncode={self.returncode}"]
        cmd = " ".join(self.command)
        if cmd:
            parts.append(f"cmd={cmd}")
        # Long tails: 100-ping runs produce large stdout; keep enough for stats line.
        _tail = 6000
        err = (self.stderr or "").strip()
        if err:
            parts.append(f"stderr={err[-_tail:]}")
        out = (self.stdout or "").strip()
        if out:
            parts.append(f"stdout_tail={out[-_tail:]}")
        return " | ".join(parts)
