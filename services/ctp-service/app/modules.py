"""
PCAP profile selection and processing utilities.

This module provides utilities for:
- Extracting network profile candidates from a tree structure
- Selecting profiles based on throughput, burstiness, asymmetry, or ON/OFF patterns
- Extracting users belonging to a profile
- Merging PCAPs belonging to selected users
- Reordering, padding, trimming, and validating PCAP files
- Parallel processing of PCAP workloads

The implementation avoids hard-coded constants, uses logging instead of print,
and provides consistent naming and docstrings suitable for production usage.
"""

import os
import json
import ipaddress
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Any
import multiprocessing as mp

import numpy as np
import pandas as pd
from scapy.all import rdpcap, wrpcap, IP
from scapy.utils import PcapReader

from create_trees import TreeNode
from load_trees import load_tree_from_json


# ----------------------------------------------------------------------
# Configuration constants
# ----------------------------------------------------------------------

BITS_PER_BYTE = 8
SECONDS_PER_MINUTE = 60
MBPS_DIVISOR = 1_000_000

DEFAULT_BATCH_SIZE = 30
DEFAULT_INTERVAL_SEC = 0.1
DEFAULT_WORKERS = max(1, int(mp.cpu_count() * 0.8))
MAX_USERS_PER_PROFILE = 2800


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Tree utilities
# ----------------------------------------------------------------------

def create_selection_pool(
    root: TreeNode,
    start_index: int,
    end_index: int
) -> Dict[str, List[Any]]:
    """
    Traverse a tree and build a dictionary of candidate network profiles.

    Each entry contains:
    [throughput_mbps, burstiness, asymmetry, start_index, end_index]

    Parameters
    ----------
    root : TreeNode
        Root node of the network tree.
    start_index : int
        Start PCAP index.
    end_index : int
        End PCAP index.

    Returns
    -------
    dict
        Mapping of subnet -> profile metadata.
    """

    nodes = {}
    queue = deque([root])
    visited = set()

    while queue:
        node = queue.popleft()
        visited.add(node)

        throughput_mbps = (
            node.downlink_bytes * BITS_PER_BYTE
        ) / (SECONDS_PER_MINUTE * MBPS_DIVISOR)

        nodes[str(node.network)] = [
            throughput_mbps,
            node.downlink_burstiness,
            node.asymmetry,
            start_index,
            end_index,
        ]

        for child in node.children:
            if child not in visited:
                queue.append(child)

    return nodes


# ----------------------------------------------------------------------
# ON/OFF burst analysis
# ----------------------------------------------------------------------

def calculate_on_off_transitions(
    traffic_array: np.ndarray,
    burst_size: int
) -> np.ndarray:
    """
    Detect ON transitions in a traffic waveform.

    Parameters
    ----------
    traffic_array : np.ndarray
        Time series of traffic measurements.
    burst_size : int
        Threshold for defining an ON state.

    Returns
    -------
    np.ndarray
        Binary array indicating ON transitions.
    """

    transitions = np.zeros_like(traffic_array)

    if traffic_array[0] >= burst_size:
        transitions[0] = 1

    for i in range(1, len(traffic_array)):
        if traffic_array[i] >= burst_size and traffic_array[i - 1] < burst_size:
            transitions[i] = 1

    return transitions


def create_selection_pool_on_off(
    root: TreeNode,
    start_index: int,
    end_index: int,
    burst_size: int
) -> Dict[str, List[Any]]:
    """
    Build profile pool using ON/OFF burst transitions.
    """

    nodes = {}
    queue = deque([root])
    visited = set()

    while queue:
        node = queue.popleft()
        visited.add(node)

        ons = calculate_on_off_transitions(
            np.array(node.download_fragment.container),
            burst_size
        )

        on_count = int(np.sum(ons == 1))

        nodes[f"{node.network}_{start_index}"] = [
            on_count,
            node.downlink_burstiness,
            node.asymmetry,
            start_index,
            end_index,
            list(node.download_fragment.container),
        ]

        for child in node.children:
            if child not in visited:
                queue.append(child)

    return nodes


# ----------------------------------------------------------------------
# Profile selection
# ----------------------------------------------------------------------

def select_profiles_by_on_off(
    nodes: Dict,
    on_count: int,
    max_profiles: int
) -> Dict:
    """
    Select profiles with a specific ON count.
    """

    selected = {}
    counter = 0
    name = f"on_{on_count}"

    for network, info in nodes.items():
        if info[0] == on_count:
            counter += 1
            selected[f"{name}_profile{counter}"] = [network, info]

            if counter == max_profiles:
                break

    return selected


def select_profiles_by_throughput(
    nodes: Dict,
    max_profiles: int,
    min_tp: float,
    max_tp: float
) -> Dict:
    """
    Select profiles within a throughput range.
    """

    selected = {}
    counter = 0
    name = f"tp_{min_tp}_{max_tp}"

    for network, info in nodes.items():
        if min_tp <= info[0] <= max_tp:
            counter += 1
            selected[f"{name}_profile{counter}"] = [network, info]

            if counter == max_profiles:
                break

    return selected


# ----------------------------------------------------------------------
# User extraction
# ----------------------------------------------------------------------

def get_users_of_profile(
    root_node: TreeNode,
    subnet_ip: str
) -> List[str]:
    """
    Extract all user IPs belonging to a subnet profile.
    """

    profile_node = root_node.find_subnet(
        target_subnet=ipaddress.ip_network(subnet_ip)
    )

    leaf_nodes = profile_node.get_leaf_nodes(profile_node)

    return [
        str(user.network.network_address)
        for user in leaf_nodes
    ]


