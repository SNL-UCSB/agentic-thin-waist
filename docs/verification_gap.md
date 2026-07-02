# Pramana's Verification Gap

**UCSB SNL · 2026-05-12**

## The roadblock

Pramana currently lacks a formal verification layer. This is a fundamental architectural gap, not a polish-pass concern — without it, Pramana's claims about producing "realistic, diverse empirical conditions" are unfalsifiable, which is a reviewer-facing weakness for both HotNets 2026 and (especially) NSDI '27 Frontiers.

The gap became visible when reviewing two papers added to the lit-survey corpus on the same day:

- **NetArena (ICLR '26)** — closes its loop with emulator-in-the-loop per-step safety checks: graph isomorphism / functional equivalence at the final state, plus constraint satisfaction at every intermediate state.
- **A Case for Learned Cloud Emulators (HotNets '25)** — closes its loop with symbolic execution that aligns the generated emulator against the real cloud, surfacing SM/spec divergence as a feedback signal to the LLM.

Both papers borrow credibility from these verification primitives. Pramana has no analog.

## Four verification layers, ordered by tractability

| Layer | Question | Tractability | Closest analog in corpus |
|---|---|---|---|
| **Spec → Substrate** | Did tc/netem actually realize the requested bottleneck regime? | High — measurable via active probing | NetArena per-step safety |
| **Intent → Spec** | Does the compiled experiment spec faithfully capture the NL intent? | Medium — no ground truth; needs round-trip / counterfactual checks | Bhatnagar SM alignment (loose) |
| **Substrate → Result** | Are observed effects attributable to intended conditions vs. confounds? | Low — causal inference under noise; needs control conditions | None |
| **Result → Claim** | Does the conclusion generalize beyond this run? | Low — reproducibility envelope, contamination resistance | None |

## Recommended starting point

The **Spec → Substrate** layer is the most tractable and gives the strongest borrowed-credibility argument:

- Structurally isomorphic to NetArena's per-step safety check, just over a real substrate instead of an emulator.
- Active probing (post-hoc bandwidth/latency/queueing measurement) yields a verifiable "ground truth realized" signal.
- Implementable inside the existing Substrate Worker without rearchitecting other planes.

## Positioning implications

- Treat verification as a **named limitation requiring positioning**, not a future-work footnote, in `docs/lit-survey/paper_outline.md`.
- The harder layers (Intent → Spec, Result → Claim) are where the agentic story lives but have no clean analogs in the reference corpus — flag as open problems rather than overclaim.
- When evaluating future Pramana architectural changes, ask whether the change opens or closes any of these four layers.

## Formal-tool map (added 2026-07-02 — educational, not prioritized)

Intent→Spec decomposes into three sub-problems with different formal status:

| Sub-problem | Formal status | Tool class |
|---|---|---|
| Syntactic validity of model output | **guaranteed by construction** | grammar-constrained decoding (Outlines, llguidance, structured outputs) |
| Semantic well-formedness / capability satisfiability | **decidable** | SMT (Z3/CVC5) over spec+capability constraints — unsat cores become backflow questions; or CUE as the spec language (invalid = unrepresentable) |
| Translation fidelity (spec ≡ intent) | **formally unbridgeable** (NL has no formal semantics) | translation-validation pattern (Pnueli '98; the intent echo is this with a human judge) + metamorphic/property-based testing (paraphrase invariance, monotonicity, unit invariance) + NLI entailment as statistical signal — never presented as verification |

Better formal-methods fits elsewhere in the stack:

- **Spec→Substrate & CTP realization:** Signal Temporal Logic runtime monitors
  (RTAMT, Breach) — regime as temporal formulas over measured series; verdict +
  robustness margin upgrades `verified: true` to a quantitative satisfaction
  degree. The technology that would make "formally verified realized conditions"
  a true sentence.
- **Workflow safety:** NetGent workflows are finite NFAs — decidable model
  checking (domain allow-lists, secret-flow-only-into-declared-fields); makes the
  repo-entry gate partially mechanical.
- **Pool lifecycle protocol:** TLA+/TLC on the claim/heartbeat/reap/retry state
  machine (no-lost-work, no-silent-duplicate, cancellation-reaches-all) — a few
  pages of PlusCal; the highest-ROI formal target since the protocol has no
  implementation to anchor on yet.

## Related artifacts

- `docs/lit-survey/papers/2026_zhou_netarena.md` — emulator-in-the-loop verification primitive
- `docs/lit-survey/papers/2025_bhatnagar_learned_emulators.md` — symbolic alignment verification primitive
- `docs/lit-survey/paper_outline.md` — to be updated to position verification as a named limitation
- `docs/thin_waist_one_pager.md` — platform framing that this gap directly affects
