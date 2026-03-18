"""
routes.py — FastAPI endpoint handlers for the CTP Service.

Endpoints
~~~~~~~~~
- ``POST /ctps/extract``   — ingest PCAP traces into the CTP corpus
- ``POST /ctps/select``    — multi-dimensional corpus query
- ``POST /ctps/transform`` — rescale CTP to target capacity
- ``POST /ctps/merge``     — compose CTPs by window concat or weighted sum
- ``GET  /ctps/{id}/replay-data`` — export replay-ready PCAP for Substrate Worker
- ``GET  /ctps/{id}``      — full CTP details
- ``GET  /ctps``           — paginated corpus listing
- ``GET  /health``         — service health + DB connectivity

All endpoints use the shared :class:`~app.database.postgres.Database` and
operation classes injected via :func:`fastapi.Depends`.
"""

from __future__ import annotations

import logging
import platform
import sys
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from app.config import Settings, get_settings
from app.database.postgres import Database
from app.models.descriptors import (
    ExtractRequest,
    ExtractResponse,
    MergeRequest,
    MergeResponse,
    SelectRequest,
    SelectResponse,
    TransformRequest,
    TransformResponse,
)
from app.operations.export import CTPExporter
from app.operations.extract import Extractor
from app.operations.merge import CTPMerger
from app.operations.select import CTPSelector
from app.operations.transform import CTPTransformer

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_db() -> Database:
    """Dependency: return the process-level Database singleton.

    The singleton is stored on the FastAPI ``app.state`` object and
    initialised in the ``lifespan`` context manager in ``main.py``.
    """
    from app.main import get_db  # avoid circular import at module level

    return get_db()


