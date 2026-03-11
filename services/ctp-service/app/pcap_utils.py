"""
pcap_utils.py — PCAP profile selection and processing utilities.

This module provides the tooling needed to go from a set of network trees
to final merged PCAP files ready for CTP replay.

Pipeline stage: **trees → node selection → CTP**

Responsibilities
~~~~~~~~~~~~~~~~
- **Profile pool construction** — traverse a ``TreeNode`` tree and extract
  candidate subnets with their traffic metrics (throughput, burstiness,
  asymmetry, ON/OFF transitions).
- **Profile selection** — filter the candidate pool by throughput range or
  ON/OFF burst count.
- **User extraction** — map a selected subnet back to its leaf (per-user) IP
  addresses.
- **PCAP merging** — use ``joincap`` to merge per-user PCAP files for all IPs
  belonging to a chosen profile.
- **PCAP post-processing** — reorder (``reordercap``), pad (``tcprewrite``),
  trim over-limit traffic, and validate frame-length correctness.
- **Parallel execution** — generic ``parallel_process`` wrapper around
  ``multiprocessing.Pool.starmap``.

Constants
~~~~~~~~~
``BITS_PER_BYTE``, ``SECONDS_PER_MINUTE``, ``MBPS_DIVISOR``
    Used when converting raw byte counts to Mbps.

``DEFAULT_BATCH_SIZE``
    Maximum number of IPs joined in a single ``joincap`` invocation.

``DEFAULT_INTERVAL_SEC``
    Interval width (seconds) used by :func:`trim_pcap_by_rate`.

``DEFAULT_WORKERS``
    Default worker count for :func:`parallel_process` (80 % of CPU cores).

``MAX_USERS_PER_PROFILE``
    Informational cap; not enforced internally but useful as a guard in
    calling code.
"""

import io
import json
import ipaddress
import logging
import multiprocessing as mp
import os
import subprocess
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import numpy as np
import pandas as pd
from scapy.all import rdpcap, wrpcap, IP
from scapy.utils import PcapReader

from tree_node import TreeNode


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

BITS_PER_BYTE: int = 8
SECONDS_PER_MINUTE: int = 60
MBPS_DIVISOR: int = 1_000_000

DEFAULT_BATCH_SIZE: int = 30
DEFAULT_INTERVAL_SEC: float = 0.1
DEFAULT_WORKERS: int = max(1, int(mp.cpu_count() * 0.8))
MAX_USERS_PER_PROFILE: int = 2800


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile pool construction
# ---------------------------------------------------------------------------

def create_selection_pool(
    root: TreeNode,
    start_index: int,
    end_index: int,
) -> Dict[str, List[Any]]:
    """Traverse the tree and build a candidate profile pool keyed by subnet.

    Performs a BFS over the entire tree.  For each node the throughput in Mbps
    is derived from ``downlink_bytes``.

    Each pool entry has the layout::

        [throughput_mbps, downlink_burstiness, asymmetry, start_index, end_index]

    Args:
        root: Root of the ``TreeNode`` tree to traverse.
        start_index: First PCAP file index for this time range.
        end_index: Last PCAP file index for this time range (inclusive).

    Returns:
        A dictionary mapping subnet string (e.g. ``'169.231.0.0/16'``) to its
        profile metadata list.
    """
    nodes: Dict[str, List[Any]] = {}
    queue = deque([root])
    visited: set = set()

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


# ---------------------------------------------------------------------------
# ON/OFF burst analysis
# ---------------------------------------------------------------------------

