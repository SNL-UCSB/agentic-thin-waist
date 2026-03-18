"""
time_series_modules.py — PCAP-to-time-series conversion.

This module converts raw PCAP files into per-user ``TimeSeries`` objects that
can be fed into the subnet tree construction stage.

Pipeline stage: **pcap → timeseries**

Key classes:

- ``Fragment`` — a fixed-length array of 100 ms traffic bins.
- ``TimeFrame`` — a 60-second window of raw (timestamp, bytes) observations.
- ``TimeSeries`` — a per-user collection of download and upload fragments.
- ``TimeSeriesProcessor`` — orchestrates PCAP reading, splitting, and binning.

Network prefix configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Upload vs. download classification is based on the destination IP address.
Packets destined for an IP in ``network_prefixes`` are counted as *download*
(inbound to the user); all others are counted as *upload* (outbound).

Pass a custom ``network_prefixes`` list to ``TimeSeriesProcessor`` to adapt the
pipeline to networks other than the UCSB campus.
"""

from __future__ import annotations

import os
import pickle
import subprocess
import multiprocessing as mp

import numpy as np

#: Default IP prefixes used to identify download (inbound) traffic.
#: These are UCSB campus subnets and should be overridden for other deployments.
_DEFAULT_NETWORK_PREFIXES: list[str] = [
    "128.111",
    "169.231",
    "192.150.216",
    "192.150.217",
    "92.35.222",
    "199.120.153",
]


class TimeFrame:
    """A fixed-length observation window used to bin raw packet data.

    Packets captured within a ``TIME_FRAME_LEN``-second sliding window are
    stored here before being converted to a ``Fragment``.  Packets arriving
    within the first ``START_LIMIT`` seconds of the trace are discarded to
    avoid capturing transient warm-up traffic.

    Attributes:
        TIME_FRAME_LEN: Window duration in seconds (default 60).
        START_LIMIT: Seconds of leading traffic to discard (default 30).
        time_frames: Ordered list of ``(epoch_timestamp, byte_count)`` tuples
            belonging to this window.
    """

    TIME_FRAME_LEN = 60  # seconds
    START_LIMIT = 30  # seconds

    def __init__(self) -> None:
        """Initialise an empty time frame."""
        self.time_frames: list[tuple[float, int]] = []


class TimeSeries:
    """Per-user aggregation of download and upload ``Fragment`` lists.

    A single ``TimeSeries`` object is produced for each user (IP address) by
    ``TimeSeriesProcessor.process_pcap``.  It contains one ``Fragment`` per
    ``TIME_FRAME_LEN``-second window found in the PCAP.

    Attributes:
        download_time_frames: Raw per-window observations for inbound traffic.
        upload_time_frames: Raw per-window observations for outbound traffic.
        download_fragments: Binned ``Fragment`` objects for inbound traffic.
        upload_fragments: Binned ``Fragment`` objects for outbound traffic.
        total_bwd_packets: Total inbound (download) packet count.
        total_fwd_packets: Total outbound (upload) packet count.
        total_packets: Sum of forward and backward packet counts.
    """

    def __init__(self) -> None:
        """Initialise an empty ``TimeSeries``."""
        self.download_time_frames: list[TimeFrame] = []
        self.upload_time_frames: list[TimeFrame] = []

        self.download_fragments: list[Fragment] = []
        self.upload_fragments: list[Fragment] = []

        self.total_bwd_packets: int = 0
        self.total_fwd_packets: int = 0
        self.total_packets: int = 0


