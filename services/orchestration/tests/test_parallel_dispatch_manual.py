"""Manual parallelism test for OrchestrationManager.

Patches ``_dispatch_one`` to just sleep for a known duration so we can
measure wall-clock time and prove the thread pool actually fans out.
Not run as part of the standard pytest suite — invoke directly:

    uv run python services/orchestration/tests/test_parallel_dispatch_manual.py
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "services", "orchestration"))
sys.path.insert(0, os.path.join(ROOT, "shared"))

from app.engine.orchestration_manager import (  # noqa: E402
    OrchestrationManager,
)

SLEEP_SECONDS = 3.0
NUM_SPECS = 6


def _make_specs(count: int) -> list[dict[str, Any]]:
    return [
        {
            "experiment_id": f"exp-{i:02d}",
            "capacity_mbps": 10,
            "latency_ms": 20,
            "cc_algorithm": "cubic",
        }
        for i in range(count)
    ]


def _fake_dispatch(sleep_seconds: float, tid_by_spec: dict[str, int]):
    """Return a bound _dispatch_one replacement that sleeps then records thread id."""

    def _dispatch(self, spec, idx, orch_id):  # noqa: ARG001 — signature match
        tid_by_spec[spec["experiment_id"]] = threading.get_ident()
        start = time.monotonic()
        time.sleep(sleep_seconds)
        return {
            "experiment_id": spec["experiment_id"],
            "iteration": idx,
            "orch_id": orch_id,
            "status": "success",
            "worker_id": f"fake-worker-{idx}",
            "wall_elapsed": time.monotonic() - start,
            "thread_id": threading.get_ident(),
        }

    return _dispatch


def _run_once(max_parallel: int, specs: list[dict[str, Any]]) -> dict[str, Any]:
    tid_by_spec: dict[str, int] = {}
    mgr = OrchestrationManager.__new__(OrchestrationManager)
    mgr.manager = None  # never used — _dispatch_one is patched
    mgr.max_parallel = max_parallel

    bound = _fake_dispatch(SLEEP_SECONDS, tid_by_spec)
    OrchestrationManager._dispatch_one = bound  # type: ignore[method-assign]

    start = time.monotonic()
    if max_parallel > 1 and len(specs) > 1:
        results = mgr._run_parallel(specs, orch_id="orch-test")
    else:
        results = mgr._run_sequential(specs, orch_id="orch-test")
    elapsed = time.monotonic() - start

    return {
        "max_parallel": max_parallel,
        "num_specs": len(specs),
        "wall_elapsed": elapsed,
        "unique_threads": len(set(tid_by_spec.values())),
        "thread_ids": tid_by_spec,
        "all_succeeded": all(r["status"] == "success" for r in results),
    }


def main() -> int:
    specs = _make_specs(NUM_SPECS)
    expected_sequential = NUM_SPECS * SLEEP_SECONDS

    print(
        f"[TEST] {NUM_SPECS} specs, each _dispatch_one sleeps {SLEEP_SECONDS:.1f}s\n"
        f"[TEST] Expected sequential wall time ≈ {expected_sequential:.1f}s\n"
    )

    # Sequential baseline
    seq = _run_once(max_parallel=1, specs=specs)
    print(
        f"[SEQ] max_parallel=1 → wall={seq['wall_elapsed']:.2f}s "
        f"unique_threads={seq['unique_threads']}"
    )

    # Full fan-out
    par_full = _run_once(max_parallel=NUM_SPECS, specs=specs)
    ideal_full = SLEEP_SECONDS
    print(
        f"[PAR] max_parallel={NUM_SPECS} → wall={par_full['wall_elapsed']:.2f}s "
        f"unique_threads={par_full['unique_threads']} "
        f"(ideal ≈ {ideal_full:.1f}s)"
    )

    # Half fan-out — should take ≈ 2 * SLEEP
    half = NUM_SPECS // 2
    par_half = _run_once(max_parallel=half, specs=specs)
    ideal_half = SLEEP_SECONDS * (NUM_SPECS / half)
    print(
        f"[PAR] max_parallel={half} → wall={par_half['wall_elapsed']:.2f}s "
        f"unique_threads={par_half['unique_threads']} "
        f"(ideal ≈ {ideal_half:.1f}s)"
    )

    # Simple pass/fail
    tolerance = 1.0  # seconds of slack for thread pool overhead
    ok_seq = abs(seq["wall_elapsed"] - expected_sequential) < tolerance
    ok_full = par_full["wall_elapsed"] < expected_sequential / 2
    ok_half = par_half["wall_elapsed"] < expected_sequential * 0.75
    ok_threads_full = par_full["unique_threads"] == NUM_SPECS
    ok_threads_half = par_half["unique_threads"] == half

    print()
    print(f"[CHECK] sequential ≈ expected:          {ok_seq}")
    print(f"[CHECK] parallel full < seq/2:          {ok_full}")
    print(f"[CHECK] parallel half < seq * 0.75:     {ok_half}")
    print(f"[CHECK] full fan-out used NUM threads:  {ok_threads_full}")
    print(f"[CHECK] half fan-out used max_parallel: {ok_threads_half}")

    all_ok = ok_seq and ok_full and ok_half and ok_threads_full and ok_threads_half
    print()
    print(f"[RESULT] {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
