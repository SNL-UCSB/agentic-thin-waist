"""Result analysis utilities for agentic-thin-waist experiments.

Pulls experiment results + artifacts from the Telemetry Service and provides
helpers to inspect QoE metrics and plot pcap time series.
"""

from .client import TelemetryClient, ExperimentBundle
from .pcap_analysis import (
    load_pcap,
    throughput_timeseries,
    icmp_rtt_pairs,
    tcp_flows,
    plot_throughput,
    plot_icmp_rtt,
    plot_packet_size,
    summarize_pcap,
)
from .qoe import (
    print_result_summary,
    print_qoe_metrics,
    print_transport_state,
    print_contextual_tree,
    extract_speedtest,
    extract_iperf,
    extract_ping,
)

__all__ = [
    "TelemetryClient",
    "ExperimentBundle",
    "load_pcap",
    "throughput_timeseries",
    "icmp_rtt_pairs",
    "tcp_flows",
    "plot_throughput",
    "plot_icmp_rtt",
    "plot_packet_size",
    "summarize_pcap",
    "print_result_summary",
    "print_qoe_metrics",
    "print_transport_state",
    "print_contextual_tree",
    "extract_speedtest",
    "extract_iperf",
    "extract_ping",
]
