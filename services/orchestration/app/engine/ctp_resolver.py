"""CTP PCAP file resolver for the orchestration workflow.

Maps a ``ctp_cluster`` name (e.g. ``"cluster0"``) to concrete PCAP file paths
on disk.  The PCAP corpus lives in a directory tree with separate download and
upload sub-directories, each containing files named like::

    cluster0_tree9_profile869.pcap
    cluster10_tree2_profile544.pcap

Resolution rules:

1. If the user specifies a cluster, list all PCAPs matching that cluster prefix
   in both download and upload directories and pick one at random.
2. If no cluster is specified (or ``"default"``), use a configurable default.

Environment variables:

- ``ORCH_CTP_DOWNLOAD_DIR`` — directory of download-direction CTP PCAPs
  (default: ``<repo>/netreplica/config/ctp/ctp_100_cluster_6M``)
- ``ORCH_CTP_UPLOAD_DIR`` — directory of upload-direction CTP PCAPs
  (default: ``<repo>/netreplica/config/ctp/ctp_100_cluster_incoming_6M``)
- ``ORCH_CTP_DEFAULT_CLUSTER`` — cluster name when none is specified
  (default: ``cluster0``)
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    """Best-effort: four levels up from this file lands at the repo root."""
    return Path(__file__).resolve().parents[4]


def _download_dir() -> Path:
    env = os.getenv("ORCH_CTP_DOWNLOAD_DIR", "").strip()
    if env:
        return Path(env)
    return _repo_root() / "netreplica" / "config" / "ctp" / "ctp_100_cluster_6M"


def _upload_dir() -> Path:
    env = os.getenv("ORCH_CTP_UPLOAD_DIR", "").strip()
    if env:
        return Path(env)
    return _repo_root() / "netreplica" / "config" / "ctp" / "ctp_100_cluster_incoming_6M"


def _default_cluster() -> str:
    return os.getenv("ORCH_CTP_DEFAULT_CLUSTER", "cluster0")


def _pick_pcap(directory: Path, cluster: str) -> Path | None:
    """Return a random PCAP from *directory* whose name starts with *cluster*_."""
    if not directory.is_dir():
        return None
    matches = sorted(directory.glob(f"{cluster}_*.pcap"))
    if not matches:
        return None
    return random.choice(matches)


class CtpResolution:
    """Resolved CTP PCAP paths for one experiment spec."""

    def __init__(
        self,
        cluster: str,
        download_pcap: Path | None,
        upload_pcap: Path | None,
    ) -> None:
        self.cluster = cluster
        self.download_pcap = download_pcap
        self.upload_pcap = upload_pcap

    @property
    def ready(self) -> bool:
        return self.download_pcap is not None and self.download_pcap.exists()

    @property
    def replay_ctp_file(self) -> str | None:
        """Value for substrate ``POST /replay`` ``ctp_file`` field.

        The substrate worker builds ``CTP_DIR/{ctp_file}.pcap``, so we return
        the relative path inside the CTP root **without** the ``.pcap`` suffix.
        e.g. ``ctp_100_cluster_6M/cluster0_tree9_profile869``
        """
        if self.download_pcap is None:
            return None
        ctp_root = _download_dir().parent
        try:
            rel = self.download_pcap.relative_to(ctp_root)
        except ValueError:
            rel = self.download_pcap
        return str(rel.with_suffix(""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster": self.cluster,
            "download_pcap": str(self.download_pcap) if self.download_pcap else None,
            "upload_pcap": str(self.upload_pcap) if self.upload_pcap else None,
            "ready": self.ready,
            "replay_ctp_file": self.replay_ctp_file,
        }


def resolve_ctp(ctp_cluster: str | None) -> CtpResolution:
    """Resolve a cluster name to concrete PCAP paths."""
    cluster = ctp_cluster or _default_cluster()

    # Normalize legacy names that don't match on-disk cluster naming
    if cluster.startswith("ctp_") or cluster == "default":
        cluster = _default_cluster()

    dl_dir = _download_dir()
    ul_dir = _upload_dir()

    dl_pcap = _pick_pcap(dl_dir, cluster)
    ul_pcap = _pick_pcap(ul_dir, cluster)

    return CtpResolution(cluster=cluster, download_pcap=dl_pcap, upload_pcap=ul_pcap)


def list_available_clusters() -> list[str]:
    """Return sorted list of cluster names present in the download directory."""
    dl_dir = _download_dir()
    if not dl_dir.is_dir():
        return []
    names = set()
    for f in dl_dir.glob("*.pcap"):
        # e.g. cluster0_tree9_profile869.pcap → cluster0
        parts = f.stem.split("_tree")
        if parts:
            names.add(parts[0])
    return sorted(names)
