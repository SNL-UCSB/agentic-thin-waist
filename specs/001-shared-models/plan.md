# Plan 001 — shared/models

Constitution check: Articles IV (contracts), VI (deps: pydantic v2 + rfc8785 +
hypothesis only — all Tier 1/2, already fenced), VII (tests first), VIII
(brownfield: shared/db + shared/s3 untouched and reused).

Stack: Python 3.11, Pydantic v2 (repo standard), rfc8785 (vendorable), pytest
+ hypothesis. uv workspace member `agentic-thin-waist-shared` (AP-14).

Layout (defs §1): shared/models/{units,spec,artifacts,capability,hashing,
defaults}.py + lexicon.yaml + fixtures/ + shared/tests/.

Starter: the build-probe implementation (60/60 passing, written from the spec
alone) is the reference; port with the 14 BP-corrections already folded into
the docs (normalization at construction, StrictModel base, render() naming).

Order: units -> spec models -> hashing + golden vectors -> artifacts ->
capability loader -> defaults/lexicon -> JSON Schema build artifact (CI).