def append_users_to_profiles(
    root_node: TreeNode,
    profiles: Dict,
    output_file: str
) -> None:
    """
    Append users to profile definitions and store them in JSON.
    """

    for profile, info in profiles.items():
        try:
            users = get_users_of_profile(root_node, info[0])
            profiles[profile].append(users)
        except Exception as e:
            logger.warning(f"Profile {profile} invalid: {e}")

    with open(output_file, "w") as f:
        json.dump(profiles, f)


# ----------------------------------------------------------------------
# PCAP merging
# ----------------------------------------------------------------------

def merge_pcaps_by_index(
    output_name: str,
    chosen_ips: List[str],
    start_index: int,
    end_index: int,
    pcap_dir: str,
    output_dir: str,
    batch_size: int = DEFAULT_BATCH_SIZE
) -> None:
    """
    Merge PCAP files for selected users across a range of indices.
    """

    logger.info(f"Merging PCAPs for {output_name}")

    pcap_names = [f"/pcap_{i}.pcap" for i in range(start_index, end_index + 1)]

    output_file = Path(output_dir) / f"{output_name}.pcap"
    tmp_file = Path(output_dir) / f"{output_name}_tmp.pcap"

    for i in range(0, len(chosen_ips), batch_size):

        current_ips = chosen_ips[i:i + batch_size]

        args = [
            str(Path(pcap_dir) / ip / pcap)
            for ip in current_ips
            for pcap in pcap_names
        ]

        cmd = ["joincap", "-w", str(output_file)] + args

        if i != 0:
            os.rename(output_file, tmp_file)
            cmd.append(str(tmp_file))

        subprocess.run(cmd, check=True)

        if tmp_file.exists():
            tmp_file.unlink()


# ----------------------------------------------------------------------
# PCAP ordering
# ----------------------------------------------------------------------

def reorder_pcap_files(input_dir: str) -> None:
    """
    Reorder packets in PCAP files using reordercap.
    """

    input_path = Path(input_dir)
    output_path = Path(f"{input_dir}_reordered")

    output_path.mkdir(exist_ok=True)

    for file in input_path.glob("*.pcap"):

        output_file = output_path / file.name

        subprocess.run(
            ["reordercap", str(file), str(output_file)],
            check=True
        )

    for file in input_path.glob("*"):
        file.unlink()

    for file in output_path.glob("*"):
        file.rename(input_path / file.name)

    output_path.rmdir()


# ----------------------------------------------------------------------
# PCAP padding
# ----------------------------------------------------------------------

def pad_pcap_frames(
    input_pcap: str,
    temp_output: str
) -> None:
    """
    Fix incorrect frame lengths and pad packets if necessary.
    """

    packets = rdpcap(input_pcap)
    modified = []

    for pkt in packets:

        if pkt.haslayer(IP):

            correct_len = pkt[IP].len + 14

            if pkt.wirelen != correct_len:
                pkt.wirelen = correct_len

        modified.append(pkt)

    wrpcap(temp_output, modified)

    subprocess.run(
        [
            "tcprewrite",
            "-F",
            "pad",
            f"--infile={temp_output}",
            f"--outfile={input_pcap}",
        ],
        check=True,
    )

    os.remove(temp_output)


# ----------------------------------------------------------------------
# PCAP trimming
# ----------------------------------------------------------------------

def trim_pcap_by_rate(
    pcap_file: str,
    output_file: str,
    threshold_bytes: int,
    interval_sec: float = DEFAULT_INTERVAL_SEC
) -> None:
    """
    Trim packets when interval traffic exceeds threshold.
    """

    logger.info(f"Processing {pcap_file}")

    interval_start = None
    total_bytes = 0

    output_packets = []

    with PcapReader(pcap_file) as reader:

        for pkt in reader:

            if not pkt.haslayer(IP):
                continue

            packet_size = pkt[IP].len
            packet_time = datetime.fromtimestamp(float(pkt.time))

            if interval_start is None:
                interval_start = packet_time

            if (packet_time - interval_start).total_seconds() < interval_sec:

                if total_bytes <= threshold_bytes:
                    output_packets.append(pkt)

                total_bytes += packet_size

            else:

                interval_start += timedelta(seconds=interval_sec)
                total_bytes = packet_size
                output_packets.append(pkt)

    wrpcap(output_file, output_packets)


# ----------------------------------------------------------------------
# Parallel utilities
# ----------------------------------------------------------------------

def parallel_process(
    func,
    args_list: List[Tuple],
    workers: int = DEFAULT_WORKERS
) -> None:
    """
    Run a function in parallel using multiprocessing.
    """

    with mp.Pool(workers) as pool:
        pool.starmap(func, args_list)


# ----------------------------------------------------------------------
# PCAP validation
# ----------------------------------------------------------------------

def validate_pcap_lengths(file_name: str) -> None:
    """
    Verify that frame length is greater than IP length.
    """

    cmd = [
        "tshark",
        "-r",
        file_name,
        "-T",
        "fields",
        "-e",
        "frame.len",
        "-e",
        "ip.len",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )

    data = pd.read_csv(
        pd.compat.StringIO(result.stdout),
        sep="\t",
        header=None
    )

    if not all(data.iloc[:, 0] > data.iloc[:, 1]):
        logger.error(f"Invalid frame lengths in {file_name}")


# ----------------------------------------------------------------------
# CLI entry
# ----------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("PCAP utilities module loaded.")