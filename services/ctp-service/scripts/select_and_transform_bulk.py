#!/usr/bin/env python3
"""
select_and_transform_bulk.py — Stratified selection + bulk transform of 1000 CTPs.

Selection strategy
------------------
Source: ``ctp_corpus_6mbps`` (the 6 Mbps capped copy).

Diversity axes:
  * **Throughput band** (download mean Mbps): [0-1], [1-2], [2-3], [3-4], [4-5], [5-6]
  * **Subnet level**: leaf (/32), small aggregate (/24–/31), large aggregate (/16–/23)
  * **Burstiness tier** (PMR): low (<2), medium (2–5), high (>5)

Already-transformed CTPs (present in the original DB) are excluded automatically.

Run this script from the HOST (not inside the container) — it uses the ``requests``
library for connection-pooled HTTP to avoid ephemeral port exhaustion.

Usage
-----
    python select_and_transform_bulk.py \\
        [--capped-db-url  postgresql://user:pass@localhost:5432/ctp_corpus_6mbps] \\
        [--src-db-url     postgresql://user:pass@localhost:5432/ctp_corpus] \\
        [--api-url        http://localhost:8001] \\
        [--output-dir     /mnt/md0/global_ctp/transformed] \\
        [--users-root     /mnt/md0/global_ctp/per_user/users] \\
        [--total          1000] \\
        [--workers        2]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Diversity configuration
# ---------------------------------------------------------------------------

THROUGHPUT_BANDS = [
    (0.0, 1.0),
    (1.0, 2.0),
    (2.0, 3.0),
    (3.0, 4.0),
    (4.0, 5.0),
    (5.0, 6.0),
]
MIN_PER_BAND = 10

SUBNET_GROUPS = {
    "leaf": (32, 32),
    "small": (24, 31),
    "large": (16, 23),
}

PMR_TIERS = {
    "low": (0.0, 2.0),
    "medium": (2.0, 5.0),
    "high": (5.0, 9999.0),
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CTPCandidate:
    ctp_id: str
    dl_mean_mbps: float
    pmr: float
    prefix_len: int
    band: str
    subnet_group: str
    pmr_tier: str


@dataclass
class TransformResult:
    ctp_id: str
    success: bool
    transformed_id: Optional[str] = None
    download_pcap: Optional[str] = None
    upload_pcap: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _band_label(lo: float, hi: float) -> str:
    return f"{lo:.0f}-{hi:.0f}Mbps"


def _subnet_group(prefix_len: int) -> str:
    for name, (lo, hi) in SUBNET_GROUPS.items():
        if lo <= prefix_len <= hi:
            return name
    return "other"


def _pmr_tier(pmr: float) -> str:
    for name, (lo, hi) in PMR_TIERS.items():
        if lo <= pmr < hi:
            return name
    return "high"


def _make_session(api_url: str, timeout: int) -> requests.Session:
    """Build a requests Session with connection pooling and retry logic."""
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def fetch_already_transformed(src_conn) -> Set[str]:
    """Return the set of original ctp_ids that already have a transformed version."""
    with src_conn.cursor() as cur:
        # Transformed IDs encode the original: ctp-transform-<original_id>-<threshold>mbps
        cur.execute("SELECT ctp_id FROM ctp_nodes WHERE is_transformed = TRUE")
        rows = cur.fetchall()
    # Extract the original ctp_id embedded in the transformed id
    already: Set[str] = set()
    for (tid,) in rows:
        # Format: ctp-transform-<original_ctp_id>-<N>mbps
        if tid.startswith("ctp-transform-"):
            inner = tid[len("ctp-transform-") :]
            # Strip trailing -<N>mbps
            parts = inner.rsplit("-", 1)
            if len(parts) == 2 and parts[1].endswith("mbps"):
                already.add(parts[0])
    return already


def fetch_candidates(
    conn, band_lo: float, band_hi: float, exclude: Set[str]
) -> List[CTPCandidate]:
    sql = """
        SELECT
            ctp_id,
            (intensity->>'download_mean_mbps')::FLOAT8  AS dl_mean,
            (burstiness->>'peak_to_mean_ratio')::FLOAT8 AS pmr,
            masklen(subnet)                              AS prefix_len
        FROM ctp_nodes
        WHERE (intensity->>'download_mean_mbps')::FLOAT8 > %s
          AND (intensity->>'download_mean_mbps')::FLOAT8 <= %s
    """
    band = _band_label(band_lo, band_hi)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (band_lo, band_hi))
        rows = cur.fetchall()

    candidates = []
    for r in rows:
        if r["ctp_id"] in exclude:
            continue
        pmr = r["pmr"] or 0.0
        candidates.append(
            CTPCandidate(
                ctp_id=r["ctp_id"],
                dl_mean_mbps=r["dl_mean"],
                pmr=pmr,
                prefix_len=r["prefix_len"],
                band=band,
                subnet_group=_subnet_group(r["prefix_len"]),
                pmr_tier=_pmr_tier(pmr),
            )
        )
    return candidates


def stratified_sample(
    candidates: List[CTPCandidate], target: int
) -> List[CTPCandidate]:
    from collections import defaultdict

    cells: dict[str, List[CTPCandidate]] = defaultdict(list)
    for c in candidates:
        cells[f"{c.subnet_group}_{c.pmr_tier}"].append(c)
    for cell in cells.values():
        random.shuffle(cell)

    iters = {k: iter(v) for k, v in cells.items()}
    selected: List[CTPCandidate] = []
    exhausted: set = set()

    while len(selected) < target and len(exhausted) < len(iters):
        for key, it in iters.items():
            if key in exhausted:
                continue
            try:
                selected.append(next(it))
            except StopIteration:
                exhausted.add(key)
            if len(selected) >= target:
                break
    return selected[:target]


def select_diverse(capped_conn, src_conn, total: int = 1000) -> List[CTPCandidate]:
    already_done = fetch_already_transformed(src_conn)
    log.info("Excluding %d already-transformed CTPs.", len(already_done))

    per_band = total // len(THROUGHPUT_BANDS)
    remainder = total - per_band * len(THROUGHPUT_BANDS)
    all_selected: List[CTPCandidate] = []

    for i, (lo, hi) in enumerate(THROUGHPUT_BANDS):
        band = _band_label(lo, hi)
        target = max(per_band + (1 if i < remainder else 0), MIN_PER_BAND)
        log.info("Band %s — fetching candidates …", band)
        candidates = fetch_candidates(capped_conn, lo, hi, already_done)
        log.info("  %d candidates available, targeting %d", len(candidates), target)
        if not candidates:
            log.warning("  No candidates for band %s.", band)
            continue
        selected = stratified_sample(candidates, min(target, len(candidates)))
        log.info(
            "  Selected %d  (subnets: %s | pmr: %s)",
            len(selected),
            sorted({c.subnet_group for c in selected}),
            sorted({c.pmr_tier for c in selected}),
        )
        all_selected.extend(selected)

    log.info("Total selected: %d", len(all_selected))
    return all_selected


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def transform_one(
    candidate: CTPCandidate,
    session: requests.Session,
    api_url: str,
    output_dir: str,
    users_root: str,
    threshold_mbps: float,
    timeout: int,
) -> TransformResult:
    try:
        resp = session.post(
            f"{api_url.rstrip('/')}/ctps/transform",
            json={
                "ctp_id": candidate.ctp_id,
                "output_dir": output_dir,
                "users_root": users_root,
                "throughput_threshold_mbps": threshold_mbps,
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            body = resp.json()
            return TransformResult(
                ctp_id=candidate.ctp_id,
                success=True,
                transformed_id=body["transformed_ctp_id"],
                download_pcap=body["download_pcap"],
                upload_pcap=body["upload_pcap"],
            )
        return TransformResult(
            ctp_id=candidate.ctp_id,
            success=False,
            error=resp.text[:200],
        )
    except Exception as exc:
        return TransformResult(ctp_id=candidate.ctp_id, success=False, error=str(exc))


def transform_bulk(
    candidates: List[CTPCandidate],
    api_url: str,
    output_dir: str,
    users_root: str,
    workers: int = 2,
    threshold_mbps: float = 6.0,
    timeout: int = 300,
) -> List[TransformResult]:
    # One shared session per worker thread (thread-local via closure)
    sessions = [_make_session(api_url, timeout) for _ in range(workers)]
    total = len(candidates)
    results: List[TransformResult] = []
    done = 0
    t_start = time.monotonic()
    log.info(
        "Transforming %d CTPs with %d workers (timeout %ds) …", total, workers, timeout
    )

    def _work(idx_candidate):
        idx, c = idx_candidate
        sess = sessions[idx % workers]
        return transform_one(
            c, sess, api_url, output_dir, users_root, threshold_mbps, timeout
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_work, (i, c)): c for i, c in enumerate(candidates)}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            done += 1
            elapsed = time.monotonic() - t_start
            rate = done / elapsed
            remaining = (total - done) / rate if rate > 0 else 0
            status = "OK" if result.success else f"FAIL: {(result.error or '')[:80]}"
            log.info(
                "  [%d/%d] %s → %s  (~%.0fs left)",
                done,
                total,
                result.ctp_id,
                status,
                remaining,
            )

    ok = sum(1 for r in results if r.success)
    log.info(
        "Done. %d succeeded, %d failed in %.1fs.",
        ok,
        len(results) - ok,
        time.monotonic() - t_start,
    )
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument(
        "--capped-db-url",
        default="postgresql://snl-agentic:snl%40UCSB.2026@localhost:5432/ctp_corpus_6mbps",
    )
    p.add_argument(
        "--src-db-url",
        default="postgresql://snl-agentic:snl%40UCSB.2026@localhost:5432/ctp_corpus",
    )
    p.add_argument("--api-url", default="http://localhost:8001")
    p.add_argument("--output-dir", default="/mnt/md0/global_ctp/transformed")
    p.add_argument("--users-root", default="/mnt/md0/global_ctp/per_user/users")
    p.add_argument("--total", type=int, default=1000)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument(
        "--timeout", type=int, default=300, help="Per-request timeout in seconds."
    )
    p.add_argument(
        "--results-file",
        default="/mnt/md0/global_ctp/transformed/transform_results.json",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    capped_conn = psycopg2.connect(args.capped_db_url)
    src_conn = psycopg2.connect(args.src_db_url)
    candidates = select_diverse(capped_conn, src_conn, total=args.total)
    capped_conn.close()
    src_conn.close()

    if not candidates:
        sys.exit("No candidates found.")

    results = transform_bulk(
        candidates=candidates,
        api_url=args.api_url,
        output_dir=args.output_dir,
        users_root=args.users_root,
        workers=args.workers,
        timeout=args.timeout,
    )

    summary = [
        {
            "ctp_id": r.ctp_id,
            "success": r.success,
            "transformed_id": r.transformed_id,
            "download_pcap": r.download_pcap,
            "upload_pcap": r.upload_pcap,
            "error": r.error,
        }
        for r in results
    ]
    Path(args.results_file).write_text(json.dumps(summary, indent=2))
    log.info("Results written to %s", args.results_file)


if __name__ == "__main__":
    main()
