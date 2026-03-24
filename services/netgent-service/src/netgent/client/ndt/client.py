from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from netgent.client.ndt.exception import (
    NDT7BinaryNotFoundError,
    NDT7Error,
    NDT7ProcessError,
)

NDT7TestName = Literal["download", "upload"]


class NDT7Event(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    key: str = Field(validation_alias="Key")
    value: dict[str, Any] = Field(validation_alias="Value")

    @property
    def test(self) -> str | None:
        test = self.value.get("Test")
        return test if isinstance(test, str) else None


class NDT7Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: list[str]
    events: list[NDT7Event]
    summary: dict[str, Any] | None = None
    stdout: str
    stderr: str
    returncode: int

    def events_for(self, key: str, *, test: str | None = None) -> list[NDT7Event]:
        return [
            event
            for event in self.events
            if event.key == key and (test is None or event.test == test)
        ]

    @property
    def measurements(self) -> list[dict[str, Any]]:
        return [event.value for event in self.events_for("measurement")]

    @property
    def download_measurements(self) -> list[dict[str, Any]]:
        return [
            event.value for event in self.events_for("measurement", test="download")
        ]

    @property
    def upload_measurements(self) -> list[dict[str, Any]]:
        return [event.value for event in self.events_for("measurement", test="upload")]

    @property
    def errors(self) -> list[dict[str, Any]]:
        return [event.value for event in self.events_for("error")]

    @property
    def completed_tests(self) -> list[str]:
        tests: list[str] = []
        for event in self.events_for("complete"):
            if event.test is not None:
                tests.append(event.test)
        return tests


class NDT7Client(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binary: str = "ndt-client"
    default_timeout: str = "55s"
    extra_args: list[str] = Field(default_factory=list)

    def run(
        self,
        *,
        timeout: str | None = None,
        download: bool = True,
        upload: bool = True,
        server: str | None = None,
        service_url: str | None = None,
        scheme: Literal["ws", "wss"] | None = None,
        no_verify: bool = False,
        client_name: str | None = None,
    ) -> NDT7Result:
        command = self._build_command(
            timeout=timeout or self.default_timeout,
            download=download,
            upload=upload,
            server=server,
            service_url=service_url,
            scheme=scheme,
            no_verify=no_verify,
            client_name=client_name,
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
            raise NDT7ProcessError(
                "ndt7 client exited with a non-zero status",
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                result=result,
            )

        return result

    def run_download(self, **kwargs: Any) -> NDT7Result:
        return self.run(download=True, upload=False, **kwargs)

    def run_upload(self, **kwargs: Any) -> NDT7Result:
        return self.run(download=False, upload=True, **kwargs)

    def _require_binary(self) -> None:
        if shutil.which(self.binary) is None:
            raise NDT7BinaryNotFoundError(
                f"Unable to find ndt7 client binary '{self.binary}' on PATH"
            )

    def _build_command(
        self,
        *,
        timeout: str,
        download: bool,
        upload: bool,
        server: str | None,
        service_url: str | None,
        scheme: Literal["ws", "wss"] | None,
        no_verify: bool,
        client_name: str | None,
    ) -> list[str]:
        command = [self.binary, "-format", "json", "-timeout", timeout]

        if not download:
            command.extend(["-download=false"])
        if not upload:
            command.extend(["-upload=false"])
        if server:
            command.extend(["-server", server])
        if service_url:
            command.extend(["-service-url", service_url])
        if scheme:
            command.extend(["-scheme", scheme])
        if no_verify:
            command.append("-no-verify")
        if client_name:
            command.extend(["-client-name", client_name])

        command.extend(self.extra_args)
        return command

    def _parse_result(
        self,
        *,
        command: list[str],
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> NDT7Result:
        events: list[NDT7Event] = []
        summary: dict[str, Any] | None = None
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
                if (
                    isinstance(payload, dict)
                    and "Key" in payload
                    and "Value" in payload
                ):
                    events.append(NDT7Event.model_validate(payload))
                    continue
                if isinstance(payload, dict):
                    summary = payload
                    continue
            except (json.JSONDecodeError, ValidationError) as exc:
                raise NDT7Error(f"Unexpected ndt7 event payload: {line}") from exc

        return NDT7Result(
            command=command,
            events=events,
            summary=summary,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
        )
