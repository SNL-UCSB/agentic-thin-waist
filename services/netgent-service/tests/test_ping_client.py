from __future__ import annotations

import subprocess

import pytest
from pydantic import BaseModel

from clients.netgent.src.client.ping import (
    PingBinaryNotFoundError,
    PingClient,
    PingProcessError,
)


def test_ping_client_builds_expected_command(mocker):
    mocker.patch("clients.netgent.src.client.ping.client.require_execution_binary")
    mock_run = mocker.patch(
        "clients.netgent.src.client.ping.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    client = PingClient(extra_args=["-n"])
    result = client.run(
        "1.1.1.1",
        count=3,
        interval_seconds=0.2,
        timeout_seconds=1,
        packet_size=64,
    )

    mock_run.assert_called_once_with(
        ["ping", "-c", "3", "-i", "0.2", "-W", "1", "-s", "64", "-n", "1.1.1.1"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert isinstance(client, BaseModel)
    assert isinstance(result, BaseModel)


def test_ping_client_parses_output(mocker):
    mocker.patch("clients.netgent.src.client.ping.client.require_execution_binary")
    mocker.patch(
        "clients.netgent.src.client.ping.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                "PING google.com (142.250.72.14) 56(84) bytes of data.\n"
                "64 bytes from 142.250.72.14: icmp_seq=1 ttl=116 time=9.91 ms\n"
                "64 bytes from 142.250.72.14: icmp_seq=2 ttl=116 time=10.23 ms\n"
                "--- google.com ping statistics ---\n"
                "2 packets transmitted, 2 received, 0% packet loss, time 1001ms\n"
                "rtt min/avg/max/mdev = 9.910/10.070/10.230/0.160 ms\n"
            ),
            stderr="",
        ),
    )

    result = PingClient().run("google.com", count=2)

    assert result.host == "google.com"
    assert result.resolved_ip == "142.250.72.14"
    assert len(result.replies) == 2
    assert result.packet_loss_percent == 0.0
    assert result.avg_latency_ms == 10.07
    assert result.jitter_ms == 0.16


def test_ping_client_raises_when_binary_is_missing():
    client = PingClient(binary="missing-ping")

    with pytest.raises(PingBinaryNotFoundError, match="missing-ping"):
        client.run("1.1.1.1")


def test_ping_client_raises_with_partial_result_on_failure(mocker):
    mocker.patch("clients.netgent.src.client.ping.client.require_execution_binary")
    mocker.patch(
        "clients.netgent.src.client.ping.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout=(
                "PING 1.1.1.1 (1.1.1.1) 56(84) bytes of data.\n"
                "--- 1.1.1.1 ping statistics ---\n"
                "2 packets transmitted, 0 received, 100% packet loss, time 1001ms\n"
            ),
            stderr="timeout",
        ),
    )

    with pytest.raises(PingProcessError) as exc_info:
        PingClient().run("1.1.1.1", count=2)

    error = exc_info.value
    assert error.result is not None
    assert error.result.packet_loss_percent == 100.0
    assert error.returncode == 1


def test_ping_client_prefixes_command_with_namespace_when_local_disabled(mocker):
    mocker.patch("clients.netgent.src.client.ping.client.require_execution_binary")
    mocker.patch(
        "clients.netgent.src.client.ping.client.build_execution_command",
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
            "ping",
            "-c",
            "2",
            "1.1.1.1",
        ],
    )
    mock_run = mocker.patch(
        "clients.netgent.src.client.ping.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    PingClient().run("1.1.1.1", count=2)

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
            "ping",
            "-c",
            "2",
            "1.1.1.1",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
