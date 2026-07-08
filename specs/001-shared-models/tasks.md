# Tasks 001 — shared/models
> Status: Ready | Created: 2026-07-03 | SOURCE OF TRUTH: this file.
> GitHub Issues are GENERATED from it (/speckit-taskstoissues, one-way; titles
> `CARD C-<n>: …`); never hand-edit issues. Planning input: WBS SM-1 — on
> scope conflict the WBS wins and this file is regenerated. Suites in
> tests/cards/ precede assignment (Art. VII).

- [ ] C-101 units grammar + canonical rendering (M, student) — suite: tests/cards/test_c101.py
- [ ] C-102 A5 block models vs JSON fixtures (M, student) — suite: tests/cards/test_c102.py
- [ ] C-103 A6–A10 artifact models (M, student) — suite: tests/cards/test_c103.py
- [ ] C-104 RFC 8785 wrapper + identity/set_hash + golden vectors (L, supervisor:Jaber) — suite: tests/cards/test_c104.py
- [ ] C-105 defaults.py + config loader (S, student) — suite: tests/cards/test_c105.py
- [ ] C-106 lexicon.yaml v1 + loader (S, student) — suite: tests/cards/test_c106.py
- [ ] C-107 uv workspace conversion + CI job swap (M, student) — suite: CI itself
- [ ] C-108 JSON Schema build artifact + drift check (S, student) — suite: tests/cards/test_c108.py
Gate: SM-1 milestone green = golden fixtures + hash vectors + mypy/ruff.
