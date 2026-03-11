"""
pipeline.py — CTP pipeline entry point.

Orchestrates the full pipeline from raw PCAP files to post-processed subnet
trees ready for profile selection and CTP generation.

Pipeline stages
~~~~~~~~~~~~~~~
1. **pcap → timeseries** (:func:`run_timeseries_stage`)

   Reads every user folder in *pcap_dir*, runs ``tshark`` to extract packet
   metadata, and saves a ``TimeSeries`` pickle per user into *ts_dir*.

2. **timeseries → trees** (:func:`run_tree_stage`)

   Loads ``TimeSeries`` pickles, constructs a hierarchical ``TreeNode`` tree for
   each time slice, and writes raw tree JSON files to *tree_dir*.

3. **post-process trees** (:func:`run_post_process_stage`)

   Reloads the raw trees, recomputes median statistics, and re-saves the
   updated trees to *processed_tree_dir*.

Any stage can be skipped with the corresponding ``--skip-*`` flag when its
output already exists on disk from a previous run.

Usage
~~~~~
.. code-block:: shell

    python pipeline.py \\
        --pcap-dir /data/pcaps \\
        --ts-dir /data/timeseries \\
        --tree-dir /data/trees \\
        --mask 169.231 \\
        --time-limit 15 \\
        --network-prefixes 128.111 169.231 192.150.216

    # Skip Stage 1 if timeseries pickles already exist:
    python pipeline.py \\
        --pcap-dir /data/pcaps \\
        --ts-dir /data/timeseries \\
        --tree-dir /data/trees \\
        --skip-timeseries
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import os

from time_series_modules import TimeSeriesProcessor
from trees import (
    construct_trees,
    extract_time_series,
    filter_users,
    post_process_trees,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------


def run_timeseries_stage(
    pcap_dir: str,
    ts_dir: str,
    network_prefixes: list[str] | None,
    workers: int,
) -> None:
    """Stage 1 — convert raw PCAPs to ``TimeSeries`` pickles.

    Discovers all user folders under *pcap_dir* and processes them in parallel
    using :class:`~time_series_modules.TimeSeriesProcessor`.  Each folder is
    expected to contain a ``merged.pcap`` file.  Output pickles are written to
    ``<ts_dir>/<folder>/timeseries.pkl``.

    Args:
        pcap_dir: Root directory containing one sub-directory per user PCAP.
        ts_dir: Destination root directory for per-user ``timeseries.pkl`` files.
        network_prefixes: IP prefixes that identify download (inbound) traffic.
            ``None`` uses the default UCSB campus prefixes.
        workers: Number of parallel worker processes.
    """
    logger.info("=== Stage 1: pcap -> timeseries ===")
    processor = TimeSeriesProcessor(network_prefixes=network_prefixes)
    folders = [
        f for f in os.listdir(pcap_dir) if os.path.isdir(os.path.join(pcap_dir, f))
    ]
    args = [(folder, pcap_dir, ts_dir) for folder in folders]
    with mp.Pool(processes=workers) as pool:
        pool.starmap(processor.load_pcap, args)
    logger.info("Stage 1 complete.")


def run_tree_stage(
    ts_dir: str,
    tree_dir: str,
    mask: str,
    time_limit: int,
    workers: int,
) -> None:
    """Stage 2 — build subnet trees from ``TimeSeries`` pickles.

    Filters users by *mask*, loads all ``TimeSeries`` pickles into memory, then
    constructs one ``TreeNode`` tree per time slice in parallel.  Raw trees are
    written to ``<tree_dir>/tree_nodes_<t>_min.json``.

    Args:
        ts_dir: Directory containing per-user ``timeseries.pkl`` sub-directories.
        tree_dir: Destination directory for the raw tree JSON files.
        mask: IP prefix filter passed to :func:`~trees.filter_users`.
            Pass ``''`` to include all users.
        time_limit: Number of 60-second time slices to construct trees for.
        workers: Number of parallel worker processes.
    """
    logger.info("=== Stage 2: timeseries -> trees ===")
    user_ips = filter_users(mask, ts_dir)
    time_series_dict = extract_time_series(user_ips, ts_dir)
    os.makedirs(tree_dir, exist_ok=True)
    args = [(user_ips, time_series_dict, tree_dir, t) for t in range(time_limit)]
    with mp.Pool(processes=workers) as pool:
        pool.starmap(construct_trees, args)
    logger.info("Stage 2 complete.")


def run_post_process_stage(
    raw_tree_dir: str,
    processed_tree_dir: str,
    time_limit: int,
) -> None:
    """Stage 3 — recompute medians on loaded trees and re-save.

    Reads each ``tree_nodes_<t>_min.json`` from *raw_tree_dir*, traverses the
    tree to recompute :meth:`~tree_node.TreeNode.compute_median` on every node,
    and writes the updated tree to *processed_tree_dir*.

    Args:
        raw_tree_dir: Directory containing raw ``tree_nodes_<t>_min.json`` files.
        processed_tree_dir: Destination directory for post-processed
            ``tree_nodes_<t>.json`` files.
        time_limit: Number of time slices to process.
    """
    logger.info("=== Stage 3: post-process trees ===")
    post_process_trees(raw_tree_dir, processed_tree_dir, time_limit)
    logger.info("Stage 3 complete.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse command-line arguments and run the requested pipeline stages."""
    parser = argparse.ArgumentParser(
        description="Run the CTP pipeline (pcap → timeseries → trees).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pcap-dir",
        required=True,
        help="Root directory containing per-user merged PCAP sub-directories.",
    )
    parser.add_argument(
        "--ts-dir",
        required=True,
        help="Directory for per-user timeseries.pkl output files.",
    )
    parser.add_argument(
        "--tree-dir",
        required=True,
        help="Directory for raw per-time-slice tree JSON output.",
    )
    parser.add_argument(
        "--processed-tree-dir",
        default=None,
        help="Directory for post-processed trees.  Defaults to <tree-dir>_processed.",
    )
    parser.add_argument(
        "--mask",
        default="",
        help="IP prefix used to filter user directories, e.g. '169.231'.",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=15,
        help="Number of 60-second time slices to process.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=mp.cpu_count(),
        help="Number of parallel worker processes.",
    )
    parser.add_argument(
        "--network-prefixes",
        nargs="*",
        default=None,
        help=(
            "Space-separated IP prefixes that identify download traffic. "
            "Defaults to UCSB campus prefixes when omitted."
        ),
    )
    parser.add_argument(
        "--skip-timeseries",
        action="store_true",
        help="Skip Stage 1 (pcap → timeseries).  Requires timeseries pickles to exist.",
    )
    parser.add_argument(
        "--skip-trees",
        action="store_true",
        help="Skip Stage 2 (timeseries → trees).  Requires raw tree JSON files to exist.",
    )
    parser.add_argument(
        "--skip-post-process",
        action="store_true",
        help="Skip Stage 3 (median recomputation).",
    )
    args = parser.parse_args()

    if not args.skip_timeseries:
        run_timeseries_stage(
            args.pcap_dir, args.ts_dir, args.network_prefixes, args.workers
        )

    if not args.skip_trees:
        run_tree_stage(
            args.ts_dir, args.tree_dir, args.mask, args.time_limit, args.workers
        )

    if not args.skip_post_process:
        processed_dir = args.processed_tree_dir or f"{args.tree_dir}_processed"
        run_post_process_stage(args.tree_dir, processed_dir, args.time_limit)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
