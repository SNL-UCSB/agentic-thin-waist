# Pramana Constitution

<!-- Distilled from docs/PRAMANA_DESIGN_SPEC.md §1 (normative source). If this
     file and the design spec disagree, the design spec wins and this file is
     amended by PR. Every article carries an Enforcement line naming its
     mechanical check; "PENDING" means the check is a committed obligation
     (tracked task), not yet wired — articles may not cite enforcement that
     does not exist. -->

## Article I — The waist rule
`compile()` is the only per-request AI site. No PR may add an LLM/API call to
any execution-path module (scheduler/, substrate/, telemetry, shared/models).
**Enforcement:** specs-lint grep for LLM client imports outside
`orchestration/app/engine/{intent_parser,llm_binding}.py` (PENDING: wired with
migration M-3).

## Article II — Usability tiers order every decision
T1 checkable bar: fresh laptop → `pramana init` → `pramana run
examples/iperf_sweep.yaml` → data in ≤10 min, zero cloud accounts, zero API
keys, no config beyond what `init` writes (= design-spec acceptance criterion
1). Features that raise T1's step count, dependency count, or required config
go to the scale profile. CLI-only; no web UI.
**Enforcement:** acceptance harness job (WBS C-705) — PENDING (job not yet authored).

## Article III — The evidence path is frozen (E1)
No PR may modify files matching `.specify/memory/evidence-path.txt` except
with a `bugfix-evidence-path` label justified in the PR body.
**Enforcement:** specs-lint path check against that allowlist file — PENDING (workflow staged in docs/ci/ until a workflow-scope push).

## Article IV — Contracts over conversations
Wire formats/schemas live only in docs/PRAMANA_INTERFACE_DEFINITIONS.md and,
once code exists, in shared/models (Pydantic = source of truth; JSON Schema a
build artifact). A new need = a missing field, not a new endpoint. Identity
hashing: one shared RFC 8785 function; golden vector #1 (defs §8.11b) must
reproduce.
**Enforcement:** shared-models CI job (golden vectors + mypy --strict + ruff) —
PENDING (staged in docs/ci/ until a workflow-scope push); becomes a required
status check at migration M-1.

## Article V — Hallucination containment
Mechanical form: (a) Match rejects any spec field failing schema/range/enum
validation against pinned capability files — never coerces; (b) endpoint-like
free-form values must match a capability `endpoints:` allow-list or produce a
Question; (c) fuzzy quantifiers resolve only via the pinned lexicon;
(d) the human gate = required PR review on `capabilities/**` and on the
workflow registry (branch protection).
**Enforcement:** (a–c) Match's table-driven test suite (WBS C-601/602);
(d) CODEOWNERS + branch protection (PENDING: set with migration M-2).

## Article VI — Dependency discipline (E6)
The closed tier list is design-spec §15. Adding any dependency requires a §15
entry naming its tier and fence in the same PR; execution-path modules may
import Tier-1 only.
**Enforcement:** specs-lint checks that PRs touching lockfiles/pyproject also
touch design-spec §15 (PENDING: M-1 uv workspace lands first).

## Article VII — Tests define done
A card/feature is complete when its supervisor-authored failing suite
(tests/cards/test_c<n>.py, e.g. test_c101.py) and the shared/models contract tests pass in CI as
required status checks. If acceptance tests cannot be written before
implementation, the interface is not frozen — spec defect; escalate. Test
tasks are MANDATORY in every tasks.md (house tasks template).
**Enforcement:** required status checks (branch protection; set at M-1).

## Article VIII — Brownfield first
Every plan.md must cite the reuse-map row (design-spec §8) for each component
it creates or replaces; creating a new component requires a "replaces X
because Y" line. Plans without reuse citations fail the constitution check.
**Enforcement:** plan-template constitution-check table — PENDING (specs-lint,
staged in docs/ci/, verifies the table exists and every article has a verdict).

## Governance
- **Amendments** by PR touching this file; approver: Arpit + one supervising
  grad student (Manni or Jaber). Semver: MAJOR = article added/removed or
  meaning reversed; MINOR = enforcement added/tightened; PATCH = wording.
- Every plan.md records the constitution version it was gated against;
  specs-lint fails on mismatch with this file's footer.
- Deviations require a `constitution-exception` PR label + justification in
  the plan's Complexity Tracking section.

**Version**: 1.1.0 | **Ratified**: 2026-07-03 | **Last Amended**: 2026-07-03
