"""CTP PCAP fetcher for substrate workers.

Ensures the *download* and *upload* PCAP files for a CTP pointer are present
under the expected directory structure inside *ctp_root*::

    <ctp_root>/
        download/<name>.pcap
        upload/<name>.pcap

CTP pointer formats
--------------------
URL ending in ``/export``  (starts with ``http://`` or ``https://``)
    The CTP service returns a single ZIP archive.  The worker downloads it once
    and extracts ``download/*.pcap`` and ``upload/*.pcap`` (also accepts
    ``downlink/`` and ``uplink/`` folder names).  This works when the worker is
    on a different host than the orchestrator: only HTTP is required.

    Example: ``http://ctp-service:8001/ctps/ctp-transform-foo/export``

URL  (other ``http://`` / ``https://`` URLs)
    The pointer is a base URL.  Direction variants are fetched by appending
    ``?direction=download`` and ``?direction=upload``.  The base name is the
    last path segment of the URL (``Path(url.path).stem``).

    Example: ``http://ctp-service:8001/ctps/abc123``
    → GET http://ctp-service:8001/ctps/abc123?direction=download
    → GET http://ctp-service:8001/ctps/abc123?direction=upload

Absolute path  (starts with ``/``)
    The pointer is the absolute path to the *download* PCAP file.  The upload
    counterpart is derived by replacing the first ``/download/`` segment with
    ``/upload/``.  Files are copied into *ctp_root* if not already present.

    Example: ``/mnt/md0/ctp/download/cluster0_tree1_p1.pcap``
    → download source: that path
    → upload source:   ``/mnt/md0/ctp/upload/cluster0_tree1_p1.pcap``

Plain name  (anything else)
    Treated as a base name already mounted in *ctp_root*.  No fetch or copy is
    performed; the function just verifies that both files exist.

    Example: ``cluster0_tree1_p1``
    → verifies ``<ctp_root>/download/cluster0_tree1_p1.pcap`` exists
    → verifies ``<ctp_root>/upload/cluster0_tree1_p1.pcap`` exists
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_CTP_ROOT = os.environ.get("CTP_DIR", "/home/netreplica/config/ctp")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_ctp(ctp_pointer: str, ctp_root: str | None = None) -> dict:
    """Ensure download + upload PCAPs for *ctp_pointer* exist in *ctp_root*.

    Creates ``<ctp_root>/download/`` and ``<ctp_root>/upload/`` directories if
    they do not exist.

    Args:
        ctp_pointer: URL, absolute path, or plain base name identifying the CTP.
        ctp_root: Root CTP directory on the worker.  Defaults to the ``CTP_DIR``
                  environment variable (``/home/netreplica/config/ctp``).

    Returns:
        A dict with keys:
            ``name`` (str)          — resolved base file name, no ``.pcap`` suffix
            ``download_path`` (str) — absolute path to the download PCAP
            ``upload_path`` (str)   — absolute path to the upload PCAP
            ``fetched`` (bool)      — True if files were fetched/copied, False if
                                      they were already present

    Raises:
        FileNotFoundError: A local source file referenced by the pointer does not exist.
        RuntimeError:      An HTTP fetch operation failed.
    """
    root = Path(ctp_root or _DEFAULT_CTP_ROOT)
    dl_dir = root / "download"
    ul_dir = root / "upload"
    dl_dir.mkdir(parents=True, exist_ok=True)
    ul_dir.mkdir(parents=True, exist_ok=True)

    if ctp_pointer.startswith(("http://", "https://")):
        if _is_export_zip_url(ctp_pointer):
            return _fetch_from_export_zip(ctp_pointer, dl_dir, ul_dir)
        return _fetch_from_url(ctp_pointer, dl_dir, ul_dir)
    elif ctp_pointer.startswith("/"):
        return _fetch_from_local_path(ctp_pointer, dl_dir, ul_dir)
    else:
        return _verify_existing(ctp_pointer, dl_dir, ul_dir)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_export_zip_url(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    return path.endswith("/export")


def _first_zip_pcap_member(
    zf: zipfile.ZipFile, top_level_folders: tuple[str, ...]
) -> tuple[str, str]:
    """Return (zip_member_name, stem) for the first ``.pcap`` under a top folder."""
    folders = {f.lower() for f in top_level_folders}
    for name in sorted(zf.namelist()):
        if name.endswith("/"):
            continue
        parts = name.split("/")
        if len(parts) < 2:
            continue
        if parts[0].lower() not in folders:
            continue
        if not name.lower().endswith(".pcap"):
            continue
        stem = Path(parts[-1]).stem
        return name, stem
    raise RuntimeError(
        f"No .pcap found under {top_level_folders} in export ZIP "
        f"(members: {zf.namelist()[:20]}...)"
    )


def _fetch_from_export_zip(url: str, dl_dir: Path, ul_dir: Path) -> dict:
    """GET a ZIP from *url*; extract download+upload (or downlink+uplink) PCAPs."""
    logger.info("Fetching CTP export ZIP from %s", url)
    try:
        resp = httpx.get(url, timeout=120, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Failed to download CTP export ZIP from {url}: {exc}"
        ) from exc

    data = resp.content

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"CTP export response is not a valid ZIP: {exc}") from exc

    with zf:
        dl_member, dl_stem = _first_zip_pcap_member(zf, ("download", "downlink"))
        ul_member, ul_stem = _first_zip_pcap_member(zf, ("upload", "uplink"))

        name = dl_stem
        if dl_stem != ul_stem:
            logger.warning(
                "Download PCAP stem %r differs from upload stem %r; using %r",
                dl_stem,
                ul_stem,
                name,
            )

        dl_dest = dl_dir / f"{name}.pcap"
        ul_dest = ul_dir / f"{name}.pcap"
        dl_dest.write_bytes(zf.read(dl_member))
        ul_dest.write_bytes(zf.read(ul_member))

    return {
        "name": name,
        "download_path": str(dl_dest),
        "upload_path": str(ul_dest),
        "fetched": True,
    }


def _base_name_from_url(url: str) -> str:
    """Return the last path segment of *url*, stripped of any ``.pcap`` suffix."""
    segment = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return Path(segment).stem if segment else "ctp"


def _fetch_from_url(base_url: str, dl_dir: Path, ul_dir: Path) -> dict:
    name = _base_name_from_url(base_url)
    dl_dest = dl_dir / f"{name}.pcap"
    ul_dest = ul_dir / f"{name}.pcap"

    fetched = False
    for dest, direction in ((dl_dest, "download"), (ul_dest, "upload")):
        url = f"{base_url.rstrip('/')}?direction={direction}"
        logger.info("Fetching CTP %s PCAP from %s → %s", direction, url, dest)
        try:
            with httpx.stream("GET", url, timeout=120, follow_redirects=True) as resp:
                resp.raise_for_status()
                with dest.open("wb") as fh:
                    for chunk in resp.iter_bytes():
                        fh.write(chunk)
            fetched = True
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Failed to fetch CTP {direction} PCAP from {url}: {exc}"
            ) from exc

    return {
        "name": name,
        "download_path": str(dl_dest),
        "upload_path": str(ul_dest),
        "fetched": fetched,
    }


def _fetch_from_local_path(source_path: str, dl_dir: Path, ul_dir: Path) -> dict:
    dl_src = Path(source_path)
    if not dl_src.exists():
        raise FileNotFoundError(f"CTP download source not found: {dl_src}")

    name = dl_src.stem  # strip .pcap extension

    # Derive upload source: /downlink/→/uplink/ or /download/→/upload/
    if "/downlink/" in source_path:
        ul_src_str = source_path.replace("/downlink/", "/uplink/", 1)
    else:
        ul_src_str = source_path.replace("/download/", "/upload/", 1)
    ul_src = Path(ul_src_str)
    if not ul_src.exists():
        raise FileNotFoundError(f"CTP upload source not found: {ul_src}")

    dl_dest = dl_dir / f"{name}.pcap"
    ul_dest = ul_dir / f"{name}.pcap"

    fetched = False
    for src, dest in ((dl_src, dl_dest), (ul_src, ul_dest)):
        if dest.exists() and dest.stat().st_size == src.stat().st_size:
            logger.debug("CTP file already in place at %s, skipping copy", dest)
        else:
            shutil.copy2(str(src), str(dest))
            logger.info("Copied CTP PCAP %s → %s", src, dest)
            fetched = True

    return {
        "name": name,
        "download_path": str(dl_dest),
        "upload_path": str(ul_dest),
        "fetched": fetched,
    }


def _verify_existing(name: str, dl_dir: Path, ul_dir: Path) -> dict:
    """Plain-name pointer: verify both files are already present."""
    dl_path = dl_dir / f"{name}.pcap"
    ul_path = ul_dir / f"{name}.pcap"

    missing = [str(p) for p in (dl_path, ul_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"CTP PCAP files not found (expected pre-mounted): {', '.join(missing)}"
        )

    return {
        "name": name,
        "download_path": str(dl_path),
        "upload_path": str(ul_path),
        "fetched": False,
    }