def calculate_on_off_transitions(
    traffic_array: np.ndarray,
    burst_size: int,
) -> np.ndarray:
    """Detect the start of ON bursts in a traffic time series.

    A bin is marked as an ON *transition* (value 1) when the traffic crosses
    upward through *burst_size* — i.e. the current bin meets the threshold but
    the previous bin did not.  The very first bin is also marked if it meets
    the threshold.

    Args:
        traffic_array: 1-D array of per-bin byte counts.
        burst_size: Minimum byte count that qualifies as an ON state.

    Returns:
        A binary array of the same shape as *traffic_array* where 1 indicates
        an ON transition and 0 indicates no transition.
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
    burst_size: int,
) -> Dict[str, List[Any]]:
    """Build a profile pool based on ON/OFF burst transition counts.

    Identical to :func:`create_selection_pool` but each entry is keyed by
    ``<subnet>_<start_index>`` and the first field is the number of ON
    transitions rather than throughput.

    Each pool entry has the layout::

        [on_count, downlink_burstiness, asymmetry, start_index, end_index,
         download_fragment_list]

    Args:
        root: Root of the ``TreeNode`` tree.
        start_index: First PCAP file index for this time range.
        end_index: Last PCAP file index for this time range (inclusive).
        burst_size: Per-bin byte threshold for an ON state.

    Returns:
        A dictionary mapping ``'<subnet>_<start_index>'`` to its ON/OFF
        profile metadata list.
    """
    nodes: Dict[str, List[Any]] = {}
    queue = deque([root])
    visited: set = set()

    while queue:
        node = queue.popleft()
        visited.add(node)

        ons = calculate_on_off_transitions(
            np.array(node.download_fragment.container), burst_size
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


# ---------------------------------------------------------------------------
# Profile selection
# ---------------------------------------------------------------------------

def select_profiles_by_on_off(
    nodes: Dict,
    on_count: int,
    max_profiles: int,
) -> Dict:
    """Select profiles from a pool that have exactly *on_count* ON transitions.

    Args:
        nodes: Profile pool produced by :func:`create_selection_pool_on_off`.
        on_count: The exact ON transition count to match.
        max_profiles: Maximum number of profiles to return.

    Returns:
        A dictionary of selected profiles keyed by
        ``'on_<on_count>_profile<n>'``.  Each value is ``[network_key, info]``.
    """
    selected: Dict = {}
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
    max_tp: float,
) -> Dict:
    """Select profiles whose throughput falls within [*min_tp*, *max_tp*] Mbps.

    Args:
        nodes: Profile pool produced by :func:`create_selection_pool`.
        max_profiles: Maximum number of profiles to return.
        min_tp: Minimum throughput in Mbps (inclusive).
        max_tp: Maximum throughput in Mbps (inclusive).

    Returns:
        A dictionary of selected profiles keyed by
        ``'tp_<min_tp>_<max_tp>_profile<n>'``.
    """
    selected: Dict = {}
    counter = 0
    name = f"tp_{min_tp}_{max_tp}"

    for network, info in nodes.items():
        if min_tp <= info[0] <= max_tp:
            counter += 1
            selected[f"{name}_profile{counter}"] = [network, info]
            if counter == max_profiles:
                break

    return selected


# ---------------------------------------------------------------------------
# User extraction
# ---------------------------------------------------------------------------

def get_users_of_profile(root_node: TreeNode, subnet_ip: str) -> List[str]:
    """Return the IP strings of all leaf users under *subnet_ip*.

    Locates the node for *subnet_ip* in the tree and collects all /32 leaf
    descendants via :meth:`TreeNode.get_leaf_nodes`.

    Args:
        root_node: Root of the full ``TreeNode`` tree.
        subnet_ip: Subnet string, e.g. ``'169.231.10.0/24'``.

    Returns:
        A list of IP address strings (e.g. ``['169.231.10.5', ...]``).

    Raises:
        AttributeError: If *subnet_ip* is not found in the tree (``find_subnet``
            returns ``None``).
    """
    profile_node = root_node.find_subnet(ipaddress.ip_network(subnet_ip))
    leaf_nodes = TreeNode.get_leaf_nodes(profile_node)
    return [str(user.network.network_address) for user in leaf_nodes]


def append_users_to_profiles(
    root_node: TreeNode,
    profiles: Dict,
    output_file: str,
) -> None:
    """Resolve user IP lists for each profile and persist the enriched dict.

    For each profile entry, calls :func:`get_users_of_profile` and appends the
    resulting list to the profile's metadata.  Invalid profiles (subnet not
    found) are logged and skipped.  The final dictionary is written to
    *output_file* as JSON.

    Args:
        root_node: Root of the ``TreeNode`` tree used for user lookup.
        profiles: Profile dictionary as returned by a ``select_profiles_*``
            function.  Modified in-place.
        output_file: Path to the JSON file that will store the enriched profiles.
    """
    for profile, info in profiles.items():
        try:
            users = get_users_of_profile(root_node, info[0])
            profiles[profile].append(users)
        except Exception as e:
            logger.warning(f"Profile {profile} invalid: {e}")

    with open(output_file, "w") as f:
        json.dump(profiles, f)


# ---------------------------------------------------------------------------
# PCAP merging
# ---------------------------------------------------------------------------

def merge_pcaps_by_index(
    output_name: str,
    chosen_ips: List[str],
    start_index: int,
    end_index: int,
    pcap_dir: str,
    output_dir: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Merge per-user PCAP files for a range of indices into a single file.

    Calls ``joincap`` in batches of *batch_size* IPs to avoid hitting OS
    argument-length limits.  Intermediate batches are merged incrementally
    into the output file via a temporary rename.

    File layout assumed under *pcap_dir*::

        <pcap_dir>/<ip>/pcap_<index>.pcap

    Args:
        output_name: Base name for the output file (without ``.pcap`` extension).
        chosen_ips: List of IP address strings whose PCAPs should be merged.
        start_index: First PCAP index to include.
        end_index: Last PCAP index to include (inclusive).
        pcap_dir: Root directory containing per-user PCAP sub-directories.
        output_dir: Directory where the merged output file is written.
        batch_size: Number of IPs to join per ``joincap`` invocation.
            Defaults to :data:`DEFAULT_BATCH_SIZE`.
    """
    logger.info(f"Merging PCAPs for {output_name}")

    pcap_names = [f"/pcap_{i}.pcap" for i in range(start_index, end_index + 1)]
    output_file = Path(output_dir) / f"{output_name}.pcap"
    tmp_file = Path(output_dir) / f"{output_name}_tmp.pcap"

    for i in range(0, len(chosen_ips), batch_size):
        current_ips = chosen_ips[i : i + batch_size]
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


