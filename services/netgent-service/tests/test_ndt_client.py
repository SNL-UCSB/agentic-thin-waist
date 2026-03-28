from __future__ import annotations

import subprocess

import pytest
from client.ndt import (
    NDT7BinaryNotFoundError,
    NDT7Client,
    NDT7ProcessError,
)
from pydantic import BaseModel


def test_ndt7_client_builds_expected_command(mocker):
    mocker.patch("client.ndt.client.require_execution_binary")
    mock_run = mocker.patch(
        "client.ndt.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"Key":"complete","Value":{"Test":"download"}}\n',
            stderr="",
        ),
    )

    client = NDT7Client(extra_args=["-quiet"])
    result = client.run_download(
        timeout="15s",
        server="mlab1.example.net",
        scheme="wss",
        no_verify=True,
        client_name="netgent",
    )

    mock_run.assert_called_once_with(
        [
            "ndt-client",
            "-format",
            "json",
            "-timeout",
            "15s",
            "-upload=false",
            "-server",
            "mlab1.example.net",
            "-scheme",
            "wss",
            "-no-verify",
            "-client-name",
            "netgent",
            "-quiet",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.completed_tests == ["download"]
    assert isinstance(client, BaseModel)
    assert isinstance(result, BaseModel)


def test_ndt7_client_parses_json_events(mocker):
    mocker.patch("client.ndt.client.require_execution_binary")
    mocker.patch(
        "client.ndt.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                '{"Key":"starting","Value":{"Test":"download"}}\n'
                '{"Key":"connected","Value":{"Test":"download","Server":"mlab1.example.net"}}\n'
                '{"Key":"measurement","Value":{"Test":"download","AppInfo":{"ElapsedTime":1234567}}}\n'
                '{"Key":"complete","Value":{"Test":"download"}}\n'
            ),
            stderr="",
        ),
    )

    result = NDT7Client().run_download()

    assert [event.key for event in result.events] == [
        "starting",
        "connected",
        "measurement",
        "complete",
    ]
    assert result.download_measurements == [
        {"Test": "download", "AppInfo": {"ElapsedTime": 1234567}}
    ]
    assert result.measurements == [
        {"Test": "download", "AppInfo": {"ElapsedTime": 1234567}}
    ]
    assert result.completed_tests == ["download"]


def test_ndt7_client_accepts_final_summary_payload(mocker):
    mocker.patch("client.ndt.client.require_execution_binary")
    mocker.patch(
        "client.ndt.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                '{"Key":"starting","Value":{"Test":"download"}}\n'
                '{"Key":"complete","Value":{"Test":"download"}}\n'
                '{"ServerFQDN":"ndt-mlab1.example.net","ServerIP":"192.0.2.10",'
                '"ClientIP":"198.51.100.25","Download":{"UUID":"uuid-123",'
                '"Throughput":{"Value":94.9,"Unit":"Mbit/s"}},"Upload":null}\n'
            ),
            stderr="",
        ),
    )

    result = NDT7Client().run_download()

    assert result.completed_tests == ["download"]
    assert result.summary == {
        "ServerFQDN": "ndt-mlab1.example.net",
        "ServerIP": "192.0.2.10",
        "ClientIP": "198.51.100.25",
        "Download": {
            "UUID": "uuid-123",
            "Throughput": {"Value": 94.9, "Unit": "Mbit/s"},
        },
        "Upload": None,
    }


def test_ndt7_client_raises_when_binary_is_missing():
    client = NDT7Client(binary="missing-ndt-client")

    with pytest.raises(NDT7BinaryNotFoundError, match="missing-ndt-client"):
        client.run()


def test_ndt7_client_raises_with_partial_result_on_process_failure(mocker):
    mocker.patch("client.ndt.client.require_execution_binary")
    mocker.patch(
        "client.ndt.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout='{"Key":"error","Value":{"Test":"download","Failure":"network error"}}\n',
            stderr="fatal: network error",
        ),
    )

    with pytest.raises(NDT7ProcessError) as exc_info:
        NDT7Client().run_download()

    error = exc_info.value
    assert error.returncode == 1
    assert error.result is not None
    assert error.result.errors == [{"Test": "download", "Failure": "network error"}]
    assert error.stderr == "fatal: network error"


def test_ndt7_client_prefixes_command_with_namespace_when_local_disabled(mocker):
    mocker.patch("client.ndt.client.require_execution_binary")
    mocker.patch(
        "client.ndt.client.build_execution_command",
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
            "ndt-client",
            "-format",
            "json",
            "-timeout",
            "55s",
            "-upload=false",
        ],
    )
    mock_run = mocker.patch(
        "client.ndt.client.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"Key":"complete","Value":{"Test":"download"}}\n',
            stderr="",
        ),
    )

    NDT7Client().run_download()

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
            "ndt-client",
            "-format",
            "json",
            "-timeout",
            "55s",
            "-upload=false",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
