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

## Verification roadmap — a grounded exercise (2026-07-02)

Method: the candidate tool papers were ingested into the survey NotebookLM
(Maler & Nickovic '04 STL; Nickovic & Yamaguchi '20 RTAMT; Necula '00 translation
validation; Barrett et al. SMT Handbook ch. 26; Willard & Louf '23 constrained
decoding; Segura et al. '16 metamorphic testing survey; Newcombe et al. '15
TLA+ at AWS) and queried for their stated *prerequisites* and *guarantees*. The
question was open — can existing tools satisfy Pramana's verification
requirements? — and the verdicts below follow from the papers' own statements,
not from a prior hypothesis. Register of quotes: notebook
`survey-agentic-systems-research`.

### Verdict table

| # | Pramana requirement | Candidate tool | Grounded verdict |
|---|---|---|---|
| V1 | LLM output is syntactically valid spec | Grammar-constrained decoding (Willard & Louf) | **SATISFIED by construction** — "guaranteeing the structure of the generated text"; explicitly syntactic only, "not semantically-correct" |
| V2 | Spec is well-formed vs. capabilities (ranges, dependencies, feasibility) | SMT (Barrett et al.) | **SATISFIED with engineering** — linear arithmetic/EUF/arrays decidable; **unsat cores** supported (CVC3/MathSAT/Yices) ⇒ machine-generated backflow explanations |
| V3 | Compiled spec faithfully captures NL intent | Translation validation (Necula) | **CANNOT** — requires a simulation relation over *two formal programs*; "the formal semantics… would be missing" for NL. Metamorphic testing (Segura) covers *consistency across paraphrasings*, not ground truth, with documented false-positive risk. Residual: the intent echo (translation-validation *pattern* with a human judge) + metamorphic paraphrase-invariance testing is the ceiling |
| V4 | Realized static envelope conforms to spec (imposed regimes) | STL monitors (Maler; RTAMT) | **SATISFIED with engineering** — boolean + quantitative robustness verdicts over measured signals; online monitoring supported |
| V5 | Realized dynamic pressure conforms to CTP descriptors | STL | **PARTIAL** — per-trace windowed descriptors work via Maler's pre-transform move ("pass the signal first through the transform… then check whether the result satisfies the formula"): windowed PMR/CoV become derived signals. But STL "cannot quantify over a distribution of traces" — ensemble-level conformance (run-to-run reproducibility, profile-level statistical equivalence) is outside the logic |
| V6 | Pool lifecycle protocol correct (claim/reap/retry/cancel) | TLA+ (Newcombe et al.) | **SATISFIED, with named limits** — AWS verified exactly this class (replication, membership, concurrency; bugs at 35-step depth; engineers productive in 2–3 weeks). Limits are the paper's own: design ≠ implementation ("How do we know the executable code correctly implements the verified design? …we don't"), no hard real-time properties, and liveness must be explicitly checked (their lock-manager miss) |
| V7 | Workflow safety (domain allow-lists, secret flow) | Finite-state analysis | **SATISFIED** — NetGent workflows are finite NFAs; reachability over the JSON suffices; standard model checking if pedigree wanted |
| V8 | End-to-end claim composed from V1–V7's heterogeneous guarantees | — | **NO TOOL IN CORPUS** — nothing addresses composing by-construction guarantees, SMT proofs, STL robustness margins, statistical confidence, and design-level model-checking into one quantified dataset-validity statement |

### The exercise's honest summary

Most of Pramana's verification requirements are **satisfiable with existing
tools** — V1 by construction, V2/V4/V6/V7 with ordinary engineering. The gaps
that survive grounding are specific:

1. **Distributional conformance monitoring (V5 residual).** Runtime verification
   is defined as a membership test on an *individual* trace; Pramana's dynamic
   half needs verdicts of the form "this ensemble of measured traces conforms to
   this statistical profile (PMR range, autocorrelation, CoV) with confidence
   c" — plus a robustness analog (divergence margin). *Before claiming novelty:*
   statistical model checking, stochastic STL variants, and conformal methods
   are not yet in this corpus and must be surveyed first (backlogged below).
2. **Certificates for NL→configuration compilation (V3 residual).** Simulation
   relations need semantics NL lacks; what *is* mechanically checkable is the
   derivation — a certificate that every spec field is derived from attributable
   evidence (capability entry, lexicon rule, user answer), with the semantic
   step delegated to a human-judged echo. What such a certificate must contain
   to be sound, and what "sound" even means here, is unformalized — a genuine
   open problem to put in front of verification researchers.
3. **A composition calculus for heterogeneous verdicts (V8).** Per-layer
   guarantees are of different kinds (construction, proof, robustness margin,
   confidence, design-level). How they compose into an end-to-end, quantified
   claim about a dataset is unaddressed in this corpus.
4. **Practical caveat for V6:** heartbeat/timeout liveness sits exactly in AWS's
   stated blind spot (no hard real-time modeling) — timing assumptions must be
   explicit parameters of the TLA+ model, checked separately by measurement.

### Corpus expansion candidates (before any novelty claim)

| Paper/area | Reason |
|---|---|
| Statistical model checking (Legay et al. survey; PRISM/UPPAAL-SMC) | direct candidate for gap 1 |
| Stochastic/probabilistic STL (StSTL, PrSTL); conformal prediction for RV | gap 1 adjacent |
| Certifying compilers / proof-carrying code (Necula & Lee) | gap 2 ancestor — certificates without re-verification |
| NL2SQL / semantic-parsing evaluation methodology | gap 2 adjacent — how that community bounds translation fidelity |

## Related artifacts

- `docs/lit-survey/papers/2026_zhou_netarena.md` — emulator-in-the-loop verification primitive
- `docs/lit-survey/papers/2025_bhatnagar_learned_emulators.md` — symbolic alignment verification primitive
- `docs/lit-survey/paper_outline.md` — to be updated to position verification as a named limitation
- `docs/thin_waist_one_pager.md` — platform framing that this gap directly affects
