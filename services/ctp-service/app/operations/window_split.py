"""
window_split.py — Step 2: Split per-user PCAPs into fixed-duration time windows.

Each user's upload and download PCAP (produced by Step 1) is split into
sequential time windows of equal duration.  Window files are named with
zero-padded four-digit indices:

.. code-block:: text

    <user_dir>/upload/
        window_0001.pcap
        window_0002.pcap
        ...
    <user_dir>/download/
        window_0001.pcap
        window_0002.pcap
        ...

Window boundaries are determined by packet timestamps:

- The first packet's timestamp is used as the capture start.
- Windows are ``[start + n*duration, start + (n+1)*duration)`` for n = 0, 1, …
- Empty windows (no packets) are **not** written to avoid sparse directories.

Scalability
~~~~~~~~~~~
- Packets are streamed one at a time with :class:`scapy.utils.PcapReader`.
- At most one :class:`scapy.utils.PcapWriter` is open at a time per
  user-direction pair.
- :func:`split_all_users_parallel` processes all users in parallel.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
from pathlib import Path
from typing import List, Optional, Tuple

from scapy.utils import PcapReader, PcapWriter

logger = logging.getLogger(__name__)


def split_pcap_into_windows(
    input_pcap: Path,
    output_dir: Path,
    window_sec: int = 30,
) -> List[Path]:
    """Split a single PCAP file into fixed-duration time-window files.

    Streams through *input_pcap* packet-by-packet.  The first packet's
    timestamp is the epoch anchor; subsequent packets are bucketed by which
    ``window_sec``-wide interval they fall into.

    Args:
        input_pcap: Path to the input PCAP file (upload or download).
        output_dir: Directory where ``window_XXXX.pcap`` files are written.
            Created if it does not exist.
        window_sec: Duration of each window in seconds.  Default 30 s.

    Returns:
        Sorted list of paths to the written window PCAP files.
        Empty if *input_pcap* contains no packets.

    Raises:
        FileNotFoundError: If *input_pcap* does not exist.
    """
    input_pcap = Path(input_pcap)
    output_dir = Path(output_dir)

    if not input_pcap.exists():
        raise FileNotFoundError(f"PCAP not found: {input_pcap}")

    output_dir.mkdir(parents=True, exist_ok=True)

    written_paths: List[Path] = []
    current_window_idx: Optional[int] = None
    current_writer: Optional[PcapWriter] = None
    start_time: Optional[float] = None

    def _open_window(idx: int) -> PcapWriter:
        out_path = output_dir / f"window_{idx:04d}.pcap"
        written_paths.append(out_path)
        return PcapWriter(str(out_path), append=False, sync=False)

    try:
        with PcapReader(str(input_pcap)) as reader:
            for pkt in reader:
                try:
                    pkt_time = float(pkt.time)
                except Exception:
                    continue  # skip packets with unparseable timestamps

                if start_time is None:
                    start_time = pkt_time

                elapsed = pkt_time - start_time
                if elapsed < 0:
                    # Packet before capture start — skip (e.g. pre-existing flow)
                    continue

                window_idx = int(elapsed // window_sec) + 1  # 1-based

                if window_idx != current_window_idx:
                    if current_writer is not None:
                        current_writer.close()
                    current_window_idx = window_idx
                    current_writer = _open_window(window_idx)

                current_writer.write(pkt)

    finally:
        if current_writer is not None:
            current_writer.close()

    if not written_paths:
        logger.debug(
            "No packets found in '%s'; no window files written.", input_pcap.name
        )
    else:
        logger.debug(
            "Split '%s' into %d window(s) of %d s each.",
            input_pcap.name,
            len(written_paths),
            window_sec,
        )

    return sorted(written_paths)


def split_user_windows(
    user_dir: Path,
    window_sec: int = 30,
) -> Tuple[List[Path], List[Path]]:
    """Split both upload and download PCAPs for a single user directory.

    Expects the following layout under *user_dir*::

        <user_dir>/
            upload/   (contains one or more .pcap files)
            download/ (contains one or more .pcap files)

    For each direction the per-source PCAPs (which may have been produced by
    multiple input gateway captures) are split into windows.  When more than
    one source PCAP is present, they are processed in sorted order but each
    file's windows are numbered independently starting from 1.  If the caller
    needs cross-file continuous numbering it should merge the source PCAPs
    first.

    Args:
        user_dir: Root directory for a single internal user IP
            (e.g. ``<output_dir>/users/169.231.10.5``).
        window_sec: Window duration in seconds.

    Returns:
        Tuple ``(upload_window_paths, download_window_paths)``.
    """
    upload_windows: List[Path] = []
    download_windows: List[Path] = []

    for direction, acc in [("upload", upload_windows), ("download", download_windows)]:
        direction_dir = user_dir / direction
        if not direction_dir.exists():
            continue
        source_pcaps = sorted(direction_dir.glob("*.pcap"))
        for pcap in source_pcaps:
            # Write windows into a subdirectory named after the source file stem
            windows_dir = direction_dir / "windows" / pcap.stem
            paths = split_pcap_into_windows(pcap, windows_dir, window_sec=window_sec)
            acc.extend(paths)

    return upload_windows, download_windows


def _split_user_worker(args: Tuple) -> Optional[Tuple[List[str], List[str]]]:
    """Multiprocessing worker for :func:`split_all_users_parallel`."""
    user_dir_str, window_sec = args
    try:
        up, dl = split_user_windows(Path(user_dir_str), window_sec=window_sec)
        return [str(p) for p in up], [str(p) for p in dl]
    except Exception as exc:
        logger.error(
            "Window split failed for '%s': %s", user_dir_str, exc, exc_info=True
        )
        return None


def split_all_users_parallel(
    users_root: Path,
    window_sec: int = 30,
    workers: int = 4,
) -> int:
    """Split upload and download PCAPs for all users under *users_root* in parallel.

    Args:
        users_root: Directory containing one sub-directory per internal IP
            (produced by :mod:`~app.operations.pcap_split`).
        window_sec: Window duration in seconds.
        workers: Number of parallel worker processes.

    Returns:
        Number of user directories successfully processed.
    """
    users_root = Path(users_root)
    if not users_root.exists():
        raise FileNotFoundError(f"Users directory not found: {users_root}")

    user_dirs = sorted(d for d in users_root.iterdir() if d.is_dir())
    if not user_dirs:
        logger.warning("No user directories found under '%s'.", users_root)
        return 0

    args_list = [(str(d), window_sec) for d in user_dirs]
    logger.info(
        "Splitting windows for %d user(s) using %d worker(s) " "(window=%d s)",
        len(user_dirs),
        workers,
        window_sec,
    )

    with mp.Pool(processes=workers) as pool:
        results = pool.map(_split_user_worker, args_list)

    succeeded = sum(1 for r in results if r is not None)
    failed = len(results) - succeeded
    if failed:
        logger.warning("%d user(s) failed during window split.", failed)

    logger.info(
        "Window split complete: %d/%d users succeeded.", succeeded, len(user_dirs)
    )
    return succeeded
