from __future__ import annotations

import json
import subprocess

import pytest
from netgent.src.client.iperf import (
    IPerf3BinaryNotFoundError,
    IPerf3Client,
    IPerf3ProcessError,
)
from pydantic import BaseModel


def test_iperf3_client_builds_expected_command(mocker):
    mocker.patch("client.iperf.client.require_execution_binary")
    mock_run = mocker.patch(
        "client.iperf.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="{}",
            stderr="",
        ),
    )

    client = IPerf3Client(extra_args=["--forceflush"])
    result = client.run(
        "iperf.example.net",
        port=5202,
        duration_seconds=15,
        interval_seconds=1,
        omit_seconds=2,
        udp=True,
        reverse=True,
        bitrate="20M",
        parallel=4,
    )

    mock_run.assert_called_once_with(
        [
            "iperf3",
            "-J",
            "-c",
            "iperf.example.net",
            "-p",
            "5202",
            "-t",
            "15",
            "-i",
            "1",
            "-O",
            "2",
            "-u",
            "-R",
            "-b",
            "20M",
            "-P",
            "4",
            "--forceflush",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert isinstance(client, BaseModel)
    assert isinstance(result, BaseModel)


def test_iperf3_client_parses_json_output(mocker):
    mocker.patch("client.iperf.client.require_execution_binary")
    mocker.patch(
        "client.iperf.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "start": {"test_start": {"protocol": "UDP"}},
                    "intervals": [{"sum": {"bits_per_second": 1000000}}],
                    "end": {
                        "sum": {
                            "bits_per_second": 8200000,
                            "jitter_ms": 0.321,
                            "lost_percent": 0.0,
                        }
                    },
                }
            ),
            stderr="",
        ),
    )

    result = IPerf3Client().run("iperf.example.net", udp=True)

    assert result.protocol == "UDP"
    assert result.bits_per_second == 8200000.0
    assert result.jitter_ms == 0.321
    assert result.packet_loss_percent == 0.0
    assert len(result.intervals) == 1


def test_iperf3_client_raises_when_binary_is_missing():
    client = IPerf3Client(binary="missing-iperf3")

    with pytest.raises(IPerf3BinaryNotFoundError, match="missing-iperf3"):
        client.run("iperf.example.net")


def test_iperf3_client_raises_with_partial_result_on_failure(mocker):
    mocker.patch("client.iperf.client.require_execution_binary")
    mocker.patch(
        "client.iperf.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=json.dumps({"error": "unable to connect to server"}),
            stderr="connect failed",
        ),
    )

    with pytest.raises(IPerf3ProcessError) as exc_info:
        IPerf3Client().run("iperf.example.net")

    error = exc_info.value
    assert error.result is not None
    assert error.result.error == "unable to connect to server"
    assert error.returncode == 1


def test_iperf3_client_prefixes_command_with_namespace_when_local_disabled(mocker):
    mocker.patch("client.iperf.client.require_execution_binary")
    mocker.patch(
        "client.iperf.client.build_execution_command",
        return_value=[
            "nsenter",
            "-t",
            "1",
            "-m",
            "--",
            "ip",
            "netns",
            "exec",
            "ns1",
            "iperf3",
            "-J",
            "-c",
            "iperf.example.net",
            "-p",
            "5201",
            "-t",
            "10",
        ],
    )
    mock_run = mocker.patch(
        "client.iperf.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="{}",
            stderr="",
        ),
    )

    IPerf3Client().run("iperf.example.net")

    mock_run.assert_called_once_with(
        [
            "nsenter",
            "-t",
            "1",
            "-m",
            "--",
            "ip",
            "netns",
            "exec",
            "ns1",
            "iperf3",
            "-J",
            "-c",
            "iperf.example.net",
            "-p",
            "5201",
            "-t",
            "10",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
