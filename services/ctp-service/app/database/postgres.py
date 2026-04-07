"""
postgres.py — PostgreSQL connection pool and data-access layer.

All CTP corpus reads and writes go through this module.  A single
:class:`Database` instance is shared for the lifetime of the process and
manages a ``psycopg2`` connection pool.

Usage
~~~~~
.. code-block:: python

    from app.database.postgres import Database

    db = Database(database_url="postgresql://user:pass@localhost:5432/ctp_corpus")
    db.initialize()                # create tables if needed
    db.upsert_ctp(ctp)             # store one CTP
    results = db.query_ctps(query, limit=50)
    db.close()                     # release pool
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import Json, RealDictCursor

from app.models.ctp import (
    CTPBurstiness,
    CTPIntensity,
    CTPStructure,
    CTPTemporalCorrelation,
    CrossTrafficProfile,
)
from app.models.descriptors import SelectQuery

logger = logging.getLogger(__name__)

# Path to the schema SQL file (sibling of this module)
_SCHEMA_FILE = Path(__file__).parent / "schema.sql"


class Database:
    """Thread-safe PostgreSQL access layer backed by a ``psycopg2`` pool.

    Args:
        database_url: ``postgresql://user:pass@host:port/dbname`` style URL.
        pool_min: Minimum connections kept alive in the pool.
        pool_max: Maximum connections the pool will open.
    """

    def __init__(
        self,
        database_url: str,
        pool_min: int = 2,
        pool_max: int = 10,
    ) -> None:
        self._url = database_url
        self._pool_min = pool_min
        self._pool_max = pool_max
        self._pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def initialize(self) -> None:
        """Open the connection pool and create tables from ``schema.sql``."""
        logger.info("Connecting to PostgreSQL: %s", self._redacted_url())
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            self._pool_min,
            self._pool_max,
            self._url,
        )
        self._apply_schema()
        logger.info(
            "PostgreSQL pool ready (min=%d, max=%d)", self._pool_min, self._pool_max
        )

    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            self._pool = None
            logger.info("PostgreSQL pool closed.")

    def health_check(self) -> bool:
        """Return ``True`` if the database is reachable."""
        try:
            with self._cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as exc:
            logger.warning("PostgreSQL health check failed: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #

    def _apply_schema(self) -> None:
        """Execute the schema SQL file to create tables and indexes."""
        if not _SCHEMA_FILE.exists():
            logger.warning("Schema file not found: %s — skipping DDL", _SCHEMA_FILE)
            return
        ddl = _SCHEMA_FILE.read_text()
        with self._cursor() as cur:
            cur.execute(ddl)
        logger.info("Schema applied from %s", _SCHEMA_FILE)

    # ------------------------------------------------------------------ #
    # Write operations
    # ------------------------------------------------------------------ #

    def upsert_ctp(self, ctp: CrossTrafficProfile) -> None:
        """Insert or update a single CTP row in ``ctp_nodes``.

        Uses ``ON CONFLICT DO UPDATE`` so the pipeline can be re-run safely.

        Args:
            ctp: The :class:`~app.models.ctp.CrossTrafficProfile` to store.
        """
        row = ctp.to_db_dict()
        sql = """
                INSERT INTO ctp_nodes (
                    ctp_id, dataset_name, subnet, window_index,
                    extracted_from, start_time, duration_seconds,
                    upload_timeseries, download_timeseries,
                    contributor_count,
                    intensity, burstiness, temporal_correlation, structure,
                    is_transformed, throughput_threshold_mbps,
                    download_pcap, upload_pcap,
                    is_merged, merge_start_index, merge_end_index,
                    created_at
                ) VALUES (
                    %(ctp_id)s, %(dataset_name)s, %(subnet)s, %(window_index)s,
                    %(extracted_from)s, %(start_time)s, %(duration_seconds)s,
                    %(upload_timeseries)s, %(download_timeseries)s,
                    %(contributor_count)s,
                    %(intensity)s, %(burstiness)s, %(temporal_correlation)s, %(structure)s,
                    %(is_transformed)s, %(throughput_threshold_mbps)s,
                    %(download_pcap)s, %(upload_pcap)s,
                    %(is_merged)s, %(merge_start_index)s, %(merge_end_index)s,
                    NOW()
                )
                ON CONFLICT (ctp_id) DO UPDATE SET
                    dataset_name              = EXCLUDED.dataset_name,
                    subnet                    = EXCLUDED.subnet,
                    window_index              = EXCLUDED.window_index,
                    extracted_from            = EXCLUDED.extracted_from,
                    start_time                = EXCLUDED.start_time,
                    duration_seconds          = EXCLUDED.duration_seconds,
                    upload_timeseries         = EXCLUDED.upload_timeseries,
                    download_timeseries       = EXCLUDED.download_timeseries,
                    contributor_count         = EXCLUDED.contributor_count,
                    intensity                 = EXCLUDED.intensity,
                    burstiness                = EXCLUDED.burstiness,
                    temporal_correlation      = EXCLUDED.temporal_correlation,
                    structure                 = EXCLUDED.structure,
                    is_transformed            = EXCLUDED.is_transformed,
                    throughput_threshold_mbps = EXCLUDED.throughput_threshold_mbps,
                    download_pcap             = EXCLUDED.download_pcap,
                    upload_pcap               = EXCLUDED.upload_pcap,
                    is_merged                 = EXCLUDED.is_merged,
                    merge_start_index         = EXCLUDED.merge_start_index,
                    merge_end_index           = EXCLUDED.merge_end_index;
        """
        params = {**row}
        # Wrap dicts as JSONB
        for key in ("intensity", "burstiness", "temporal_correlation", "structure"):
            params[key] = Json(params[key])

        with self._cursor() as cur:
            cur.execute(sql, params)

    def upsert_ctps_bulk(self, ctps: List[CrossTrafficProfile]) -> int:
        """Bulk-upsert a list of CTPs in a single transaction.

        Args:
            ctps: List of CTPs to store.

        Returns:
            Number of rows upserted.
        """
        for ctp in ctps:
            self.upsert_ctp(ctp)
        return len(ctps)

    def upsert_dataset(
        self,
        dataset_name: str,
        *,
        pcap_source: str = "",
        window_duration_sec: int = 30,
        burst_interval_ms: int = 100,
        gateway_subnet: str = "",
        total_windows: int = 0,
        total_users: int = 0,
    ) -> None:
        """Insert or update a row in the ``datasets`` table.

        Args:
            dataset_name: Primary key for the dataset.
            pcap_source: Original PCAP file/directory path.
            window_duration_sec: Window length used during extraction.
            burst_interval_ms: Bin width used during extraction.
            gateway_subnet: Gateway CIDR, e.g. ``'169.231.0.0/16'``.
            total_windows: Number of time windows extracted.
            total_users: Number of unique /32 leaf users.
        """
        sql = """
            INSERT INTO datasets (
                dataset_name, pcap_source,
                window_duration_sec, burst_interval_ms,
                gateway_subnet, total_windows, total_users
            ) VALUES (
                %(dataset_name)s, %(pcap_source)s,
                %(window_duration_sec)s, %(burst_interval_ms)s,
                %(gateway_subnet)s, %(total_windows)s, %(total_users)s
            )
            ON CONFLICT (dataset_name) DO UPDATE SET
                pcap_source         = EXCLUDED.pcap_source,
                window_duration_sec = EXCLUDED.window_duration_sec,
                burst_interval_ms   = EXCLUDED.burst_interval_ms,
                gateway_subnet      = EXCLUDED.gateway_subnet,
                total_windows       = EXCLUDED.total_windows,
                total_users         = EXCLUDED.total_users;
        """
        with self._cursor() as cur:
            cur.execute(
                sql,
                {
                    "dataset_name": dataset_name,
                    "pcap_source": pcap_source,
                    "window_duration_sec": window_duration_sec,
                    "burst_interval_ms": burst_interval_ms,
                    "gateway_subnet": gateway_subnet or None,
                    "total_windows": total_windows,
                    "total_users": total_users,
                },
            )

    # ------------------------------------------------------------------ #
    # Read operations
    # ------------------------------------------------------------------ #

    def get_ctp(self, ctp_id: str) -> Optional[CrossTrafficProfile]:
        """Fetch a single CTP by its ``ctp_id``.

        Args:
            ctp_id: Unique CTP identifier.

        Returns:
            :class:`~app.models.ctp.CrossTrafficProfile` or ``None``.
        """
        sql = "SELECT * FROM ctp_nodes WHERE ctp_id = %s LIMIT 1;"
        with self._cursor() as cur:
            cur.execute(sql, (ctp_id,))
            row = cur.fetchone()
        return _row_to_ctp(row) if row else None

    def get_ctp_by_key(
        self, dataset_name: str, subnet: str, window_index: int
    ) -> Optional[CrossTrafficProfile]:
        """Fetch a CTP by its primary key (dataset, subnet, window_index).

        Args:
            dataset_name: Dataset label.
            subnet: CIDR subnet string.
            window_index: Zero-based window index.

        Returns:
            :class:`~app.models.ctp.CrossTrafficProfile` or ``None``.
        """
        sql = """
            SELECT * FROM ctp_nodes
            WHERE dataset_name = %s AND subnet = %s AND window_index = %s
            LIMIT 1;
        """
        with self._cursor() as cur:
            cur.execute(sql, (dataset_name, subnet, window_index))
            row = cur.fetchone()
        return _row_to_ctp(row) if row else None

    def query_ctps(
        self,
        query: SelectQuery,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "intensity",
    ) -> tuple[int, List[CrossTrafficProfile]]:
        """Multi-dimensional range query against ``ctp_nodes``.

        Args:
            query: :class:`~app.models.descriptors.SelectQuery` filter.
            limit: Maximum rows to return.
            offset: Pagination offset.
            order_by: Sort field (``intensity`` | ``burstiness`` |
                ``contributor_count`` | ``window_index``).

        Returns:
            Tuple of ``(total_matched_count, list_of_ctps)``.
        """
        where_clauses, params = _build_where(query)
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        order_sql = _build_order(order_by)

        count_sql = f"SELECT COUNT(*) FROM ctp_nodes {where_sql};"
        data_sql = f"""
            SELECT * FROM ctp_nodes
            {where_sql}
            ORDER BY {order_sql}
            LIMIT %s OFFSET %s;
        """
        with self._cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()["count"]

            cur.execute(data_sql, params + [limit, offset])
            rows = cur.fetchall()

        ctps = [_row_to_ctp(r) for r in rows if r]
        return total, ctps

    def list_ctps(
        self,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "intensity",
    ) -> tuple[int, List[CrossTrafficProfile]]:
        """Return a paginated list of all CTPs.

        Args:
            limit: Max rows to return.
            offset: Pagination offset.
            order_by: Sort field.

        Returns:
            Tuple of ``(total_count, list_of_ctps)``.
        """
        return self.query_ctps(
            SelectQuery(), limit=limit, offset=offset, order_by=order_by
        )

    def count_ctps(self, dataset_name: Optional[str] = None) -> int:
        """Return the total number of CTPs, optionally filtered by dataset.

        Args:
            dataset_name: If provided, count only CTPs in this dataset.

        Returns:
            Integer row count.
        """
        if dataset_name:
            sql = "SELECT COUNT(*) FROM ctp_nodes WHERE dataset_name = %s;"
            params: tuple = (dataset_name,)
        else:
            sql = "SELECT COUNT(*) FROM ctp_nodes;"
            params = ()
        with self._cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()["count"]

    def get_leaf_ctps_for_subnet(
        self, dataset_name: str, subnet: str, window_index: int
    ) -> List[CrossTrafficProfile]:
        """Return all /32 leaf CTPs that are sub-networks of *subnet*.

        Used by the transform operation to locate per-user PCAP files.

        Args:
            dataset_name: Dataset to search.
            subnet: Parent CIDR subnet (e.g. ``'169.231.10.0/24'``).
            window_index: Time-window index.

        Returns:
            List of /32 leaf CTPs under *subnet*.
        """
        sql = """
            SELECT * FROM ctp_nodes
            WHERE dataset_name = %s
              AND window_index  = %s
              AND subnet        <<= %s::cidr
              AND masklen(subnet) = 32
              AND is_transformed = FALSE
              AND is_merged = FALSE;
        """
        with self._cursor() as cur:
            cur.execute(sql, (dataset_name, window_index, subnet))
            rows = cur.fetchall()
        return [_row_to_ctp(r) for r in rows if r]

    def get_leaf_ctps_for_subnet_range(
        self, dataset_name: str, subnet: str, start_index: int, end_index: int
    ) -> List[CrossTrafficProfile]:
        """Return all /32 leaf CTPs under *subnet* across a window index range.

        Args:
            dataset_name: Dataset to search.
            subnet: Parent CIDR subnet (e.g. ``'169.231.10.0/24'``).
            start_index: First window index (inclusive).
            end_index: Last window index (inclusive).

        Returns:
            List of /32 leaf CTPs under *subnet* for windows in [start, end].
        """
        sql = """
            SELECT * FROM ctp_nodes
            WHERE dataset_name = %s
              AND subnet        <<= %s::cidr
              AND window_index  BETWEEN %s AND %s
              AND masklen(subnet) = 32
              AND is_transformed = FALSE
              AND is_merged = FALSE;
        """
        with self._cursor() as cur:
            cur.execute(sql, (dataset_name, subnet, start_index, end_index))
            rows = cur.fetchall()
        return [_row_to_ctp(r) for r in rows if r]

    # ------------------------------------------------------------------ #
    # Connection helpers
    # ------------------------------------------------------------------ #

    @contextmanager
    def _cursor(self) -> Generator[RealDictCursor, None, None]:
        """Yield a ``RealDictCursor`` from the pool, auto-committing on exit.

        Raises:
            RuntimeError: If :meth:`initialize` has not been called yet.
        """
        if self._pool is None:
            raise RuntimeError("Database.initialize() must be called before use.")
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def _redacted_url(self) -> str:
        """Return the DB URL with the password replaced by ``****``."""
        try:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(self._url)
            redacted = parsed._replace(
                netloc=parsed.netloc.replace(parsed.password or "", "****")
            )
            return urlunparse(redacted)
        except Exception:
            return "<redacted>"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


# Default bin width in seconds (100 ms).  Used in the unnest fallback when
# per-direction means are not yet stored (original DB without capped copy).
_BIN_SEC: float = 0.1
_MBPS_FACTOR: float = 8.0 / _BIN_SEC / 1_000_000.0  # bytes/bin → Mbps


def _intensity_mean_expr(direction: str) -> str:
    """Return a SQL expression for mean throughput in Mbps for *direction*.

    For 'both' uses the pre-computed ``intensity->>'mean_mbps'`` (indexed).
    For 'download'/'upload' uses the stored per-direction field when present,
    falling back to an ``unnest()`` computation so the filter works on both
    the original DB and the capped copy.
    """
    if direction == "both":
        return "(intensity->>'mean_mbps')::FLOAT8"
    col = "download_timeseries" if direction == "download" else "upload_timeseries"
    stored = f"(intensity->>'{direction}_mean_mbps')::FLOAT8"
    fallback = f"(SELECT AVG(v) * {_MBPS_FACTOR} FROM unnest({col}) v)"
    return f"COALESCE({stored}, {fallback})"


def _intensity_peak_expr(direction: str) -> str:
    """Return a SQL expression for peak throughput in Mbps for *direction*."""
    if direction == "both":
        return "(intensity->>'peak_bps')::FLOAT8 / 1000000.0"
    col = "download_timeseries" if direction == "download" else "upload_timeseries"
    return f"(SELECT MAX(v) * {_MBPS_FACTOR} FROM unnest({col}) v)"


def _build_where(query: SelectQuery) -> tuple[list[str], list[Any]]:
    """Build ``WHERE`` clauses and positional params from a :class:`SelectQuery`.

    Returns:
        Tuple of ``(list_of_clause_strings, list_of_params)``.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if query.dataset_name:
        clauses.append("dataset_name = %s")
        params.append(query.dataset_name)

    if query.is_transformed is not None:
        clauses.append("is_transformed = %s")
        params.append(query.is_transformed)

    if query.subnet_prefix_len is not None:
        clauses.append("masklen(subnet) = %s")
        params.append(query.subnet_prefix_len)

    if query.intensity_range_mbps:
        lo, hi = query.intensity_range_mbps
        clauses.append(
            f"{_intensity_mean_expr(query.intensity_direction)} BETWEEN %s AND %s"
        )
        params.extend([lo, hi])

    if query.burstiness_pmr_range:
        lo, hi = query.burstiness_pmr_range
        clauses.append("(burstiness->>'peak_to_mean_ratio')::FLOAT8 BETWEEN %s AND %s")
        params.extend([lo, hi])

    if query.burstiness_cov_range:
        lo, hi = query.burstiness_cov_range
        clauses.append(
            "(burstiness->>'coefficient_of_variation')::FLOAT8 BETWEEN %s AND %s"
        )
        params.extend([lo, hi])

    if query.temporal_correlation_min is not None:
        clauses.append("(temporal_correlation->>'lag_1')::FLOAT8 >= %s")
        params.append(query.temporal_correlation_min)

    if query.contributor_count_min is not None:
        clauses.append("contributor_count >= %s")
        params.append(query.contributor_count_min)

    if query.contributor_count_max is not None:
        clauses.append("contributor_count <= %s")
        params.append(query.contributor_count_max)

    if query.upload_download_ratio_max is not None:
        clauses.append("(structure->>'upload_download_ratio')::FLOAT8 <= %s")
        params.append(query.upload_download_ratio_max)

    if query.window_index_range:
        lo, hi = query.window_index_range
        clauses.append("window_index BETWEEN %s AND %s")
        params.extend([lo, hi])

    if query.peak_intensity_max_mbps is not None:
        clauses.append(f"{_intensity_peak_expr(query.intensity_direction)} <= %s")
        params.append(query.peak_intensity_max_mbps)

    return clauses, params