class Fragment:
    """A fixed-length array representing traffic in 100 ms bins.

    One ``Fragment`` covers exactly one ``TimeFrame`` (``TIME_FRAME_LEN``
    seconds) discretised into ``FRAGMENT_LEN`` ms intervals.  With the default
    values this produces a 600-element array (60 s / 0.1 s).

    Attributes:
        FRAGMENT_LEN: Bin width in milliseconds (default 100 ms).
        container: NumPy array of byte counts, one per bin.
    """

    FRAGMENT_LEN = 100  # ms

    def __init__(self) -> None:
        """Initialise a zero-filled fragment array."""
        self.container: np.ndarray = np.zeros(
            int((TimeFrame.TIME_FRAME_LEN * 1000) // self.FRAGMENT_LEN)
        )

    @classmethod
    def from_list(cls, cont: list) -> Fragment:
        """Construct a ``Fragment`` from a plain Python list.

        Args:
            cont: List of numeric byte-count values, one per bin.

        Returns:
            A new ``Fragment`` whose ``container`` wraps *cont* as a NumPy array.
        """
        fragment = cls()
        fragment.container = np.array(cont)
        return fragment

    def __add__(self, other: Fragment) -> Fragment:
        """Concatenate two fragments into a new (longer) fragment.

        This is used to join back-to-back time windows into a single array.
        The original operands are **not** modified.

        Args:
            other: The fragment to append after ``self``.

        Returns:
            A new ``Fragment`` whose ``container`` is the concatenation of
            ``self.container`` and ``other.container``.
        """
        result = Fragment.__new__(Fragment)
        result.container = np.concatenate((self.container, other.container))
        return result


class TimeSeriesProcessor:
    """Orchestrates the conversion of raw PCAP files to ``TimeSeries`` objects.

    For each user folder the processor:

    1. Runs ``tshark`` to extract per-packet ``(timestamp, length, dst_ip)``.
    2. Classifies packets as download or upload based on destination IP prefix.
    3. Splits the packet stream into ``TimeFrame`` windows.
    4. Bins each window into a ``Fragment`` (100 ms bins).
    5. Pickles the resulting ``TimeSeries`` to disk.

    Args:
        network_prefixes: IP prefixes that identify download (inbound) traffic.
            Any packet whose destination IP starts with one of these strings is
            classified as download; all others are upload.  Defaults to
            :data:`_DEFAULT_NETWORK_PREFIXES` (UCSB campus addresses).
    """

    def __init__(self, network_prefixes: list[str] | None = None) -> None:
        self.network_prefixes: list[str] = (
            network_prefixes
            if network_prefixes is not None
            else _DEFAULT_NETWORK_PREFIXES
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load_pcap(self, folder: str, pcap_dir: str, output_dir: str) -> list:
        """Process a single user folder and save the ``TimeSeries`` to disk.

        Looks for ``<pcap_dir>/<folder>/merged.pcap`` and writes the result to
        ``<output_dir>/<folder>/timeseries.pkl``.  Skips processing if the
        output file already exists.

        Args:
            folder: Sub-directory name (typically the user's IP address string).
            pcap_dir: Root directory containing per-user PCAP sub-directories.
            output_dir: Root directory where per-user time-series pickles are written.

        Returns:
            An empty list (return value is intentionally unused; errors are
            logged to ``errorsInTimeSeries.txt``).
        """
        try:
            merged_pcap = os.path.join(pcap_dir, folder, "merged.pcap")
            out_dir = os.path.join(output_dir, folder)
            os.makedirs(out_dir, exist_ok=True)
            output_file = os.path.join(out_dir, "timeseries.pkl")

            if os.path.exists(output_file):
                print(f"Time series already exists for {folder}")
                return []

            if os.path.exists(merged_pcap):
                time_series = self.process_pcap(merged_pcap)
                if time_series:
                    self._save_to_pkl(output_file, time_series)

            return []

        except Exception as e:
            print(f"Error: {e}")
            print(f"Failed to process {folder}/ {pcap_dir}")
            self._log_error(f"Failed to process {folder}/ {pcap_dir}", e)
            return []

    def process_pcap(self, merged_pcap: str) -> TimeSeries | None:
        """Parse a merged PCAP file and produce a ``TimeSeries``.

        Uses ``tshark`` to extract ``(frame.time_epoch, ip.len, ip.dst)`` for
        every IP packet, classifies each as download or upload, splits by time
        window, and bins into ``Fragment`` arrays.

        Args:
            merged_pcap: Absolute path to the ``merged.pcap`` file.

        Returns:
            A fully populated ``TimeSeries``, or ``None`` if an error occurs.
        """
        try:
            tshark_cmd = [
                "tshark",
                "-r",
                merged_pcap,
                "-T",
                "fields",
                "-e",
                "frame.time_epoch",
                "-e",
                "ip.len",
                "-e",
                "ip.dst",
            ]
            result = subprocess.run(tshark_cmd, capture_output=True, text=True)

            time_series = TimeSeries()
            download_series: list[tuple[float, int]] = []
            upload_series: list[tuple[float, int]] = []
            total_fwd_packets = 0
            total_bwd_packets = 0
            start_time = 0.0

            packets = result.stdout.splitlines()
            if packets:
                timestamp, _, _ = packets[0].split("\t")
                start_time = float(timestamp)

            for line in packets:
                try:
                    timestamp, length, dst_ip = line.split("\t")
                    if any(dst_ip.startswith(p) for p in self.network_prefixes):
                        download_series.append((float(timestamp), int(length)))
                        total_bwd_packets += 1
                    else:
                        upload_series.append((float(timestamp), int(length)))
                        total_fwd_packets += 1
                except ValueError:
                    continue  # skip malformed tshark output lines

            with mp.Pool(processes=mp.cpu_count()) as pool:
                time_frames = pool.starmap(
                    self.split_time_frames,
                    [(download_series, start_time), (upload_series, start_time)],
                )

            time_series.download_time_frames = time_frames[0]
            time_series.upload_time_frames = time_frames[1]

            time_series.download_fragments = self.process_time_frame(
                time_series.download_time_frames
            )
            time_series.upload_fragments = self.process_time_frame(
                time_series.upload_time_frames
            )

            time_series.total_fwd_packets = total_fwd_packets
            time_series.total_bwd_packets = total_bwd_packets
            time_series.total_packets = total_fwd_packets + total_bwd_packets

            return time_series

        except Exception as e:
            print(f"Error: {e}")
            print(f"Failed to process {merged_pcap}")
            self._log_error(f"Failed to process {merged_pcap}", e)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def process_time_frame(self, time_frames: list[TimeFrame]) -> list[Fragment]:
        """Convert a list of ``TimeFrame`` windows to ``Fragment`` objects in parallel.

        Args:
            time_frames: The list of raw time-window observations to bin.

        Returns:
            A list of ``Fragment`` objects, one per input ``TimeFrame``, in the
            same order as *time_frames*.
        """
        with mp.Pool(processes=mp.cpu_count()) as pool:
            return pool.map(self.convert_time_frame, time_frames)

    def convert_time_frame(self, time_frame: TimeFrame) -> Fragment:
        """Bin a single ``TimeFrame`` into a ``Fragment``.

        Each ``(timestamp, bytes)`` observation is placed into the appropriate
        100 ms bin relative to the first observation in the window.

        Args:
            time_frame: A single ``TimeFrame`` containing ordered observations.

        Returns:
            A ``Fragment`` with byte counts accumulated per 100 ms bin.
        """
        fragment = Fragment()
        if not time_frame.time_frames:
            return fragment
        start_time = time_frame.time_frames[0][0]
        for timestamp, nbytes in time_frame.time_frames:
            idx = int((timestamp - start_time) * 1000 // Fragment.FRAGMENT_LEN)
            fragment.container[idx] += nbytes
        assert sum(fragment.container) == sum(t[1] for t in time_frame.time_frames)
        return fragment

    def split_time_frames(
        self,
        time_series: list[tuple[float, int]],
        start_time: float,
    ) -> list[TimeFrame]:
        """Partition a flat packet stream into fixed-length ``TimeFrame`` windows.

        Observations within the first ``TimeFrame.START_LIMIT`` seconds of the
        trace are discarded.  Each subsequent window spans exactly
        ``TimeFrame.TIME_FRAME_LEN`` seconds.

        Args:
            time_series: Ordered list of ``(epoch_timestamp, byte_count)`` tuples
                for a single direction (download or upload).
            start_time: Epoch timestamp of the very first packet in the PCAP,
                used to compute relative offsets.

        Returns:
            A list of ``TimeFrame`` objects in chronological order.
        """
        time_frames: list[TimeFrame] = []
        if not time_series:
            return time_frames

        time_frame = TimeFrame()
        counter = 1
        limit = TimeFrame.TIME_FRAME_LEN
        curr_limit = counter * limit

        for timestamp, nbytes in time_series:
            if timestamp - start_time < TimeFrame.START_LIMIT:
                continue
            if timestamp - start_time < curr_limit:
                time_frame.time_frames.append((timestamp, nbytes))
            else:
                time_frames.append(time_frame)
                time_frame = TimeFrame()
                counter += 1
                curr_limit = counter * limit
                time_frame.time_frames.append((timestamp, nbytes))

        return time_frames

    def _save_to_pkl(self, output_file: str, time_series: TimeSeries) -> bool:
        """Pickle a ``TimeSeries`` object to *output_file*.

        Args:
            output_file: Destination path for the pickle file.
            time_series: The ``TimeSeries`` to serialise.

        Returns:
            ``True`` on success, ``False`` if an exception was raised.
        """
        try:
            with open(output_file, "wb") as f:
                pickle.dump(time_series, f)
            return True
        except Exception as e:
            print(f"Error: {e}")
            print(f"Failed to save the time series to PKL file for {output_file}")
            self._log_error(
                f"Failed to save the time series to PKL file for {output_file}", e
            )
            return False

    @staticmethod
    def _log_error(message: str, error: Exception) -> None:
        """Append an error record to ``errorsInTimeSeries.txt``.

        Args:
            message: Human-readable description of what failed.
            error: The caught exception.
        """
        with open("errorsInTimeSeries.txt", "a") as f:
            f.write(f"{message}\n")
            f.write(f"Error: {error}\n")
            f.write("--------------------------------------\n")
