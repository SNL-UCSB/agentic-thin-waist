# Pending CI workflows (needs `workflow`-scope push)

These two files belong in `.github/workflows/` but were staged here because
the authoring session's GitHub token lacked the `workflow` OAuth scope.
Whoever next pushes with normal permissions (or from the GitHub web UI):
move both files to `.github/workflows/`, then delete this directory.

- `specs-lint.yml` — enforces constitution Art. III (frozen evidence paths),
  spec structure, reference resolution, and the constitution-version gate.
- `shared-models.yml` — the Art. IV/VII gate: ruff + mypy --strict + pytest
  on shared/models (required status check from migration M-1).

Until moved, the constitution's Enforcement lines for these checks are
PENDING by definition.
