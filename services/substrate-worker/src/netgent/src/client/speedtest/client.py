from __future__ import annotations

import json
import subprocess
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..execution import build_execution_command, require_execution_binary
from .exception import (
    SpeedtestBinaryNotFoundError,
    SpeedtestError,
    SpeedtestProcessError,
)


class SpeedtestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: list[str]
    data: dict[str, Any]
    stdout: str
    stderr: str
    returncode: int

    @property
    def ping_ms(self) -> float | None:
        value = self.data.get("ping")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @property
    def download_bits_per_second(self) -> float | None:
        value = self.data.get("download")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @property
    def upload_bits_per_second(self) -> float | None:
        value = self.data.get("upload")
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @property
    def server(self) -> dict[str, Any]:
        server = self.data.get("server")
        return server if isinstance(server, dict) else {}

    @property
    def client(self) -> dict[str, Any]:
        client = self.data.get("client")
        return client if isinstance(client, dict) else {}

    @property
    def share_url(self) -> str | None:
        value = self.data.get("share")
        return value if isinstance(value, str) else None


class SpeedtestClient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binary: str = "speedtest-cli"
    extra_args: list[str] = Field(default_factory=list)

    def run(
        self,
        *,
        secure: bool = False,
        server_id: int | None = None,
        source: str | None = None,
        timeout_seconds: int | None = None,
        share: bool = False,
        bytes_units: bool = False,
    ) -> SpeedtestResult:
        command = self._build_command(
            secure=secure,
            server_id=server_id,
            source=source,
            timeout_seconds=timeout_seconds,
            share=share,
            bytes_units=bytes_units,
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
            raise SpeedtestProcessError(
                "speedtest-cli exited with a non-zero status",
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
            raise SpeedtestBinaryNotFoundError(str(exc)) from exc
        except RuntimeError as exc:
            raise SpeedtestError(str(exc)) from exc

    def _build_command(
        self,
        *,
        secure: bool,
        server_id: int | None,
        source: str | None,
        timeout_seconds: int | None,
        share: bool,
        bytes_units: bool,
    ) -> list[str]:
        args = ["--json"]
        if secure:
            args.append("--secure")
        if server_id is not None:
            args.extend(["--server", str(server_id)])
        if source:
            args.extend(["--source", source])
        if timeout_seconds is not None:
            args.extend(["--timeout", str(timeout_seconds)])
        if share:
            args.append("--share")
        if bytes_units:
            args.append("--bytes")

        args.extend(self.extra_args)
        return build_execution_command(binary=self.binary, args=args)

    def _parse_result(
        self,
        *,
        command: list[str],
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> SpeedtestResult:
        try:
            data = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError as exc:
            raise SpeedtestError("Unexpected speedtest-cli JSON output") from exc

        if not isinstance(data, dict):
            raise SpeedtestError("Unexpected speedtest-cli JSON output")

        return SpeedtestResult(
            command=command,
            data=data,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
        )
