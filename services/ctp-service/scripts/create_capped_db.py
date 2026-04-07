#!/usr/bin/env python3
"""
create_capped_db.py — Build a threshold-capped copy of the CTP corpus database.

For every row in ``ctp_nodes`` the script applies:

    capped_bin = min(original_bin, threshold_bytes_per_bin)

to both ``upload_timeseries`` and ``download_timeseries``, then recomputes
all statistical descriptors (intensity, burstiness, temporal correlation) from
the capped data.  The ``structure`` descriptor is carried over as-is, except
for ``upload_download_ratio`` which is recalculated from the capped byte totals.

The resulting database is named ``<src_db>_<threshold>mbps``
(e.g. ``ctp_corpus_6mbps`` for a 6 Mbps cap) and is created automatically.
The ``datasets`` metadata table is copied verbatim.

Usage
-----
    python create_capped_db.py --src-url postgresql://user:pass@host:5432/ctp_corpus \\
                                --threshold-mbps 6.0 \\
                                [--batch-size 2000] [--workers 4]

The script can be run from inside the ctp-service container or from any host
that has network access to PostgreSQL and the ctp-service Python environment::

    docker exec ctp-service python /app/scripts/create_capped_db.py \\
        --src-url "$CTP_DATABASE_URL" --threshold-mbps 6.0
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import numpy as np
import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values

# Allow running from inside or outside the container.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from app.operations.metrics import (
    compute_burstiness,
    compute_intensity,
    compute_temporal_correlation,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Default bin width — must match the value used during extraction.
_DEFAULT_BIN_SEC: float = 0.1


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _admin_url(src_url: str) -> str:
    """Replace the database name in *src_url* with ``postgres`` for admin ops."""
    p = urlparse(src_url)
    return urlunparse(p._replace(path="/postgres"))


def _replace_db(src_url: str, new_db: str) -> str:
    """Return *src_url* with the database component replaced by *new_db*."""
    p = urlparse(src_url)
    return urlunparse(p._replace(path=f"/{new_db}"))


def _dst_db_name(src_url: str, threshold_mbps: float) -> str:
    """Derive destination database name from source URL and threshold."""
    src_db = urlparse(src_url).path.lstrip("/")
    threshold_str = f"{threshold_mbps:g}".replace(".", "_")
    return f"{src_db}_{threshold_str}mbps"


def _create_database(src_url: str, dst_db: str) -> None:
    """Create *dst_db* if it does not already exist."""
    admin_url = _admin_url(src_url)
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dst_db,))
        if cur.fetchone():
            log.info("Database '%s' already exists — skipping creation.", dst_db)
        else:
            cur.execute(f'CREATE DATABASE "{dst_db}"')
            log.info("Created database '%s'.", dst_db)
    conn.close()


def _apply_schema(dst_url: str, schema_path: Path) -> None:
    """Apply schema DDL to the destination database."""
    ddl = schema_path.read_text()
    conn = psycopg2.connect(dst_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.close()
    log.info("Schema applied to '%s'.", urlparse(dst_url).path.lstrip("/"))


def _copy_datasets(src_url: str, dst_url: str) -> None:
    """Copy the ``datasets`` table verbatim."""
    src = psycopg2.connect(src_url)
    dst = psycopg2.connect(dst_url)
    with src.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM datasets")
        rows = cur.fetchall()
    if not rows:
        src.close()
        dst.close()
        return
    cols = list(rows[0].keys())
    col_list = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    with dst.cursor() as cur:
        execute_values(
            cur,
            f"INSERT INTO datasets ({col_list}) VALUES %s ON CONFLICT DO NOTHING",
            [tuple(r[c] for c in cols) for r in rows],
        )
    dst.commit()
    src.close()
    dst.close()
    log.info("Copied %d dataset(s).", len(rows))


# ---------------------------------------------------------------------------
# Row-level capping and descriptor recomputation
# ---------------------------------------------------------------------------


def _threshold_bytes(threshold_mbps: float, bin_sec: float = _DEFAULT_BIN_SEC) -> float:
    """Convert Mbps threshold to bytes-per-bin."""
    return threshold_mbps * 1_000_000 / 8.0 * bin_sec


def _process_row(
    row: dict[str, Any],
    threshold_bytes: float,
    bin_sec: float,
) -> dict[str, Any]:
    """Cap a single CTP node row and recompute its descriptors.

    Structure fields that depend on contributor IPs (contributor_count,
    unique_source_ips, unique_dest_ips, prefix_diversity) are carried over
    unchanged.  Only upload_download_ratio is recalculated from the capped
    byte totals.

    Returns a dict ready for insertion into ``ctp_nodes``.
    """
    dl_ts = np.asarray(row["download_timeseries"], dtype=np.float64)
    ul_ts = np.asarray(row["upload_timeseries"], dtype=np.float64)

    dl_capped = np.minimum(dl_ts, threshold_bytes)
    ul_capped = np.minimum(ul_ts, threshold_bytes)
    combined = dl_capped + ul_capped

    # Recompute intensity from combined capped timeseries
    intensity = compute_intensity(combined, bin_sec)
    intensity.download_mean_mbps = compute_intensity(dl_capped, bin_sec).mean_mbps
    intensity.upload_mean_mbps = compute_intensity(ul_capped, bin_sec).mean_mbps

    burstiness = compute_burstiness(combined)
    correlation = compute_temporal_correlation(combined)

    # Update only upload_download_ratio from capped totals; keep the rest
    struct_d = (
        row["structure"]
        if isinstance(row["structure"], dict)
        else json.loads(row["structure"])
    )
    dl_bytes = float(np.sum(dl_capped))
    ul_bytes = float(np.sum(ul_capped))
    new_ratio = ul_bytes / dl_bytes if dl_bytes > 0 else -1.0
    struct_d = {**struct_d, "upload_download_ratio": new_ratio}

    return {
        "ctp_id": row["ctp_id"],
        "dataset_name": row["dataset_name"],
        "subnet": str(row["subnet"]),
        "window_index": row["window_index"],
        "extracted_from": row.get("extracted_from"),
        "start_time": row.get("start_time"),
        "duration_seconds": row.get("duration_seconds", 30),
        "upload_timeseries": ul_capped.tolist(),
        "download_timeseries": dl_capped.tolist(),
        "contributor_count": struct_d.get("contributor_count", 0),
        "intensity": json.dumps(
            {
                "mean_pps": intensity.mean_pps,
                "mean_bps": intensity.mean_bps,
                "mean_mbps": intensity.mean_mbps,
                "peak_pps": intensity.peak_pps,
                "peak_bps": intensity.peak_bps,
                "download_mean_mbps": intensity.download_mean_mbps,
                "upload_mean_mbps": intensity.upload_mean_mbps,
            }
        ),
        "burstiness": json.dumps(
            {
                "peak_to_mean_ratio": burstiness.peak_to_mean_ratio,
                "coefficient_of_variation": burstiness.coefficient_of_variation,
                "percentile_95_to_mean": burstiness.percentile_95_to_mean,
                "on_periods": burstiness.on_periods,
                "off_periods": burstiness.off_periods,
            }
        ),
        "temporal_correlation": json.dumps(
            {
                "lag_1": correlation.lag_1,
                "lag_5": correlation.lag_5,
                "lag_10": correlation.lag_10,
                "lag_60": correlation.lag_60,
            }
        ),
        "structure": json.dumps(struct_d),
        "is_transformed": row.get("is_transformed", False),
        "throughput_threshold_mbps": row.get("throughput_threshold_mbps"),
        "download_pcap": row.get("download_pcap"),
        "upload_pcap": row.get("upload_pcap"),
        "is_merged": row.get("is_merged", False),
        "merge_start_index": row.get("merge_start_index"),
        "merge_end_index": row.get("merge_end_index"),
    }


_INSERT_SQL = """
INSERT INTO ctp_nodes (
    ctp_id, dataset_name, subnet, window_index,
    extracted_from, start_time, duration_seconds,
    upload_timeseries, download_timeseries,
    contributor_count,
    intensity, burstiness, temporal_correlation, structure,
    is_transformed, throughput_threshold_mbps,
    download_pcap, upload_pcap,
    is_merged, merge_start_index, merge_end_index
) VALUES %s
ON CONFLICT (ctp_id) DO NOTHING
"""

_INSERT_COLS = [
    "ctp_id",
    "dataset_name",
    "subnet",
    "window_index",
    "extracted_from",
    "start_time",
    "duration_seconds",
    "upload_timeseries",
    "download_timeseries",
    "contributor_count",
    "intensity",
    "burstiness",
    "temporal_correlation",
    "structure",
    "is_transformed",
    "throughput_threshold_mbps",
    "download_pcap",
    "upload_pcap",
    "is_merged",
    "merge_start_index",
    "merge_end_index",
]


# ---------------------------------------------------------------------------
# Main copy loop
# ---------------------------------------------------------------------------


def run(
    src_url: str,
    threshold_mbps: float,
    batch_size: int = 2000,
    bin_sec: float = _DEFAULT_BIN_SEC,
) -> None:
    dst_db = _dst_db_name(src_url, threshold_mbps)
    dst_url = _replace_db(src_url, dst_db)
    thresh_bytes = _threshold_bytes(threshold_mbps, bin_sec)

    log.info(
        "Source: %s  →  Destination: %s  (threshold %.4g bytes/bin = %.4g Mbps)",
        urlparse(src_url).path.lstrip("/"),
        dst_db,
        thresh_bytes,
        threshold_mbps,
    )

    # --- Create destination DB and apply schema ---
    _create_database(src_url, dst_db)
    schema_path = (
        Path(__file__).resolve().parent.parent / "app" / "database" / "schema.sql"
    )
    _apply_schema(dst_url, schema_path)

    # --- Copy datasets table ---
    _copy_datasets(src_url, dst_url)

    # --- Count source rows ---
    src_conn = psycopg2.connect(src_url)
    with src_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ctp_nodes")
        total = cur.fetchone()[0]
    log.info("Processing %d rows in batches of %d …", total, batch_size)

    dst_conn = psycopg2.connect(dst_url)
    processed = 0
    t_start = time.monotonic()

    # Use a server-side named cursor to avoid loading all rows into memory.
    with src_conn.cursor(
        name="ctp_cursor", cursor_factory=psycopg2.extras.RealDictCursor
    ) as src_cur:
        src_cur.itersize = batch_size
        src_cur.execute("SELECT * FROM ctp_nodes ORDER BY ctp_id")

        batch: list[dict] = []
        for row in src_cur:
            batch.append(_process_row(dict(row), thresh_bytes, bin_sec))
            if len(batch) >= batch_size:
                _flush(dst_conn, batch)
                processed += len(batch)
                batch = []
                elapsed = time.monotonic() - t_start
                rate = processed / elapsed
                remaining = (total - processed) / rate if rate > 0 else 0
                log.info(
                    "  %d / %d  (%.0f rows/s, ~%.0fs remaining)",
                    processed,
                    total,
                    rate,
                    remaining,
                )

        if batch:
            _flush(dst_conn, batch)
            processed += len(batch)

    src_conn.close()
    dst_conn.close()

    elapsed = time.monotonic() - t_start
    log.info(
        "Done. %d rows written to '%s' in %.1fs.",
        processed,
        dst_db,
        elapsed,
    )
    log.info("To use the capped DB, set: CTP_DATABASE_URL=%s", dst_url)


def _flush(conn: psycopg2.extensions.connection, rows: list[dict]) -> None:
    """Write a batch of processed rows to the destination DB."""
    with conn.cursor() as cur:
        execute_values(
            cur,
            _INSERT_SQL,
            [tuple(r[c] for c in _INSERT_COLS) for r in rows],
            page_size=500,
        )
    conn.commit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create a threshold-capped copy of the CTP corpus database.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--src-url",
        default=os.environ.get("CTP_DATABASE_URL"),
        help="Source PostgreSQL URL (defaults to $CTP_DATABASE_URL).",
    )
    p.add_argument(
        "--threshold-mbps",
        type=float,
        required=True,
        help="Throughput cap in Mbps.  Each timeseries bin is clamped to this rate.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Rows processed per batch.",
    )
    p.add_argument(
        "--bin-sec",
        type=float,
        default=_DEFAULT_BIN_SEC,
        help="Bin width in seconds (must match the value used during extraction).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if not args.src_url:
        sys.exit("Error: --src-url is required (or set $CTP_DATABASE_URL).")
    run(
        src_url=args.src_url,
        threshold_mbps=args.threshold_mbps,
        batch_size=args.batch_size,
        bin_sec=args.bin_sec,
    )
