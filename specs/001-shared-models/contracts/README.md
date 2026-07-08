# Contracts for feature 001
`test_probe_reference.py` is the reference acceptance suite, produced by the
zero-context build probe (60/60 passing against the docs alone). Cards
C-101–C-104 port it into `shared/tests/` — port, don't rewrite. Imports refer
to the probe's local `models/` package; adjust to `shared.models.*` when
porting.
