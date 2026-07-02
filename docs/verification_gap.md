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

## Related artifacts

- `docs/lit-survey/papers/2026_zhou_netarena.md` — emulator-in-the-loop verification primitive
- `docs/lit-survey/papers/2025_bhatnagar_learned_emulators.md` — symbolic alignment verification primitive
- `docs/lit-survey/paper_outline.md` — to be updated to position verification as a named limitation
- `docs/thin_waist_one_pager.md` — platform framing that this gap directly affects
