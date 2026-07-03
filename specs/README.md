# Spec-driven workflow (Spec Kit)

**Order:** `/speckit-specify` (new feature dir) → `/speckit-clarify` →
`/speckit-plan` (constitution check, versioned) → `/speckit-tasks` →
`/speckit-taskstoissues` (generates GitHub issues; ONE-WAY) →
`/speckit-implement`. The constitution lives at
`.specify/memory/constitution.md` and gates every plan.

**Task authority (one ruling):** each feature's `tasks.md` is the source of
truth for execution state; GitHub Issues are GENERATED from it (card-aware
patched skill; titles `CARD C-<n>: …`) and never hand-edited; the WBS
(docs/PRAMANA_WBS.md) is the planning input — on scope conflicts the WBS
wins and tasks.md is regenerated; closures reconcile at each milestone gate.

**Repo conventions:** house-style templates live in
`.specify/templates/overrides/` (terse, reference-first — NEVER restate
schemas from the canonical docs; specs-lint checks references resolve). Task
IDs use the card namespace `C-<n>`, not upstream's `T###`. Feature branches
use spec-kit's `NNN-name` scheme — the sanctioned exception to the repo's
`<user>/<area>/<desc>` convention. Research/data-model/quickstart artifacts
are optional for internal-library features; `contracts/` holds reference
suites. Feature selection for the skills: `export
SPECIFY_FEATURE_DIRECTORY=specs/<NNN-name>` (`.specify/feature.json` is
per-user local state, gitignored). The plan step's "update agent context" is
a documented no-op here (`update-agent-context.sh`).
