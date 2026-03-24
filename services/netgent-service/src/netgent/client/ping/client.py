from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from netgent.client.ping.exception import (
    PingBinaryNotFoundError,
    PingError,
    PingProcessError,
)

PING_HEADER_RE = re.compile(r"^PING\s+(?P<host>\S+)\s+\((?P<ip>[^)]+)\)")
PING_REPLY_RE = re.compile(
    r"^(?P<bytes>\d+)\s+bytes from\s+(?P<source>[^:]+):\s+"
    r"icmp_seq=(?P<icmp_seq>\d+)(?:\s+ttl=(?P<ttl>\d+))?\s+time[=<](?P<time_ms>[\d.]+)\s+ms$"
)
PING_STATS_RE = re.compile(
    r"^(?P<transmitted>\d+)\s+packets transmitted,\s+"
    r"(?P<received>\d+)\s+(?:packets\s+)?received,.*?"
    r"(?P<packet_loss_percent>[\d.]+)%\s+packet loss"
    r"(?:,\s+time\s+(?P<total_time_ms>\d+)ms)?$"
)
PING_RTT_RE = re.compile(
    r"^(?:rtt|round-trip)\s+min/avg/max/(?:mdev|stddev)\s+=\s+"
    r"(?P<min_ms>[\d.]+)/(?P<avg_ms>[\d.]+)/(?P<max_ms>[\d.]+)/(?P<jitter_ms>[\d.]+)\s+ms$"
)


class PingReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bytes: int
    source: str
    icmp_seq: int
    ttl: int | None = None
    time_ms: float
    raw: str


class PingStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transmitted: int
    received: int
    packet_loss_percent: float
    total_time_ms: int | None = None
    min_ms: float | None = None
    avg_ms: float | None = None
    max_ms: float | None = None
    jitter_ms: float | None = None


class PingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: list[str]
    stdout: str
    stderr: str
    returncode: int
    host: str | None = None
    resolved_ip: str | None = None
    replies: list[PingReply] = Field(default_factory=list)
    statistics: PingStatistics | None = None

    @property
    def packet_loss_percent(self) -> float | None:
        if self.statistics is None:
            return None
        return self.statistics.packet_loss_percent

    @property
    def avg_latency_ms(self) -> float | None:
        if self.statistics is None:
            return None
        return self.statistics.avg_ms

    @property
    def jitter_ms(self) -> float | None:
        if self.statistics is None:
            return None
        return self.statistics.jitter_ms


class PingClient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binary: str = "ping"
    default_count: int = 4
    extra_args: list[str] = Field(default_factory=list)

    def run(
        self,
        host: str,
        *,
        count: int | None = None,
        interval_seconds: float | None = None,
        timeout_seconds: int | None = None,
        packet_size: int | None = None,
    ) -> PingResult:
        command = self._build_command(
            host=host,
            count=self.default_count if count is None else count,
            interval_seconds=interval_seconds,
            timeout_seconds=timeout_seconds,
            packet_size=packet_size,
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

        if completed.returncode != 0:
            raise PingProcessError(
                "ping exited with a non-zero status",
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                result=result,
            )

        return result

    def _require_binary(self) -> None:
        if shutil.which(self.binary) is None:
            raise PingBinaryNotFoundError(
                f"Unable to find ping binary '{self.binary}' on PATH"
            )

    def _build_command(
        self,
        *,
        host: str,
        count: int,
        interval_seconds: float | None,
        timeout_seconds: int | None,
        packet_size: int | None,
    ) -> list[str]:
        command = [self.binary, "-c", str(count)]
        if interval_seconds is not None:
            command.extend(["-i", str(interval_seconds)])
        if timeout_seconds is not None:
            command.extend(["-W", str(timeout_seconds)])
        if packet_size is not None:
            command.extend(["-s", str(packet_size)])
        command.extend(self.extra_args)
        command.append(host)
        return command

    def _parse_result(
        self,
        *,
        command: list[str],
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> PingResult:
        host: str | None = None
        resolved_ip: str | None = None
        replies: list[PingReply] = []
        stats_data: dict[str, Any] | None = None

        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            header_match = PING_HEADER_RE.match(line)
            if header_match:
                host = header_match.group("host")
                resolved_ip = header_match.group("ip")
                continue

            reply_match = PING_REPLY_RE.match(line)
            if reply_match:
                ttl = reply_match.group("ttl")
                replies.append(
                    PingReply(
                        bytes=int(reply_match.group("bytes")),
                        source=reply_match.group("source"),
                        icmp_seq=int(reply_match.group("icmp_seq")),
                        ttl=int(ttl) if ttl is not None else None,
                        time_ms=float(reply_match.group("time_ms")),
                        raw=line,
                    )
                )
                continue

            stats_match = PING_STATS_RE.match(line)
            if stats_match:
                stats_data = {
                    "transmitted": int(stats_match.group("transmitted")),
                    "received": int(stats_match.group("received")),
                    "packet_loss_percent": float(
                        stats_match.group("packet_loss_percent")
                    ),
                    "total_time_ms": (
                        int(stats_match.group("total_time_ms"))
                        if stats_match.group("total_time_ms") is not None
                        else None
                    ),
                }
                continue

            rtt_match = PING_RTT_RE.match(line)
            if rtt_match:
                if stats_data is None:
                    stats_data = {
                        "transmitted": 0,
                        "received": 0,
                        "packet_loss_percent": 0.0,
                    }
                stats_data.update(
                    {
                        "min_ms": float(rtt_match.group("min_ms")),
                        "avg_ms": float(rtt_match.group("avg_ms")),
                        "max_ms": float(rtt_match.group("max_ms")),
                        "jitter_ms": float(rtt_match.group("jitter_ms")),
                    }
                )

        return PingResult(
            command=command,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            host=host,
            resolved_ip=resolved_ip,
            replies=replies,
            statistics=(
                PingStatistics.model_validate(stats_data)
                if stats_data is not None
                else None
            ),
        )
