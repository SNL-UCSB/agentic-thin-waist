"""
pcap_split.py — Step 1: Split gateway PCAPs by internal IP address.

For each packet in the input PCAP:

- Source IP is *internal* → **upload** traffic for that source host.
  Written to ``<output_dir>/users/<src_ip>/upload/<pcap_stem>.pcap``
- Destination IP is *internal* → **download** traffic for that dest host.
  Written to ``<output_dir>/users/<dst_ip>/download/<pcap_stem>.pcap``

A packet can match both criteria (intra-campus traffic); in that case it is
written to both the source host's upload directory and the destination host's
download directory.

Scalability
~~~~~~~~~~~
- PCAP files are read with :class:`scapy.utils.PcapReader` (streaming; the
  entire file is never loaded into memory).
- One :class:`scapy.utils.PcapWriter` per ``(ip, direction)`` pair is held
  open during processing and flushed/closed in a ``finally`` block.
- Multiple input PCAPs are processed in parallel via
  :func:`split_pcaps_parallel`.

Expected output layout
~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: text

    <output_dir>/
    └── users/
        ├── 169.231.10.5/
        │   ├── upload/
        │   │   └── gateway-trace.pcap
        │   └── download/
        │       └── gateway-trace.pcap
        └── 169.231.12.3/
            ├── upload/
            └── download/
"""

from __future__ import annotations

import logging
import multiprocessing as mp
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scapy.layers.inet import IP
from scapy.utils import PcapReader, PcapWriter

logger = logging.getLogger(__name__)


def _is_internal(ip_str: str, internal_subnets: List[str]) -> bool:
    """Return ``True`` if *ip_str* starts with any prefix in *internal_subnets*.

    This is a fast string-prefix check rather than a full subnet mask test.
    It is consistent with the approach used throughout the existing codebase.

    Args:
        ip_str: Dotted-decimal IP address string, e.g. ``'169.231.10.5'``.
        internal_subnets: List of prefix strings, e.g. ``['128.111', '169.231']``.

    Returns:
        ``True`` if the IP belongs to any configured internal subnet.
    """
    return any(ip_str.startswith(prefix) for prefix in internal_subnets)


def split_pcap_by_ip(
    pcap_input: Path,
    output_dir: Path,
    internal_subnets: List[str],
) -> Dict[str, Dict[str, Path]]:
    """Split a single gateway PCAP file by internal source/destination IP.

    Streams through *pcap_input* packet-by-packet without loading the full
    file into memory.  For each IP packet the source and destination addresses
    are checked against *internal_subnets*:

    - Internal ``src`` → packet written to ``users/<src>/upload/<stem>.pcap``
    - Internal ``dst`` → packet written to ``users/<dst>/download/<stem>.pcap``

    Non-IP packets are silently skipped.  Writers are opened lazily on first
    use and flushed/closed in a ``finally`` block to ensure no data is lost
    even if an error occurs mid-file.

    Args:
        pcap_input: Path to the input PCAP file.
        output_dir: Root output directory.  Created if it does not exist.
        internal_subnets: IP prefix strings identifying internal hosts.

    Returns:
        ``{ip: {"upload": Path, "download": Path}}`` for every internal IP
        found in the capture.  Only directions that actually received packets
        are included.

    Raises:
        FileNotFoundError: If *pcap_input* does not exist.
    """
    pcap_input = Path(pcap_input)
    output_dir = Path(output_dir)

    if not pcap_input.exists():
        raise FileNotFoundError(f"PCAP file not found: {pcap_input}")

    stem = pcap_input.stem
    logger.info("Splitting '%s' by internal IP (subnets: %s)", pcap_input.name, internal_subnets)

    # (ip_str, direction) → open PcapWriter
    writers: Dict[Tuple[str, str], PcapWriter] = {}
    # (ip_str) → {"upload": Path, "download": Path}
    result: Dict[str, Dict[str, Path]] = {}

    def _get_writer(ip: str, direction: str) -> PcapWriter:
        """Open (or return cached) a PcapWriter for the given (ip, direction)."""
        key = (ip, direction)
        if key not in writers:
            user_dir = output_dir / "users" / ip / direction
            user_dir.mkdir(parents=True, exist_ok=True)
            path = user_dir / f"{stem}.pcap"
            writers[key] = PcapWriter(str(path), append=False, sync=False)
            result.setdefault(ip, {})[direction] = path
        return writers[key]

    packets_total = 0
    packets_written = 0

    try:
        with PcapReader(str(pcap_input)) as reader:
            for pkt in reader:
                packets_total += 1
                if not pkt.haslayer(IP):
                    continue

                src = pkt[IP].src
                dst = pkt[IP].dst

                # Upload: internal source
                if _is_internal(src, internal_subnets):
                    _get_writer(src, "upload").write(pkt)
                    packets_written += 1

                # Download: internal destination
                if _is_internal(dst, internal_subnets):
                    _get_writer(dst, "download").write(pkt)
                    packets_written += 1

    finally:
        for writer in writers.values():
            writer.close()

    logger.info(
        "Split '%s': %d IP packets → %d written across %d users",
        pcap_input.name,
        packets_total,
        packets_written,
        len(result),
    )
    return result


