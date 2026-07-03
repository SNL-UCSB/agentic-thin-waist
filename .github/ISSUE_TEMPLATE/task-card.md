---
name: Task card
about: Atomic student-assignable unit (<=3 days) with supervisor-authored failing tests
title: 'CARD <id>: <one-line what>'
labels: card
---

CONTEXT
<!-- <=5 sentences. A student never needs the whole system. -->

INTERFACE
<!-- Verbatim from PRAMANA_INTERFACE_DEFINITIONS.md §<n> (DESIGN_SPEC for intent only) -->

INPUTS
- Skeleton: <path>
- Fixtures: <path>
- Failing suite: tests/cards/test_<id>.py

DONE WHEN
- [ ] `pytest tests/cards/test_<id>.py` green in CI
- [ ] shared/models contract tests green (required check)

MUST NOT
- Touch files outside: <paths>
- Add dependencies (see DESIGN_SPEC §15)
- Change any schema

HANDOFF (fill in the PR body)
- What I did:
- What surprised me:
- Anything flaky:
