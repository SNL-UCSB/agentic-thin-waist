from __future__ import annotations

import json
import subprocess
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..execution import build_execution_command, require_execution_binary
from .exception import (
    IPerf3BinaryNotFoundError,
    IPerf3Error,
    IPerf3ProcessError,
)


class IPerf3Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: list[str]
    data: dict[str, Any]
    stdout: str
    stderr: str
    returncode: int

    @property
    def error(self) -> str | None:
        error = self.data.get("error")
        return error if isinstance(error, str) else None

    @property
    def protocol(self) -> str | None:
        protocol = self.data.get("start", {}).get("test_start", {}).get("protocol")
        return protocol if isinstance(protocol, str) else None

    @property
    def end(self) -> dict[str, Any]:
        end = self.data.get("end")
        return end if isinstance(end, dict) else {}

    @property
    def intervals(self) -> list[dict[str, Any]]:
        intervals = self.data.get("intervals")
        if not isinstance(intervals, list):
            return []
        return [interval for interval in intervals if isinstance(interval, dict)]

    @property
    def sent_summary(self) -> dict[str, Any]:
        summary = self.end.get("sum_sent")
        return summary if isinstance(summary, dict) else {}

    @property
    def received_summary(self) -> dict[str, Any]:
        summary = self.end.get("sum_received")
        return summary if isinstance(summary, dict) else {}

    @property
    def summary(self) -> dict[str, Any]:
        fallback = self.end.get("sum", {})
        if not isinstance(fallback, dict):
            fallback = {}
        return self.received_summary or self.sent_summary or fallback

    @property
    def bits_per_second(self) -> float | None:
        value = self.summary.get("bits_per_second")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @property
    def jitter_ms(self) -> float | None:
        value = self.summary.get("jitter_ms")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @property
    def packet_loss_percent(self) -> float | None:
        value = self.summary.get("lost_percent")
        if isinstance(value, (int, float)):
            return float(value)
        return None


class IPerf3Client(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binary: str = "iperf3"
    default_port: int = 5201
    default_duration: int = 10
    extra_args: list[str] = Field(default_factory=list)

    def run(
        self,
        host: str,
        *,
        port: int | None = None,
        duration_seconds: int | None = None,
        interval_seconds: int | None = None,
        omit_seconds: int | None = None,
        udp: bool = False,
        reverse: bool = False,
        bitrate: str | None = None,
        parallel: int | None = None,
    ) -> IPerf3Result:
        command = self._build_command(
            host=host,
            port=self.default_port if port is None else port,
            duration_seconds=(
                self.default_duration if duration_seconds is None else duration_seconds
            ),
            interval_seconds=interval_seconds,
            omit_seconds=omit_seconds,
            udp=udp,
            reverse=reverse,
            bitrate=bitrate,
            parallel=parallel,
        )

        self._require_binary()

        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
        )
        result = self._parse_result(
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )

        if completed.returncode != 0 or result.error is not None:
            raise IPerf3ProcessError(
                "iperf3 exited with a non-zero status",
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                result=result,
            )

        return result

    def _require_binary(self) -> None:
        try:
            require_execution_binary(self.binary)
        except FileNotFoundError as exc:
            raise IPerf3BinaryNotFoundError(str(exc)) from exc
        except RuntimeError as exc:
            raise IPerf3Error(str(exc)) from exc

    def _build_command(
        self,
        *,
        host: str,
        port: int,
        duration_seconds: int,
        interval_seconds: int | None,
        omit_seconds: int | None,
        udp: bool,
        reverse: bool,
        bitrate: str | None,
        parallel: int | None,
    ) -> list[str]:
        args = [
            "-J",
            "-c",
            host,
            "-p",
            str(port),
            "-t",
            str(duration_seconds),
        ]

        if interval_seconds is not None:
            args.extend(["-i", str(interval_seconds)])
        if omit_seconds is not None:
            args.extend(["-O", str(omit_seconds)])
        if udp:
            args.append("-u")
        if reverse:
            args.append("-R")
        if bitrate:
            args.extend(["-b", bitrate])
        if parallel is not None:
            args.extend(["-P", str(parallel)])

        args.extend(self.extra_args)
        return build_execution_command(binary=self.binary, args=args)

    def _parse_result(
        self,
        *,
        command: list[str],
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> IPerf3Result:
        try:
            data = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError as exc:
            raise IPerf3Error("Unexpected iperf3 JSON output") from exc

        if not isinstance(data, dict):
            raise IPerf3Error("Unexpected iperf3 JSON output")

        return IPerf3Result(
            command=command,
            data=data,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
        )
