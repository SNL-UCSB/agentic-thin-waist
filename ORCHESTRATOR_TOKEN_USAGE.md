# Orchestrator Token Usage — Measurements & Sweep Analysis

How many Anthropic (orchestrator-LLM) tokens one intent costs, what the LLM
calls are spent on, and what happens to token usage when you sweep a parameter
such as bandwidth. All numbers are measured from live runs of the README wget
example against the running stack — they count **only** the orchestrator's own
Anthropic key usage (via `langchain_anthropic`), not the Claude Code CLI.

Per-intent numbers are recorded automatically to
`services/orchestration/intent_tokens.md` (one section per submitted intent).

---

## 1. Measured token usage for the README wget intent

**Intent:** *"Run a wget download from `https://speed.cloudflare.com/__down?bytes=10485760`
over a 10 Mbps bottleneck with 20 ms added latency, pfifo queue, the queue size
of 200 packets and cubic congestion control. One trial, 30 seconds"*

**Provider / model:** `anthropic` / `claude-sonnet-4-6` · **Status:** complete

| Metric | Value |
|---|---|
| **Total tokens** | **≈ 15,863** |
| Input tokens | 14,611 |
| Output tokens | 1,252 |
| Orchestrator LLM calls | 3 |
| Experiments generated | 1 |

> A second identical run recorded **14,611 input / 1,281 output / 15,892 total** —
> input tokens were *byte-for-byte identical*, output wobbled by ~2%. (See §3.)

---

## 2. What the 3 LLM calls do, and tokens per call

Each intent runs a LangGraph pipeline that makes **three** structured-output LLM
calls. Measured split for the run above (`orch-96008194`):

| # | Call (graph node) | Purpose | Input | Output | Total |
|---|---|---|---:|---:|---:|
| 1 | `parse_intent` → `ParsedIntent` | Extracts structured params (CC, capacity, latency, AQM, buffer, trials, duration, app) from the natural-language intent. Carries the large **few-shot examples block**, so it's by far the biggest call. | 12,282 | 605 | **12,887** |
| 2 | `choose_workflow` → `ChooseWorkflow` | Picks the matching NetGent workflow from the shell workflow **library** for this intent. | 1,259 | 279 | **1,538** |
| 3 | `choose_workflow` → `MapWorkflowParams` | Maps the parsed intent parameters onto the chosen workflow's parameter slots. | 1,070 | 368 | **1,438** |
| | **Total** | | **14,611** | **1,252** | **15,863** |

**Takeaway:** call #1 (`parse_intent`) is ~81% of all tokens, dominated by the
static few-shot examples prompt. Calls #2 and #3 (workflow selection + parameter
mapping) are small (~1.5k each) and dominated by the workflow-library context.

---

## 3. Does a bandwidth sweep cost the same tokens per intent?

**Yes — each swept intent costs essentially the same (~15.9k tokens), because
every intent is built from scratch and nothing is reused between runs.**

Why the count barely moves when you change only the bandwidth:

- **Input tokens (~14.6k) are dominated by the *static* prefix**, not your intent
  text: the fixed system prompt + few-shot examples (call #1) and the fixed
  workflow-library context (calls #2/#3). Those bytes are identical across a sweep.
- **The intent string is the only thing that changes**, and only by a couple of
  digits (`"10 Mbps"` → `"20 Mbps"`) — a difference of ~0–1 tokens.
- **Output tokens (~1.25k)** are the structured results; same shape every run, so
  they vary by only a few percent.

**Empirical proof** — two runs of the *same* intent:

| Run | Input | Output | Total |
|---|---:|---:|---:|
| `orch-be550ec2` | 14,611 | 1,281 | 15,892 |
| `orch-96008194` | 14,611 | 1,252 | 15,863 |

Input was **identical**; only output moved (~2%). A bandwidth-only change would
behave the same. So a 5-point sweep ≈ 5 × ~15.9k ≈ **~79k tokens**, near-linear.

### The key nuance: there is no prompt caching today

`get_model()` builds `ChatAnthropic` with no `cache_control`, so the identical
~14.6k-token prefix is **re-processed at full input price on every run** — you get
zero savings from the repetition even though ~92% of each request is identical.
That repeated prefix is the real cost driver of a sweep.

### Two ways to cut sweep cost

1. **Prompt caching** — mark the static system/few-shot/library prefix with
   `cache_control: {"type": "ephemeral"}`. Token *count* stays about the same, but
   cached input reads cost ~0.1× instead of 1×, cutting input **cost** ~90% on
   runs 2..N within the 5-minute cache TTL. Highest-leverage fix for a sweep.
2. **Skip the LLM for pure numeric sweeps** — the request `context` block already
   deterministically pins every parameter (`cc_algorithms`, `buffer_packets`, …)
   via `intent_overrides`, yet `parse_intent` still calls the LLM and the overrides
   just replace its output afterward. For a mechanical bandwidth sweep where all
   params are already known, that call (call #1, ~12.9k tokens = ~81% of the cost)
   is redundant. A fast-path that skips parsing when the context fully specifies
   the experiment would take those runs to near-zero orchestrator tokens.

---

## 4. How this is tracked

- A LangChain callback (`TokenUsageCallback` in
  `services/orchestration/app/engine/token_tracker.py`) aggregates
  `usage_metadata` across every LLM call in a run — including per-call detail
  labeled by graph node.
- `OrchestratorAgent.run()` attaches it to `graph.invoke(config={"callbacks":[…]})`;
  after each intent it appends a record (total, per-model, **per-call**, parsed
  params, status) to `services/orchestration/intent_tokens.md`.
- The orchestrator reads its Anthropic key from the repo-root `.env`
  (`ANTHROPIC_API_KEY`), wired through docker-compose and `load_dotenv()`.