def collect_pcap_inputs(input_path: Path) -> List[Path]:
    """Return all PCAP files under *input_path* (single file or directory).

    Args:
        input_path: A single ``.pcap`` file, or a directory that is searched
            recursively for ``*.pcap`` files.

    Returns:
        Sorted list of PCAP ``Path`` objects.

    Raises:
        FileNotFoundError: If *input_path* does not exist.
        ValueError: If *input_path* is neither a file nor a directory.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    if input_path.is_file():
        return [input_path]

    if input_path.is_dir():
        paths = sorted(input_path.rglob("*.pcap"))
        logger.info("Found %d PCAP file(s) under '%s'", len(paths), input_path)
        return paths

    raise ValueError(f"Input path is neither a file nor a directory: {input_path}")


def _split_pcap_worker(args: Tuple) -> Optional[Dict[str, Dict[str, Path]]]:
    """Multiprocessing worker that unpacks args and calls :func:`split_pcap_by_ip`.

    Returns the result dict on success, or ``None`` if an exception is raised.
    """
    pcap_input, output_dir, internal_subnets = args
    try:
        return split_pcap_by_ip(Path(pcap_input), Path(output_dir), internal_subnets)
    except Exception as exc:
        logger.error("Worker failed for '%s': %s", pcap_input, exc, exc_info=True)
        return None


def split_pcaps_parallel(
    pcap_paths: List[Path],
    output_dir: Path,
    internal_subnets: List[str],
    workers: int = 4,
) -> List[Dict[str, Dict[str, Path]]]:
    """Process multiple PCAP files in parallel, splitting each by internal IP.

    Args:
        pcap_paths: PCAP file paths to process.
        output_dir: Root output directory (shared across all input files).
        internal_subnets: Internal IP prefix strings.
        workers: Number of parallel processes.

    Returns:
        List of per-file result dicts (same shape as :func:`split_pcap_by_ip`).
        Entries are ``None`` for files that failed to process.
    """
    if not pcap_paths:
        logger.warning("No PCAP files provided for parallel split.")
        return []

    args_list = [(str(p), str(output_dir), internal_subnets) for p in pcap_paths]
    logger.info(
        "Splitting %d PCAP(s) in parallel using %d worker(s)",
        len(pcap_paths),
        workers,
    )

    # Use spawn context to avoid issues with scapy forking
    with mp.Pool(processes=workers) as pool:
        results = pool.map(_split_pcap_worker, args_list)

    failed = sum(1 for r in results if r is None)
    if failed:
        logger.warning("%d PCAP file(s) failed during parallel split.", failed)

    return [r for r in results if r is not None]