def merge_profile_pcaps(
    profile_name: str,
    profile_info: List[Any],
    root_node: TreeNode,
    pcap_dir: str,
    output_dir: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """Merge PCAPs for all users belonging to a single profile.

    Convenience wrapper around :func:`merge_pcaps_by_index` that unpacks a
    profile entry produced by :func:`append_users_to_profiles`.  If the profile
    entry does not yet contain a user list (index 2), the list is resolved
    on-the-fly via :func:`get_users_of_profile`.

    Args:
        profile_name: Label used as the output file base name
            (e.g. ``'on_3_profile1'``).
        profile_info: Profile entry list with layout
            ``[subnet_str, metadata_list, user_ips]`` where *user_ips* is
            optional.  *metadata_list* must contain ``start_index`` at position
            3 and ``end_index`` at position 4.
        root_node: Root of the ``TreeNode`` tree, used to resolve users when
            *profile_info* does not already include a user list.
        pcap_dir: Root directory containing per-user PCAP sub-directories.
        output_dir: Destination directory for the merged PCAP file.
        batch_size: Number of IPs per ``joincap`` call.
            Defaults to :data:`DEFAULT_BATCH_SIZE`.
    """
    subnet_str: str = profile_info[0]
    metadata: List[Any] = profile_info[1]
    start_index: int = metadata[3]
    end_index: int = metadata[4]

    if len(profile_info) >= 3:
        chosen_ips: List[str] = profile_info[2]
    else:
        chosen_ips = get_users_of_profile(root_node, subnet_str)

    merge_pcaps_by_index(
        output_name=profile_name,
        chosen_ips=chosen_ips,
        start_index=start_index,
        end_index=end_index,
        pcap_dir=pcap_dir,
        output_dir=output_dir,
        batch_size=batch_size,
    )


# ---------------------------------------------------------------------------
# PCAP ordering
# ---------------------------------------------------------------------------

def reorder_pcap_files(input_dir: str) -> None:
    """Reorder packets in all PCAP files in *input_dir* using ``reordercap``.

    Writes reordered files to a temporary ``<input_dir>_reordered`` directory,
    then atomically replaces the originals.

    Args:
        input_dir: Directory containing ``*.pcap`` files to reorder.
    """
    input_path = Path(input_dir)
    output_path = Path(f"{input_dir}_reordered")
    output_path.mkdir(exist_ok=True)

    for file in input_path.glob("*.pcap"):
        subprocess.run(["reordercap", str(file), str(output_path / file.name)], check=True)

    for file in input_path.glob("*"):
        file.unlink()
    for file in output_path.glob("*"):
        file.rename(input_path / file.name)
    output_path.rmdir()


# ---------------------------------------------------------------------------
# PCAP padding
# ---------------------------------------------------------------------------

def pad_pcap_frames(input_pcap: str, temp_output: str) -> None:
    """Fix incorrect Ethernet frame lengths and pad short frames if needed.

    Iterates over all packets in *input_pcap*, corrects ``wirelen`` when it
    does not equal ``ip.len + 14`` (Ethernet header), writes the adjusted
    packets to *temp_output*, and then runs ``tcprewrite --pad`` to bring
    under-size frames up to the minimum Ethernet frame length.

    Args:
        input_pcap: Path to the input PCAP file.  The corrected output
            overwrites this file.
        temp_output: Path used for the intermediate Scapy-written file.
            Deleted after ``tcprewrite`` completes.
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
        ["tcprewrite", "-F", "pad", f"--infile={temp_output}", f"--outfile={input_pcap}"],
        check=True,
    )
    os.remove(temp_output)


# ---------------------------------------------------------------------------
# PCAP trimming
# ---------------------------------------------------------------------------

def trim_pcap_by_rate(
    pcap_file: str,
    output_file: str,
    threshold_bytes: int,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
) -> None:
    """Drop packets in intervals where traffic exceeds *threshold_bytes*.

    Reads *pcap_file* packet by packet.  Within each *interval_sec* window,
    packets are forwarded to the output until the cumulative byte count
    exceeds *threshold_bytes*; subsequent packets in that window are dropped.
    The first packet of every new interval is always forwarded (to preserve
    inter-arrival timing structure).

    Args:
        pcap_file: Path to the input PCAP file.
        output_file: Path for the trimmed output PCAP file.
        threshold_bytes: Maximum cumulative bytes allowed per interval before
            subsequent packets are dropped.
        interval_sec: Duration of each rate-measurement window in seconds.
            Defaults to :data:`DEFAULT_INTERVAL_SEC` (100 ms).
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


# ---------------------------------------------------------------------------
# Parallel utilities
# ---------------------------------------------------------------------------

def parallel_process(
    func: Callable,
    args_list: List[Tuple],
    workers: int = DEFAULT_WORKERS,
) -> None:
    """Run *func* in parallel over *args_list* using ``multiprocessing.Pool``.

    Args:
        func: A picklable callable to invoke for each argument tuple.
        args_list: List of argument tuples; each tuple is unpacked and passed
            to *func* via ``starmap``.
        workers: Number of worker processes.
            Defaults to :data:`DEFAULT_WORKERS`.
    """
    with mp.Pool(workers) as pool:
        pool.starmap(func, args_list)


# ---------------------------------------------------------------------------
# PCAP validation
# ---------------------------------------------------------------------------

def validate_pcap_lengths(file_name: str) -> None:
    """Verify that every frame's Ethernet length exceeds its IP length.

    Uses ``tshark`` to extract ``frame.len`` and ``ip.len`` for every packet
    and logs an error if any frame violates the invariant
    ``frame.len > ip.len``.

    Args:
        file_name: Path to the PCAP file to validate.

    Raises:
        subprocess.CalledProcessError: If the ``tshark`` invocation fails.
    """
    cmd = [
        "tshark", "-r", file_name,
        "-T", "fields",
        "-e", "frame.len",
        "-e", "ip.len",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    data = pd.read_csv(io.StringIO(result.stdout), sep="\t", header=None)

    if not all(data.iloc[:, 0] > data.iloc[:, 1]):
        logger.error(f"Invalid frame lengths in {file_name}")


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("PCAP utilities module loaded.")
