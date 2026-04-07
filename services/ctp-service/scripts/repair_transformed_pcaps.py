"""
repair_transformed_pcaps.py — Clip existing transformed PCAPs to their CTP
window duration and recompute all stored metrics.

Problem
-------
The joincap merge step in transform.py did not clip the output PCAP to the
30-second CTP window.  Per-user window PCAPs sometimes span the full capture
period, so the merged PCAP could be much longer than the CTP timeseries.
build_timeseries_from_window already reads only the first window_sec of
packets so the stored timeseries is *correct* — but the PCAP file on disk
contains extra data that inflates replay duration and makes measured
throughput look wrong.

What this script does
---------------------
For every is_transformed=true row in ctp_corpus:

1.  Clip download_pcap and upload_pcap in-place to duration_seconds.
2.  Rebuild download_timeseries and upload_timeseries from the clipped PCAPs.
3.  Recompute intensity, burstiness, temporal_correlation, structure.
4.  UPDATE the row in ctp_nodes with the new values.

Run inside the ctp-service container:

    docker exec -it ctp-service python /app/scripts/repair_transformed_pcaps.py

Dry-run (report only, no file or DB changes):

    docker exec -it ctp-service python /app/scripts/repair_transformed_pcaps.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import struct
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import psycopg2
import psycopg2.extras

sys.path.insert(0, "/app")
from app.config import get_settings
from app.operations.metrics import compute_all_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fast struct-based PCAP helpers (no scapy overhead)
# ---------------------------------------------------------------------------

_PCAP_GLOBAL_HEADER: bytes = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
_REC_HDR = struct.Struct("<IIII")   # ts_sec, ts_usec, incl_len, orig_len
_IP_HDR  = struct.Struct(">BBHHHBBH4s4s")  # enough to get ip.len (offset 2, H)

ETHERNET_HDR_LEN = 14


def _pcap_records(path: Path):
    """Yield (ts_float, incl_len, orig_len, raw_record_bytes) for each packet."""
    with open(path, "rb") as f:
        hdr = f.read(24)
        if len(hdr) < 24:
            return
        magic = struct.unpack_from("<I", hdr)[0]
        if magic == 0xA1B2C3D4:
            endian = "<"
        elif magic == 0xD4C3B2A1:
            endian = ">"
        else:
            return
        rec_fmt = struct.Struct(endian + "IIII")
        while True:
            rec = f.read(16)
            if len(rec) < 16:
                break
            ts_sec, ts_usec, incl_len, orig_len = rec_fmt.unpack(rec)
            payload = f.read(incl_len)
            yield (ts_sec + ts_usec / 1_000_000, incl_len, orig_len, rec, payload)


def _ip_len_from_payload(payload: bytes) -> Optional[int]:
    """Return the IP total-length field (bytes) or None if not an IP packet."""
    if len(payload) < ETHERNET_HDR_LEN + 20:
        return None
    eth_type = struct.unpack_from(">H", payload, 12)[0]
    if eth_type != 0x0800:   # not IPv4
        return None
    ip_len = struct.unpack_from(">H", payload, ETHERNET_HDR_LEN + 2)[0]
    return ip_len


def pcap_duration(path: Path) -> float:
    """Return the time span of a PCAP in seconds (first to last IP packet)."""
    start: Optional[float] = None
    end: float = 0.0
    for ts, incl_len, orig_len, _, payload in _pcap_records(path):
        if _ip_len_from_payload(payload) is None:
            continue
        if start is None:
            start = ts
        end = ts
    return (end - start) if start is not None else 0.0


def clip_pcap_in_place(path: Path, window_sec: float) -> tuple[float, float]:
    """Clip *path* to the first *window_sec* seconds (in-place).

    Returns (old_duration, new_duration).  If already within window, the file
    is left completely unchanged (not even re-written).
    """
    old_dur = pcap_duration(path)
    if old_dur <= window_sec + 0.5:
        return old_dur, old_dur

    # Collect records within the window
    start: Optional[float] = None
    kept: list[bytes] = []
    for ts, incl_len, orig_len, rec_hdr, payload in _pcap_records(path):
        if _ip_len_from_payload(payload) is None:
            continue
        if start is None:
            start = ts
        if ts - start > window_sec:
            break
        kept.append(rec_hdr + payload)

    tmp = path.with_suffix(".repair_tmp.pcap")
    with open(tmp, "wb") as f:
        f.write(_PCAP_GLOBAL_HEADER)
        for rec in kept:
            f.write(rec)
    tmp.rename(path)

    new_dur = pcap_duration(path)
    return old_dur, new_dur


def build_timeseries(path: Path, bin_ms: int, window_sec: int) -> np.ndarray:
    """Bin IP packet IP-header lengths into a byte-count array."""
    n_bins = int(window_sec * 1000 // bin_ms)
    ts = np.zeros(n_bins, dtype=np.float64)

    if not path.exists():
        return ts

    start: Optional[float] = None
    for ts_f, incl_len, orig_len, _, payload in _pcap_records(path):
        ip_len = _ip_len_from_payload(payload)
        if ip_len is None:
            continue
        if start is None:
            start = ts_f
        idx = int((ts_f - start) * 1000 // bin_ms)
        if 0 <= idx < n_bins:
            ts[idx] += ip_len

    return ts


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def fetch_transformed_ctps(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
                n.ctp_id,
                n.duration_seconds,
                n.download_pcap,
                n.upload_pcap,
                COALESCE(
                    (SELECT array_agg(leaf.subnet::text)
                     FROM ctp_nodes leaf
                     WHERE leaf.dataset_name = n.dataset_name
                       AND leaf.window_index = n.window_index
                       AND leaf.subnet << n.subnet
                       AND leaf.subnet::text LIKE '%/32'),
                    ARRAY[]::text[]
                ) AS leaf_subnets
            FROM ctp_nodes n
            WHERE n.is_transformed = true
            ORDER BY n.ctp_id
        """)
        return cur.fetchall()


