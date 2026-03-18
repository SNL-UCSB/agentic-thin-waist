"""
pipeline.py — CTP pipeline CLI entry point.

Orchestrates the full pipeline from raw gateway PCAP files to CTP nodes
stored in PostgreSQL (the full Extract operation), and also supports the
legacy JSON-tree workflow for offline analysis.

Pipeline modes
~~~~~~~~~~~~~~
**Full extract** (``--mode extract``, default)
    Runs the complete six-step pipeline:

    1. Split gateway PCAPs by internal IP → per-user upload/download PCAPs.
    2. Split per-user PCAPs into fixed time windows.
    3. Build byte-count timeseries (IP-header lengths, 100 ms bins).
    4. Construct prefix-hierarchical TreeNode trees (/32 → /16 → /0).
    5. Store every tree node as a CTP row in PostgreSQL.
    6. Return CTP list.

**Legacy JSON trees** (``--mode legacy``)
    Runs the original three-stage pipeline against pre-split per-user PCAPs:

    Stage 1: pcap → timeseries pickles  (``--skip-timeseries`` to skip)
    Stage 2: timeseries → raw JSON trees (``--skip-trees`` to skip)
    Stage 3: recompute medians → processed JSON trees (``--skip-post-process`` to skip)

All runtime paths (pcap input, output directories, database URL, dataset name,
subnets) are provided as CLI arguments; no defaults encode production paths.

Usage — full extract
~~~~~~~~~~~~~~~~~~~~
.. code-block:: shell

    python pipeline.py \\
        --mode extract \\
        --pcap-input /data/gateway-2026-03-04.pcap \\
        --output-dir /data/ctp-working \\
        --dataset-name ucsb-2026-03-04 \\
        --database-url postgresql://user:pass@localhost:5432/ctp_corpus \\
        --workers 8

Usage — legacy JSON trees
~~~~~~~~~~~~~~~~~~~~~~~~~
.. code-block:: shell

    python pipeline.py \\
        --mode legacy \\
        --pcap-dir /data/pcaps \\
        --ts-dir /data/timeseries \\
        --tree-dir /data/trees \\
        --mask 169.231 \\
        --time-limit 15 \\
        --network-prefixes 128.111 169.231 192.150.216
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import os
import sys

from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Full extract pipeline (Steps 1-5)
# ---------------------------------------------------------------------------


def run_extract_pipeline(args: argparse.Namespace) -> None:
    """Run the full PCAP → PostgreSQL extraction pipeline.

    Imports are deferred inside the function so that ``legacy`` mode users
    do not need a database connection.

    Args:
        args: Parsed CLI arguments.
    """
    # Import here to allow the module to load without psycopg2 installed
    from app.config import Settings
    from app.database.postgres import Database
    from app.operations.extract import Extractor

    cfg = Settings(
        database_url=args.database_url,
        workers=args.workers,
        window_duration_sec=args.window_duration_sec,
        burst_interval_ms=args.burst_interval_ms,
        internal_subnets=args.internal_subnets or [],
        gateway_subnet=args.gateway_subnet or "169.231.0.0/16",
    )

    db = Database(database_url=cfg.database_url)
    db.initialize()

    extractor = Extractor(db=db, settings=cfg)
    ctps = extractor.run(
        pcap_input=args.pcap_input,
        output_dir=args.output_dir,
        dataset_name=args.dataset_name,
        workers=args.workers,
    )

    db.close()
    logger.info(
        "Extract complete: %d CTPs stored for dataset '%s'.",
        len(ctps),
        args.dataset_name,
    )


# ---------------------------------------------------------------------------
# Legacy pipeline stages
# ---------------------------------------------------------------------------


def run_timeseries_stage(
    pcap_dir: str,
    ts_dir: str,
    network_prefixes: list[str] | None,
    workers: int,
) -> None:
    """Stage 1 — convert pre-split user PCAPs to ``TimeSeries`` pickles.

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
    from app.time_series_modules import TimeSeriesProcessor

    logger.info("=== Legacy Stage 1: pcap -> timeseries ===")
    processor = TimeSeriesProcessor(network_prefixes=network_prefixes)
    folders = [
        f for f in os.listdir(pcap_dir) if os.path.isdir(os.path.join(pcap_dir, f))
    ]
    args = [(folder, pcap_dir, ts_dir) for folder in folders]
    with mp.Pool(processes=workers) as pool:
        pool.starmap(processor.load_pcap, args)
    logger.info("Legacy Stage 1 complete — %d user(s) processed.", len(folders))


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
    from app.trees import construct_trees, extract_time_series, filter_users

    logger.info("=== Legacy Stage 2: timeseries -> trees ===")
    user_ips = filter_users(mask, ts_dir)
    time_series_dict = extract_time_series(user_ips, ts_dir)
    os.makedirs(tree_dir, exist_ok=True)
    stage_args = [(user_ips, time_series_dict, tree_dir, t) for t in range(time_limit)]
    with mp.Pool(processes=workers) as pool:
        pool.starmap(construct_trees, stage_args)
    logger.info("Legacy Stage 2 complete.")


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
    from app.trees import post_process_trees

    logger.info("=== Legacy Stage 3: post-process trees ===")
    post_process_trees(raw_tree_dir, processed_tree_dir, time_limit)
    logger.info("Legacy Stage 3 complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="CTP Pipeline — from gateway PCAPs to the CTP corpus.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ---- Mode ----
    parser.add_argument(
        "--mode",
        choices=["extract", "legacy"],
        default="extract",
        help=(
            "'extract': full pipeline PCAP → PostgreSQL. "
            "'legacy': original JSON-tree pipeline."
        ),
    )

    # ---- Shared ----
    parser.add_argument(
        "--workers",
        type=int,
        default=mp.cpu_count(),
        help="Number of parallel worker processes.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )

    # ---- Full-extract mode arguments ----
    extract_group = parser.add_argument_group("Extract mode")
    extract_group.add_argument(
        "--pcap-input",
        help="Path to a PCAP file or directory of PCAPs (extract mode).",
    )
    extract_group.add_argument(
        "--output-dir",
        help="Root directory for intermediate per-user files (extract mode).",
    )
    extract_group.add_argument(
        "--dataset-name",
        help="Human-readable dataset label stored in PostgreSQL.",
    )
    extract_group.add_argument(
        "--database-url",
        default="postgresql://ctp_user:ctp_pass@localhost:5432/ctp_corpus",
        help="PostgreSQL connection URL.",
    )
    extract_group.add_argument(
        "--window-duration-sec",
        type=int,
        default=30,
        help="Duration of each time window in seconds.",
    )
    extract_group.add_argument(
        "--burst-interval-ms",
        type=int,
        default=100,
        help="Bin width for timeseries in milliseconds.",
    )
    extract_group.add_argument(
        "--internal-subnets",
        nargs="*",
        default=None,
        help=(
            "IP prefix strings identifying internal hosts.  "
            "Defaults to UCSB campus prefixes when omitted."
        ),
    )
    extract_group.add_argument(
        "--gateway-subnet",
        default=None,
        help="Gateway CIDR subnet, e.g. '169.231.0.0/16'.",
    )

    # ---- Legacy mode arguments ----
    legacy_group = parser.add_argument_group("Legacy mode")
    legacy_group.add_argument(
        "--pcap-dir",
        help="Root directory containing per-user merged PCAP sub-directories.",
    )
    legacy_group.add_argument(
        "--ts-dir",
        help="Directory for per-user timeseries.pkl output files.",
    )
    legacy_group.add_argument(
        "--tree-dir",
        help="Directory for raw per-time-slice tree JSON output.",
    )
    legacy_group.add_argument(
        "--processed-tree-dir",
        default=None,
        help="Directory for post-processed trees.  Defaults to <tree-dir>_processed.",
    )
    legacy_group.add_argument(
        "--mask",
        default="",
        help="IP prefix used to filter user directories, e.g. '169.231'.",
    )
    legacy_group.add_argument(
        "--time-limit",
        type=int,
        default=15,
        help="Number of 60-second time slices to process (legacy mode).",
    )
    legacy_group.add_argument(
        "--network-prefixes",
        nargs="*",
        default=None,
        help=(
            "Space-separated IP prefixes for download traffic classification "
            "(legacy mode).  Defaults to UCSB campus prefixes."
        ),
    )
    legacy_group.add_argument(
        "--skip-timeseries",
        action="store_true",
        help="Skip Stage 1 (pcap → timeseries).",
    )
    legacy_group.add_argument(
        "--skip-trees",
        action="store_true",
        help="Skip Stage 2 (timeseries → trees).",
    )
    legacy_group.add_argument(
        "--skip-post-process",
        action="store_true",
        help="Skip Stage 3 (median recomputation).",
    )

    return parser


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate pipeline mode."""
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(level=args.log_level)

    if args.mode == "extract":
        required = ["pcap_input", "output_dir", "dataset_name"]
        missing = [r for r in required if not getattr(args, r, None)]
        if missing:
            parser.error(
                f"Extract mode requires: {', '.join('--' + r.replace('_', '-') for r in missing)}"
            )
        run_extract_pipeline(args)

    else:  # legacy
        if not args.pcap_dir or not args.ts_dir or not args.tree_dir:
            parser.error("Legacy mode requires --pcap-dir, --ts-dir, and --tree-dir.")

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
