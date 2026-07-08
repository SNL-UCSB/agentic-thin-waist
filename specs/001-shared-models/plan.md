# Plan 001 — shared/models
> Status: Ready | Created: 2026-07-03 | Constitution: v1.1.0

Constitution check (v1.1.0) — per-article verdicts:
| Art | Verdict |
|---|---|
| I waist | PASS — no LLM anywhere in shared/ |
| II tiers | PASS — no runtime surface |
| III evidence path | PASS — no frozen files touched |
| IV contracts | PASS — implements the canonical schemas + golden vector |
| V containment | N/A — no AI surface |
| VI dependencies | PASS — pydantic/rfc8785/hypothesis, tiers fenced in §15 |
| VII tests-define-done | PASS — reference suite committed; card suites precede assignment |
| VIII brownfield | PASS — shared/db + shared/s3 reused untouched (reuse map §8) |

Legacy summary: Articles IV (contracts), VI (deps: pydantic v2 + rfc8785 +
hypothesis only — all Tier 1/2, already fenced), VII (tests first), VIII
(brownfield: shared/db + shared/s3 untouched and reused).

Stack: Python 3.11, Pydantic v2 (repo standard), rfc8785 (vendorable), pytest
+ hypothesis. uv workspace member `agentic-thin-waist-shared` (per the dependency-management ruling in docs/pramana_adversarial_review_2026-07-02.md §SE, finding AP-14).

Layout (defs §1): shared/models/{units,spec,artifacts,capability,hashing,
defaults}.py + lexicon.yaml + fixtures/ + shared/tests/.

Starter: the committed reference suite (contracts/test_probe_reference.py,
from the build probe — 60/60 passing, written from the spec alone); port with the 14 BP-corrections already folded into
the docs (normalization at construction, StrictModel base, render() naming).

Order: units -> spec models -> hashing + golden vectors -> artifacts ->
capability loader -> defaults/lexicon -> JSON Schema build artifact (CI).