def update_ctp_metrics(conn, ctp_id, dl_ts, ul_ts, intensity, burstiness, correlation, structure):
    intensity_json = {
        "mean_pps": intensity.mean_pps, "mean_bps": intensity.mean_bps,
        "mean_mbps": intensity.mean_mbps, "peak_pps": intensity.peak_pps,
        "peak_bps": intensity.peak_bps,
        "download_mean_mbps": intensity.download_mean_mbps,
        "upload_mean_mbps": intensity.upload_mean_mbps,
    }
    burstiness_json = {
        "peak_to_mean_ratio": burstiness.peak_to_mean_ratio,
        "coefficient_of_variation": burstiness.coefficient_of_variation,
        "percentile_95_to_mean": burstiness.percentile_95_to_mean,
        "on_periods": burstiness.on_periods, "off_periods": burstiness.off_periods,
    }
    correlation_json = {
        "lag_1": correlation.lag_1, "lag_5": correlation.lag_5,
        "lag_10": correlation.lag_10, "lag_60": correlation.lag_60,
    }
    structure_json = {
        "contributor_count": structure.contributor_count,
        "unique_source_ips": structure.unique_source_ips,
        "unique_dest_ips": structure.unique_dest_ips,
        "upload_download_ratio": structure.upload_download_ratio,
        "prefix_diversity": structure.prefix_diversity,
    }
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE ctp_nodes SET
                download_timeseries  = %s,
                upload_timeseries    = %s,
                contributor_count    = %s,
                intensity            = %s,
                burstiness           = %s,
                temporal_correlation = %s,
                structure            = %s
            WHERE ctp_id = %s
        """, (
            dl_ts.tolist(), ul_ts.tolist(),
            structure.contributor_count,
            json.dumps(intensity_json), json.dumps(burstiness_json),
            json.dumps(correlation_json), json.dumps(structure_json),
            ctp_id,
        ))
    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Report durations only; do NOT clip files or update DB.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process at most N CTPs (0 = all).")
    args = parser.parse_args()

    settings = get_settings()
    bin_ms  = settings.burst_interval_ms
    bin_sec = bin_ms / 1000.0

    conn = psycopg2.connect(settings.database_url)
    rows = fetch_transformed_ctps(conn)
    log.info("Found %d transformed CTPs.", len(rows))

    if args.limit:
        rows = rows[:args.limit]

    clipped = skipped = errors = 0

    for i, row in enumerate(rows, 1):
        ctp_id     = row["ctp_id"]
        window_sec = int(row["duration_seconds"] or 30)
        dl_path    = Path(row["download_pcap"]) if row["download_pcap"] else None
        ul_path    = Path(row["upload_pcap"])   if row["upload_pcap"]   else None
        leaf_ips   = [s.split("/")[0] for s in (row["leaf_subnets"] or [])]

        try:
            # --- Measure / clip ---
            pcap_clipped = False
            for pcap in (dl_path, ul_path):
                if pcap is None or not pcap.exists():
                    continue
                old_dur = pcap_duration(pcap)
                if old_dur > window_sec + 0.5:
                    if args.dry_run:
                        log.info("[%d/%d] NEEDS CLIP  %s  %.1fs → %ds",
                                 i, len(rows), ctp_id, old_dur, window_sec)
                    else:
                        _, new_dur = clip_pcap_in_place(pcap, window_sec)
                        log.info("[%d/%d] CLIPPED  %s  %.1fs → %.1fs",
                                 i, len(rows), ctp_id, old_dur, new_dur)
                    pcap_clipped = True

            if pcap_clipped:
                clipped += 1
            else:
                skipped += 1

            if args.dry_run:
                continue

            # --- Rebuild timeseries + metrics ---
            n_bins = int(window_sec * 1000 // bin_ms)
            dl_ts = build_timeseries(dl_path, bin_ms, window_sec) if dl_path else np.zeros(n_bins)
            ul_ts = build_timeseries(ul_path, bin_ms, window_sec) if ul_path else np.zeros(n_bins)

            intensity, burstiness, correlation, structure = compute_all_metrics(
                upload_ts=ul_ts, download_ts=dl_ts,
                bin_width_sec=bin_sec, contributor_ips=leaf_ips,
            )
            update_ctp_metrics(conn, ctp_id, dl_ts, ul_ts,
                               intensity, burstiness, correlation, structure)

            if i % 50 == 0:
                log.info("Progress: %d/%d  clipped=%d  skipped=%d  errors=%d",
                         i, len(rows), clipped, skipped, errors)

        except Exception as exc:
            log.error("[%d/%d] ERROR %s: %s", i, len(rows), ctp_id, exc)
            errors += 1
            try:
                conn.rollback()
            except Exception:
                pass

    conn.close()
    log.info("Done. clipped=%d  skipped=%d  errors=%d", clipped, skipped, errors)


if __name__ == "__main__":
    main()
