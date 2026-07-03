# Pramana Constitution

<!-- Distilled from docs/PRAMANA_DESIGN_SPEC.md §1 (normative source). Every
     /speckit-plan and /speckit-implement run is checked against this file.
     If this file and the design spec disagree, the design spec wins and this
     file gets a PR. -->

## Article I — The waist rule
Spend intelligence above the waist, never below it. `compile()` is the only
per-request AI site; everything below the compiled experiment-set spec is
deterministic by construction. No LLM call may be added to any execution path.

## Article II — Usability tiers order every decision
T1 laptop is the primary target: one command to data, keyless via direct spec
submission. T2 cloud reuses the same spec with only `mapping:` changed. Any
feature that helps T2/T3 but adds weight to T1 goes to the scale profile.
CLI-only; no web UI.

## Article III — The evidence path is frozen (E1)
Zoom/HotNets data collection runs on the pre-spec pipeline, bugfix-only.
No task may touch it, depend on it, or block it.

## Article IV — Contracts over conversations
Modules exchange the versioned artifacts defined in
docs/PRAMANA_INTERFACE_DEFINITIONS.md (normative for wire/schema/code detail).
A new need = a missing field, not a new endpoint. Validation is strict at the
compile gate, must-ignore-unknown below it. Identity hashing goes through the
one shared RFC 8785 function; the golden vectors are CI-enforced; no
reimplementation.

## Article V — Hallucination containment
Enumerable fields are closed-world against capability files; free-form fields
are validated, allow-listed, or become questions; fuzzy words resolve only via
the pinned lexicon; every compiled field carries provenance; the user confirms
a plain-language echo before execution; AI-generated artifacts (workflows,
capability files) pass a human gate before entering the system.

## Article VI — Dependency discipline (E6)
The execution path may depend only on Tier-1 (boring, battle-tested) tools.
Anything newer must be dev-time-only, config-swappable, or vendorable, and
must be added to design spec §15 with its tier and fence. Spec Kit itself is
dev-time-only.

## Article VII — Tests define done
A card/feature is complete when its supervisor-authored failing suite and the
shared/models contract tests pass in CI (required status checks). No
judgment-based acceptance. If acceptance tests cannot be written before
implementation, the interface is not frozen — that is a spec defect; escalate.

## Article VIII — Brownfield first
Reuse existing code wherever it satisfies a contract (reuse map: design spec
§8). New components must name what they replace and why refactoring was
insufficient.

**Version**: 1.0.0 | **Ratified**: 2026-07-03 | Source: PRAMANA_DESIGN_SPEC v1.2 (post 7-round audit)