def _build_order(order_by: str) -> str:
    """Return a safe SQL ``ORDER BY`` expression for *order_by*.

    Uses a whitelist to prevent SQL injection.
    """
    mapping = {
        "intensity": "(intensity->>'mean_mbps')::FLOAT8 DESC",
        "burstiness": "(burstiness->>'peak_to_mean_ratio')::FLOAT8 DESC",
        "contributor_count": "contributor_count DESC",
        "window_index": "window_index ASC",
    }
    return mapping.get(order_by, "(intensity->>'mean_mbps')::FLOAT8 DESC")


def _row_to_ctp(row: Dict[str, Any]) -> CrossTrafficProfile:
    """Reconstruct a :class:`CrossTrafficProfile` from a ``RealDictCursor`` row.

    Args:
        row: A row dict from the ``ctp_nodes`` table.

    Returns:
        Fully populated :class:`~app.models.ctp.CrossTrafficProfile`.
    """
    intensity_d = (
        row["intensity"]
        if isinstance(row["intensity"], dict)
        else json.loads(row["intensity"])
    )
    burst_d = (
        row["burstiness"]
        if isinstance(row["burstiness"], dict)
        else json.loads(row["burstiness"])
    )
    corr_d = (
        row["temporal_correlation"]
        if isinstance(row["temporal_correlation"], dict)
        else json.loads(row["temporal_correlation"])
    )
    struct_d = (
        row["structure"]
        if isinstance(row["structure"], dict)
        else json.loads(row["structure"])
    )

    return CrossTrafficProfile(
        ctp_id=row["ctp_id"],
        dataset_name=row["dataset_name"],
        subnet=str(row["subnet"]),
        window_index=row["window_index"],
        extracted_from=row.get("extracted_from", ""),
        start_time=row.get("start_time"),
        duration_seconds=row.get("duration_seconds", 30),
        upload_timeseries=list(row.get("upload_timeseries") or []),
        download_timeseries=list(row.get("download_timeseries") or []),
        intensity=CTPIntensity(
            mean_pps=intensity_d.get("mean_pps", 0.0),
            mean_bps=intensity_d.get("mean_bps", 0.0),
            peak_pps=intensity_d.get("peak_pps", 0.0),
            peak_bps=intensity_d.get("peak_bps", 0.0),
            download_mean_mbps=intensity_d.get("download_mean_mbps"),
            upload_mean_mbps=intensity_d.get("upload_mean_mbps"),
        ),
        burstiness=CTPBurstiness(
            peak_to_mean_ratio=burst_d.get("peak_to_mean_ratio", 0.0),
            coefficient_of_variation=burst_d.get("coefficient_of_variation", 0.0),
            percentile_95_to_mean=burst_d.get("percentile_95_to_mean", 0.0),
            on_periods=burst_d.get("on_periods", 0),
            off_periods=burst_d.get("off_periods", 0),
        ),
        temporal_correlation=CTPTemporalCorrelation(
            lag_1=corr_d.get("lag_1", 0.0),
            lag_5=corr_d.get("lag_5", 0.0),
            lag_10=corr_d.get("lag_10", 0.0),
            lag_60=corr_d.get("lag_60"),
        ),
        structure=CTPStructure(
            contributor_count=struct_d.get("contributor_count", 0),
            unique_source_ips=struct_d.get("unique_source_ips", 0),
            unique_dest_ips=struct_d.get("unique_dest_ips", 0),
            upload_download_ratio=struct_d.get("upload_download_ratio", -1.0),
            prefix_diversity=struct_d.get("prefix_diversity", 0.0),
        ),
        created_at=row.get("created_at"),
        is_transformed=row.get("is_transformed", False),
        throughput_threshold_mbps=row.get("throughput_threshold_mbps"),
        download_pcap=row.get("download_pcap"),
        upload_pcap=row.get("upload_pcap"),
        is_merged=row.get("is_merged", False),
        merge_start_index=row.get("merge_start_index"),
        merge_end_index=row.get("merge_end_index"),
    )
