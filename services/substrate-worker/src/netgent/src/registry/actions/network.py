from __future__ import annotations

from typing import Literal

from netgent.src.client.iperf import IPerf3Client, IPerf3Result
from netgent.src.client.ndt import NDT7Client, NDT7Result
from netgent.src.client.ping import PingClient, PingResult
from netgent.src.client.speedtest import SpeedtestClient, SpeedtestResult
from netgent.src.registry.actions.base import action
from netgent.src.registry.actions.exception import ActionError


@action(name="iperf")
def run_iperf(
    host: str,
    port: int | None = None,
    duration_seconds: int | None = None,
    interval_seconds: int | None = None,
    omit_seconds: int | None = None,
    udp: bool = False,
    reverse: bool = False,
    bitrate: str | None = None,
    parallel: int | None = None,
) -> IPerf3Result:
    client = IPerf3Client()
    return client.run(
        host=host,
        port=port,
        duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        omit_seconds=omit_seconds,
        udp=udp,
        reverse=reverse,
        bitrate=bitrate,
        parallel=parallel,
    )


@action(name="ndt")
def run_ndt(
    timeout: str | None = None,
    download: bool = True,
    upload: bool = True,
    server: str | None = None,
    service_url: str | None = None,
    scheme: Literal["ws", "wss"] | None = None,
    no_verify: bool = False,
    client_name: str | None = None,
) -> NDT7Result:
    if not download and not upload:
        raise ActionError("At least one of download or upload must be true")

    client = NDT7Client()
    return client.run(
        timeout=timeout,
        download=download,
        upload=upload,
        server=server,
        service_url=service_url,
        scheme=scheme,
        no_verify=no_verify,
        client_name=client_name,
    )


@action(name="ping")
def run_ping(
    host: str,
    count: int | None = None,
    interval_seconds: float | None = None,
    timeout_seconds: int | None = None,
    packet_size: int | None = None,
) -> PingResult:
    client = PingClient()
    return client.run(
        host=host,
        count=count,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        packet_size=packet_size,
    )


@action(name="speedtest")
def run_speedtest(
    secure: bool = False,
    server_id: int | None = None,
    source: str | None = None,
    timeout_seconds: int | None = None,
    share: bool = False,
    bytes_units: bool = False,
) -> SpeedtestResult:
    client = SpeedtestClient()
    return client.run(
        secure=secure,
        server_id=server_id,
        source=source,
        timeout_seconds=timeout_seconds,
        share=share,
        bytes_units=bytes_units,
    )


NETWORK_ACTIONS = (run_iperf, run_ndt, run_ping, run_speedtest)


__all__ = ["NETWORK_ACTIONS", "run_iperf", "run_ndt", "run_ping", "run_speedtest"]
