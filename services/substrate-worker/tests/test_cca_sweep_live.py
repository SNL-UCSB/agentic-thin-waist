"""Live sweep of all 15 CCAnalyzer CCAs against a running substrate-worker.

Skipped by default — opt in by setting ``RUN_CCA_SWEEP=1`` and pointing
``SUBSTRATE_API_URL`` (defaults to ``http://localhost:8002``) at a running
worker. The test asks the worker to set each algorithm in turn, runs a short
wget through ``/run``, and asserts the runtime observer recorded the algorithm
on at least one socket.

This is the canonical end-to-end check for issue #142. On Docker Desktop's
LinuxKit kernel only cubic + reno will pass (the rest fail at the modprobe
step with a clear diagnostic). On a real Linux host with ``linux-modules-extra``
+ a ``/lib/modules:/lib/modules:ro`` mount, all 15 should pass.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

WORKER = os.environ.get("SUBSTRATE_API_URL", "http://localhost:8002").rstrip("/")

ALL_CCAS = (
    "bbr",
    "bic",
    "cdg",
    "cubic",
    "highspeed",
    "htcp",
    "hybla",
    "illinois",
    "nv",
    "reno",
    "scalable",
    "vegas",
    "veno",
    "westwood",
    "yeah",
)


def _post(path: str, body: dict, timeout: float = 60) -> tuple[int, dict]:
    """POST to the substrate worker. Returns (status, parsed JSON body)."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{WORKER}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.fixture(scope="module")
def worker_reachable() -> bool:
    if not os.environ.get("RUN_CCA_SWEEP"):
        pytest.skip("RUN_CCA_SWEEP not set — opt in to run the live sweep")
    try:
        with urllib.request.urlopen(f"{WORKER}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        pytest.skip(f"Substrate worker at {WORKER} unreachable")


@pytest.mark.parametrize("cca", ALL_CCAS)
def test_cca_round_trip(cca: str, worker_reachable: bool) -> None:
    """For each CCA: set it, run a short wget, assert the observer saw it.

    Two acceptable outcomes by default:
      - 200 from /congestion → /run completes and `congestion_observed`
        contains the requested algorithm (the application actually used it).
      - 400 from /congestion with the structured "not available in this kernel"
        message → algorithm is in the whitelist but this kernel doesn't have
        the module loadable. Treated as a soft pass so the suite runs cleanly
        on Docker Desktop's LinuxKit kernel.

    Strict mode (``REQUIRE_ALL_CCAS=1``): kernel-unavailable 400s are treated
    as failures. CI on a real Linux host uses this mode to verify all 15
    CCAnalyzer algorithms genuinely work end-to-end.
    """
    strict = bool(os.environ.get("REQUIRE_ALL_CCAS"))
    status, body = _post("/congestion", {"algorithm": cca, "namespace": "ns1"})
    if status == 400:
        detail = body.get("detail", "")
        if strict:
            pytest.fail(
                f"{cca}: /congestion returned 400 in strict mode — host kernel "
                f"is missing the module. detail: {detail}"
            )
        assert (
            "not available in this kernel" in detail
        ), f"{cca}: unexpected 400 detail — {detail}"
        return

    assert status == 200, f"{cca}: /congestion returned {status}: {body}"
    assert body.get("current_algorithm") == cca

    run_status, run_body = _post(
        "/run",
        {
            "runtime": "shell",
            "cca": cca,
            "cca_namespace": "ns1",
            "experiment_max_seconds": 12,
            "workflow": {
                "specification": "wget",
                "states": [
                    {
                        "checks": [{"type": "always_true", "params": {}}],
                        "actions": [
                            {
                                "type": "wget",
                                "params": {"url": "{{url}}"},
                            }
                        ],
                    }
                ],
                "parameters": ["url"],
            },
            "parameters": {"url": "https://speed.cloudflare.com/__down?bytes=5242880"},
        },
        timeout=120,
    )
    assert run_status == 200, f"{cca}: /run returned {run_status}: {run_body}"
    observed = run_body.get("congestion_observed", {})
    assert cca in observed, (
        f"{cca}: configured but not observed on any TCP socket during run "
        f"(observed={observed}). Possible silent kernel downgrade to cubic."
    )
    assert observed[cca] > 0
