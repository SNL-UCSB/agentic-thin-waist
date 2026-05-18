"""HTTP client for the Telemetry Service (port 8004).

Wraps `/results`, `/results/{id}`, `/results/{id}/artifacts`, `/artifacts/{id}`
and provides a one-shot `fetch_experiment` that pulls every result + artifact
metadata for a given `experiment_id`, plus a `download_pcap` helper.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests

DEFAULT_BASE_URL = os.environ.get("TELEMETRY_BASE", "http://localhost:8004")


@dataclass
class ExperimentBundle:
    """Everything telemetry knows about a single experiment_id."""

    experiment_id: str
    results: list[dict[str, Any]] = field(default_factory=list)
    artifacts_by_result: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def latest(self) -> Optional[dict[str, Any]]:
        return self.results[0] if self.results else None

    def pcap_artifacts(self, result_id: Optional[str] = None) -> list[dict[str, Any]]:
        target_ids = [result_id] if result_id else list(self.artifacts_by_result.keys())
        out = []
        for rid in target_ids:
            for a in self.artifacts_by_result.get(rid, []):
                fn = (a.get("filename") or "").lower()
                if (a.get("artifact_type") or "").lower() == "pcap" or fn.endswith(
                    (".pcap", ".pcapng")
                ):
                    out.append(a)
        return out

    def qtrace_artifacts(self, result_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Queue-occupancy trace artifacts (JSONL written by /qtrace)."""
        target_ids = [result_id] if result_id else list(self.artifacts_by_result.keys())
        out = []
        for rid in target_ids:
            for a in self.artifacts_by_result.get(rid, []):
                fn = (a.get("filename") or "").lower()
                if (
                    (a.get("artifact_type") or "").lower() == "queue_trace"
                    or fn.endswith(".jsonl")
                ):
                    out.append(a)
        return out


class TelemetryClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._sess = requests.Session()

    def health(self) -> dict[str, Any]:
        r = self._sess.get(f"{self.base_url}/health", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def list_results(
        self,
        experiment_id: Optional[str] = None,
        application: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        **extra: Any,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if experiment_id:
            params["experiment_id"] = experiment_id
        if application:
            params["application"] = application
        params.update({k: v for k, v in extra.items() if v is not None})

        r = self._sess.get(
            f"{self.base_url}/results", params=params, timeout=self.timeout
        )
        r.raise_for_status()
        return r.json().get("results", []) or []

    def get_result(self, result_id: str) -> dict[str, Any]:
        r = self._sess.get(f"{self.base_url}/results/{result_id}", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def list_artifacts(self, result_id: str) -> list[dict[str, Any]]:
        r = self._sess.get(
            f"{self.base_url}/results/{result_id}/artifacts", timeout=self.timeout
        )
        r.raise_for_status()
        return r.json().get("artifacts", []) or []

    def download_artifact(
        self,
        artifact_id: str,
        out_path: str | Path,
        chunk_size: int = 1 << 20,
    ) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with self._sess.get(
            f"{self.base_url}/artifacts/{artifact_id}",
            timeout=max(self.timeout, 120),
            stream=True,
        ) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
        return out_path

    def fetch_experiment(self, experiment_id: str) -> ExperimentBundle:
        """Pull every result for `experiment_id` and the artifact list for each."""
        results = self.list_results(experiment_id=experiment_id, limit=500)
        bundle = ExperimentBundle(experiment_id=experiment_id, results=results)
        for res in results:
            rid = res.get("result_id")
            if not rid:
                continue
            try:
                bundle.artifacts_by_result[rid] = self.list_artifacts(rid)
            except requests.HTTPError:
                bundle.artifacts_by_result[rid] = []
        return bundle

    def download_pcaps(
        self,
        bundle: ExperimentBundle,
        out_dir: str | Path,
        result_id: Optional[str] = None,
    ) -> list[Path]:
        """Download every pcap artifact in `bundle` (or just one result) into `out_dir`.

        Returns the list of local paths written.
        """
        out_dir = Path(out_dir)
        paths: list[Path] = []
        for art in bundle.pcap_artifacts(result_id=result_id):
            fname = art.get("filename") or f"{art['artifact_id']}.pcap"
            paths.append(self.download_artifact(art["artifact_id"], out_dir / fname))
        return paths

    def download_qtraces(
        self,
        bundle: ExperimentBundle,
        out_dir: str | Path,
        result_id: Optional[str] = None,
    ) -> list[Path]:
        """Download every queue_trace artifact in `bundle` into `out_dir`."""
        out_dir = Path(out_dir)
        paths: list[Path] = []
        for art in bundle.qtrace_artifacts(result_id=result_id):
            fname = art.get("filename") or f"{art['artifact_id']}.jsonl"
            paths.append(self.download_artifact(art["artifact_id"], out_dir / fname))
        return paths
