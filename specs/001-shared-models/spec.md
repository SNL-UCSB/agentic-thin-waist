# Feature 001 — shared/models foundation (migration step M-1)

## What
The typed foundation every other module imports: units, the A5 experiment-set
models, artifact models A6–A10, capability-file models, identity hashing,
operational defaults, and the lexicon.

## Why
Single point everything blocks on (pragmatist review PR-4). Freezing it first,
with golden fixtures, is what makes 35 student cards parallelizable and makes
further spec ambiguity structurally impossible.

## Normative sources (do NOT restate; reference)
- Models & field lists: docs/PRAMANA_INTERFACE_DEFINITIONS.md §2, §8.1
- Strictness mechanism (StrictModel + lenient()): §2 preamble (BP-6)
- Units grammar + canonical rendering: DESIGN_SPEC §4.2 + defs (BP-1/11)
- Identity/set_hash payload layout + GOLDEN VECTOR #1: defs §8.11b
- Defaults table: DESIGN_SPEC §10 · Lexicon schema: defs §8.15
- Function surface: defs §1.5 (units, hashing, capability loader)

## Acceptance (feature gate = WBS SM-1 milestone)
1. Golden vector #1 reproduced exactly (defs §8.11b) — CI job.
2. Hypothesis property tests: parse∘render idempotent; hash stability under
   input-form variation (30s == {value:30,unit:s} == {value:30000,unit:ms}).
3. Identity excludes placement/iterations/telemetry/verify; includes
   cca/ctp/queue-args/workflow-sha (probe test list is the reference suite:
   see scratchpad build_probe — port, don't rewrite).
4. mypy --strict + ruff clean on shared/ (required status check).

## Out of scope
Match/validation logic (feature 003); REST surface; anything touching
services/*.