DbDep = Annotated[Database, Depends(_get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/health", tags=["Health"])
def health_check(db: DbDep) -> dict:
    """Return service health and PostgreSQL connectivity status.

    Returns:
        JSON with ``status``, ``postgresql_connected``, and version info.
    """
    pg_ok = db.health_check()
    return {
        "status": "healthy" if pg_ok else "degraded",
        "postgresql_connected": pg_ok,
        "service_version": "1.0.0",
        "python_version": sys.version,
        "platform": platform.platform(),
    }


# ---------------------------------------------------------------------------
# CTP corpus listing
# ---------------------------------------------------------------------------


@router.get("/ctps", tags=["CTP Corpus"])
def list_ctps(
    db: DbDep,
    limit: int = Query(50, ge=1, le=10_000, description="Max results."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
    order_by: str = Query("intensity", description="Sort field."),
) -> dict:
    """Return a paginated listing of all CTPs in the corpus.

    Query Parameters:
        limit: Maximum results (default 50, max 10 000).
        offset: Pagination offset (default 0).
        order_by: intensity | burstiness | contributor_count | window_index.
    """
    selector = CTPSelector(db)
    total, ctps = selector.list_all(limit=limit, offset=offset, order_by=order_by)
    return {
        "total": total,
        "returned": len(ctps),
        "ctps": [c.to_db_dict() for c in ctps],
    }


# ---------------------------------------------------------------------------
# CTP details
# ---------------------------------------------------------------------------


@router.get("/ctps/{ctp_id}", tags=["CTP Corpus"])
def get_ctp(ctp_id: str, db: DbDep) -> dict:
    """Return full details and statistical descriptors for a single CTP.

    Path Parameters:
        ctp_id: Unique CTP identifier assigned during extraction.
    """
    selector = CTPSelector(db)
    ctp = selector.get_by_id(ctp_id)
    if ctp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CTP '{ctp_id}' not found.",
        )
    return ctp.to_db_dict()


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------


@router.post("/ctps/extract", tags=["Operations"], response_model=ExtractResponse)
def extract_ctps(
    request: ExtractRequest,
    db: DbDep,
    cfg: SettingsDep,
) -> ExtractResponse:
    """Ingest raw PCAP traces and extract CTP representations.

    The full six-step extraction pipeline is run synchronously:

    1. Split PCAPs by internal IP.
    2. Split per-user PCAPs into time windows.
    3. Build byte-count timeseries (100 ms bins).
    4. Construct prefix-hierarchical trees.
    5. Store all nodes in PostgreSQL.

    Request body:
        ``pcap_input``: Path to a PCAP file or directory.
        ``output_dir``: Root directory for intermediate per-user files.
        ``dataset_name``: Human-readable label for this dataset.
        ``window_duration_sec``: Override default window size.
        ``burst_interval_ms``: Override default bin width.
        ``internal_subnets``: Override default UCSB campus prefixes.
        ``workers``: Override default worker count.
    """
    extractor = Extractor(db=db, settings=cfg)
    try:
        ctps = extractor.run(
            pcap_input=request.pcap_input,
            output_dir=request.output_dir,
            dataset_name=request.dataset_name,
            window_duration_sec=request.window_duration_sec,
            burst_interval_ms=request.burst_interval_ms,
            internal_subnets=request.internal_subnets,
            workers=request.workers,
            start_time_epoch=request.start_time_epoch,
        )
    except Exception as exc:
        logger.exception("Extract failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {exc}",
        )

    window_indices = {c.window_index for c in ctps}
    user_count = len(
        {c.subnet for c in ctps if "/" in c.subnet and c.subnet.endswith("/32")}
    )

    return ExtractResponse(
        dataset_name=request.dataset_name,
        ctp_count=len(ctps),
        window_count=len(window_indices),
        user_count=user_count,
        extraction_status="success",
    )


# ---------------------------------------------------------------------------
# Select
# ---------------------------------------------------------------------------


@router.post("/ctps/select", tags=["Operations"], response_model=SelectResponse)
def select_ctps(request: SelectRequest, db: DbDep) -> SelectResponse:
    """Query the CTP corpus using multi-dimensional statistical descriptors.

    Request body:
        ``query``: Filter parameters (all optional).
        ``limit``: Max results (default 50).
        ``offset``: Pagination offset.
        ``order_by``: Sort field.
    """
    selector = CTPSelector(db)
    total, ctps = selector.select(
        query=request.query,
        limit=request.limit,
        offset=request.offset,
        order_by=request.order_by,
    )
    return SelectResponse(
        query_matched=total,
        results_returned=len(ctps),
        ctps=[c.to_db_dict() for c in ctps],
    )


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


@router.post("/ctps/transform", tags=["Operations"], response_model=TransformResponse)
def transform_ctp(
    request: TransformRequest,
    db: DbDep,
    cfg: SettingsDep,
) -> TransformResponse:
    """Rescale a CTP to a target bottleneck capacity.

    Amplitude scaling preserves burst timing, temporal correlation, and
    contributor structure.  Optionally trims bursts to a hard threshold.

    Request body:
        ``ctp_id``: ID of the CTP to transform.
        ``output_dir``: Directory for output PCAP files.
        ``throughput_threshold_mbps``: hard cap (burst trimming).
        ``preserve_structure``: Always ``true``; structure is never modified.
    """
    transformer = CTPTransformer(db=db, settings=cfg)

    # users_root must be derivable from the dataset's pcap source.
    # We use output_dir as users_root here for flexibility; callers can
    # override by passing an explicit users_root in a future extension.
    try:
        transformed, dl_path, ul_path = transformer.transform(
            ctp_id=request.ctp_id,
            output_dir=request.output_dir,
            users_root=request.users_root,
            throughput_threshold_mbps=request.throughput_threshold_mbps,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.exception("Transform failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transform failed: {exc}",
        )

    original = db.get_ctp(request.ctp_id)
    return TransformResponse(
        original_ctp_id=request.ctp_id,
        transformed_ctp_id=transformed.ctp_id,
        throughput_threshold_mbps=request.throughput_threshold_mbps,
        download_pcap=str(dl_path),
        upload_pcap=str(ul_path),
        notes="Trimming Done; temporal structure and asymmetry preserved.",
    )


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


@router.post("/ctps/merge", tags=["Operations"], response_model=MergeResponse)
def merge_ctps(
    request: MergeRequest,
    db: DbDep,
    cfg: SettingsDep,
) -> MergeResponse:
    """Merge all /32 leaf CTPs under a subnet across a window index range.

    Finds every /32 leaf node under *subnet* for windows
    ``[start_index, end_index]``, sums their timeseries per window,
    concatenates across windows, merges the underlying PCAP files with
    ``joincap``, and stores the resulting CTP in the corpus.

    Output PCAPs are written to::

        <output_dir>/<dataset_name>_merged/downlink/<ctp_id>_download.pcap
        <output_dir>/<dataset_name>_merged/uplink/<ctp_id>_upload.pcap

    Request body:
        ``dataset_name``: Dataset label.
        ``subnet``: Parent CIDR subnet.
        ``start_index``: First window index (inclusive).
        ``end_index``: Last window index (inclusive).
        ``output_dir``: Root directory for merged PCAP output.
        ``users_root``: Root of per-user PCAP directory from extraction.
    """
    merger = CTPMerger(db=db, settings=cfg)
    try:
        merged, dl_path, ul_path = merger.merge_subnet_range(
            dataset_name=request.dataset_name,
            subnet=request.subnet,
            start_index=request.start_index,
            end_index=request.end_index,
            output_dir=request.output_dir,
            users_root=request.users_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception("Merge failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Merge failed: {exc}",
        )

    return MergeResponse(
        merged_ctp_id=merged.ctp_id,
        dataset_name=request.dataset_name,
        subnet=request.subnet,
        start_index=request.start_index,
        end_index=request.end_index,
        leaf_count=merged.structure.contributor_count,
        merged_intensity_mbps=merged.intensity.mean_mbps,
        merged_contributor_count=merged.structure.contributor_count,
        download_pcap=str(dl_path),
        upload_pcap=str(ul_path),
        notes=(
            f"Merged {merged.structure.contributor_count} leaf IP(s) across "
            f"windows {request.start_index}–{request.end_index}."
        ),
    )


# ---------------------------------------------------------------------------
# Replay-data export
# ---------------------------------------------------------------------------


@router.get("/ctps/{ctp_id}/replay-data", tags=["Operations"])
def get_replay_data(
    ctp_id: str,
    db: DbDep,
    cfg: SettingsDep,
    replay_dir: str = Query(..., description="Root directory for replay-ready PCAPs."),
    users_root: str = Query(..., description="Root of per-user PCAP directory tree."),
    direction: str = Query("download", description="'download' or 'upload'."),
) -> FileResponse:
    """Export a CTP as a replay-ready PCAP file for the Substrate Worker.

    The merged PCAP is located (or generated) and returned as a file download.

    Query Parameters:
        replay_dir: Root directory for replay PCAP output.
        users_root: Root of the per-user PCAP directory (from extraction).
        direction: Which direction to export (``download`` or ``upload``).
    """
    exporter = CTPExporter(db=db, settings=cfg)
    try:
        dl_path, ul_path = exporter.export_replay_pcap(
            ctp_id=ctp_id,
            replay_dir=replay_dir,
            users_root=users_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.exception("Replay export failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {exc}",
        )

    pcap_path = dl_path if direction == "download" else ul_path
    if not pcap_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replay PCAP for direction '{direction}' not found at '{pcap_path}'.",
        )

    return JSONResponse(
        content={
            "download_pcap": str(dl_path),
            "upload_pcap": str(ul_path),
        }
    )
