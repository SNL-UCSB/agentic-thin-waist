# The Prudentia intent in Pramana's language

What a researcher writes, what it compiles to, and what has to exist underneath.

Grounded in three sources: Pramana's grammar (Fig 2), Prudentia's actual setup
([`prudentia_rendering.md`](prudentia_rendering.md)), and what this harness was
empirically shown to do on 2026-07-15
([`prudentia_latency_experiment/vimeoiperf3.md`](prudentia_latency_experiment/vimeoiperf3.md)).

---

## 0. Which Prudentia experiment Pramana §2 is actually describing

Pramana's motivating example — *"a real Google Meet call (WebRTC, up to 1.5 Mbps)
playing the reference Big Buck Bunny video against a bulk BBR download … video
resolution, frames per second, freezes per minute, and high-delay packets"* — is
**not** Prudentia's headline Figure 2. It is:

| | |
|---|---|
| **Experiment** | **Exp2** — RTC competition, January 2024 |
| **Figure** | **Figure 5** (metric definitions in **Table 2**) |
| **Incumbents** | Google Meet (GCC, WebRTC, ≤1.5 Mbps, 1 flow); MS Teams (≤2.6 Mbps) |
| **Contenders** | the throughput services — incl. the iPerf BBR/Cubic/NewReno baselines |
| **Metrics** | resolution, avg FPS, freezes/min, fraction of packets > ITU 190 ms |

Worth stating precisely because Exp1 (Fig 2, MmF share) and Exp2 (Fig 5, QoE) are
**different experiments with different grammar needs**, and the distinction decides
the Foreground/pressure question in §3. Pramana's example is one *cell* of Fig 5:
Meet vs bulk BBR.

---

## 1. The intent — what the researcher writes once

> Measure how a real Google Meet call's video quality degrades when it competes
> against a bulk BBR download over a shared drop-tail bottleneck of about 4×BDP,
> at 8 Mbps and 50 Mbps, with every service's RTT normalized to 50 ms. The call
> plays the Big Buck Bunny reference video. Report video resolution, frames per
> second, freezes per minute, and the fraction of packets past the ITU 190 ms
> bar. Run each for 10 minutes, discard the first and last 2 minutes, and repeat
> at least 10 times up to 30 until the 95% CI of the median is within ±0.5 Mbps
> at 8 Mbps and ±1.5 Mbps at 50 Mbps.

That is the whole researcher-authored artifact. Everything below is compiled.

---

## 2. The compiled specification (Fig 2 grammar)

```
ExperimentSet = compile(Intent, Answers)          # 2 Experiments: capacity ∈ {8, 50}

Experiment    = ⟨Foreground ⊗ Regime⟩ × iterations

# ── Foreground: only what is MEASURED ────────────────────────────────────────
Foreground    = { W_call @ node_client }

W_call        = CLI(chrome) ⊲ NFA(meet_join ▸ play_bbb ▸ hold(600s))
                with path = ⟨latency = normalize(50ms),          # ⚠ G1
                             jitter=0, loss=0, reorder=0, dup=0⟩
                     cca  = ⟨algo=gcc, stack=webrtc⟩             # observed, not set

# ── Regime: the shared bottleneck + the imposed load ─────────────────────────
Regime        = Static⟨capacity↓ = 8 | 50 Mbps,
                       capacity↑ = symmetric,
                       queue = ⟨discipline = droptail_fifo,
                                size       = pow2(4 × BDP(capacity, 50ms)),  # ⚠ G2
                                ecn        = off,
                                mode       = packets⟩⟩
              ⊗ Dynamic⟨pressure = load(W_bulk ↦ node_contender)⟩            # ⚠ G4

W_bulk        = CLI(iperf3 -R) ⊲ NFA(bulk_transfer(600s))
                with path = ⟨latency = normalize(50ms)⟩
                     cca  = ⟨algo=bbr, stack=linux, version=5.15⟩            # ⚠ G5

# ── Stopping rule ────────────────────────────────────────────────────────────
iterations    = until(sufficient(signal    = throughput,                     # ⚠ G6
                                 precision = ±0.5Mbps @8 | ±1.5Mbps @50),    # ⚠ G3
                      min = 10, max = 30)

identity(e)   = H(workflow@sha, params, path, cca, static, dynamic)
collect       = deploy; prepare; verify; run; publish
```

`⚠` marks a clause the grammar **cannot express as written**. Six of them, §4.

---

## 3. Foreground or pressure? — resolving the paper's own ambiguity

Pramana §3 says both things about the download:

> "The two competing applications become **a Foreground of two Workflows** pinned
> to nodes: the real Google Meet call … **and a bulk iperf3 transfer** with cca=BBR."

> "**Dynamic pressure** schedules the download as the call's contending load."

It cannot be both, and the grammar permits either — `pressure = load(Workflow* ↦
Node*)` takes the same Workflow type the Foreground does. The distinction is
**semantic, not syntactic: is the flow measured or merely imposed?**

Prudentia settles it, and differently per experiment:

| Prudentia | measured | imposed | ⇒ spec |
|---|---|---|---|
| **Exp2 / Fig 5** (this intent) | the call's QoE only | the download | call = Foreground, download = `Dynamic.pressure.load()` |
| **Exp1 / Fig 2** (all-pairs MmF) | **both** — rows are contentiousness, columns sensitivity | — | **both = Foreground** |

So the *same* iperf3 BBR flow is `pressure` in one intent and `Foreground` in the
other. That is not a defect — it is the grammar correctly encoding what the
researcher is asking about. But it means **Foreground membership is a claim about
measurement intent**, and §3's prose should pick one for the RTC example. For
Fig 5 it is pressure.

*(Empirical note: our own Vimeo-vs-iPerf run is an Exp1/Fig 2 cell, so both flows
are Foreground there — and indeed we measured both.)*

---

## 4. What the grammar cannot say — six gaps

### G1. "Normalized 50 ms RTT" is not expressible, and it breaks portability

`path = ⟨latency, …⟩` is an **absolute** delay. Prudentia's intent is not
"latency = 50 ms" — it is **"latency = 50 − base_rtt(service)"**, where the base
RTT must be *measured first*. From our runs:

| service | endpoint | base RTT | ⇒ path.latency |
|---|---|---|---|
| Vimeo | `104.18.95.41` (Cloudflare) | 3.84 ms | **+46.16 ms** |
| YouTube | `142.251.155.4` (Google) | 3.97 ms | **+46.03 ms** |
| iPerf | `128.111.5.234` (local) | 0.15 ms | **+49.85 ms** |

Three different numbers for one clause of the intent. Worse, they are
**substrate-dependent** — our host sits ~4 ms from a Google cache; from an AWS node
or a PINOT node the same intent compiles to different constants. That directly
contradicts the paper's portability claim:

> "an artifact carries no substrate, so one specification runs on a laptop, in the
> cloud, or on a testbed **by changing only the node mapping**."

If `path.latency = 46.16` is baked at compile, changing the node mapping silently
produces the **wrong RTT**, and the spec no longer means what the researcher wrote.

**Proposed fix:** make normalization a production resolved at `prepare`, not
`compile`:

```
path.latency = normalize(target)            # target = 50ms
             ⇒ prepare: measure base_rtt(endpoint) ; set delay = target − base
             ⇒ publish: realized_rtt per sample (verified | characterized)
```

This fits Pramana's existing machinery exactly — `collect = deploy; prepare;
verify; run; publish` already has a `prepare` and `verify` stage, and the paper
already promises per-factor "verified / characterized / unverified" labels.
Normalization is precisely a *prepare-time measurement + verify-time check*.

### G2. `queue.size = 4×BDP` is derived, and the sweep makes it load-bearing

`queue = ⟨discipline, size, params, ecn, mode⟩` — if `size` is an int, the intent
is lost. BDP depends on **capacity × RTT**, and this intent sweeps capacity:

| capacity | BDP (@50 ms, 1500 B) | 4×BDP | → pow2 |
|---|---|---|---|
| 8 Mbps | 33.3 pkt | 133 | **128 pkt** |
| 50 Mbps | 208.3 pkt | 833 | **1024 pkt** |

*(We validated this rule against the paper's own published number: 50 Mbps × 50 ms
→ 1024 pkt, exactly what Prudentia reports. The rule is right.)*

Write `size = 128` and the 50 Mbps arm runs an **8× under-sized buffer** while
still claiming "4×BDP". `size` must accept an expression over `Static.capacity`
and `path.latency` — otherwise the two Experiments in this one ExperimentSet
cannot share a specification, which is the whole point of the sweep.

### G3. The `until` precision is itself capacity-dependent

Prudentia stops at ±0.5 Mbps @ 8 Mbps but **±1.5 Mbps @ 50 Mbps**. So
`sufficient(signal, precision)` needs `precision` as a function of
`Static.capacity`, not a constant — the same derived-field problem as G2.

### G4. `pressure` needs a schedule, and the grammar has no time

§3 says *"Dynamic pressure **schedules** the download as the call's contending
load"* — but `pressure = replay(ctp) | load(Workflow* ↦ Node*) | both` has **no
temporal operator**. Prudentia's Exp3 (web PLT) is explicit about timing: *"start
contender, **wait 30 s**, load page … repeat 10× with **45 s gaps**"*. And our own
run shows why it matters: iPerf reaching full cwnd *before* the video starts is
exactly what destroyed the video's startup burst (11% retained). Start order is
not a detail — it is the finding.

`load()` needs `at`/`for`/`every`, or the schedule lives outside the spec and the
identity hash misses it — two experiments with identical hashes and different
results.

### G5. `cca` is a Workflow field, but a *download*'s CCA belongs to the sender

`Workflow = CLI(app) ⊲ NFA with path, cca` attaches `cca` to the workflow, i.e. to
the **client node**. But "a bulk BBR **download**" means the **server** sends, so
the *server's* CCA governs the flow. We hit this directly:

- `iperf3 -R` against `128.111.5.234` → the flow ran **Cubic**, because that is the
  server's CCA. Setting the client's CCA would have changed nothing.
- Realizing `cca=BBR` on a download therefore requires either (a) the iperf3
  **server inside the testbed** with BBR set in its namespace — `main_local.py`
  already runs `ip netns exec ns2 iperf3 -s` and the CCA endpoint accepts
  `namespace ∈ {root, ns1, ns2}`, so this is available — or (b) a capability
  declaration from the external server, which no external server offers.

So `cca` is not a property of the workflow; it is a property of **the sender of the
flow the workflow induces**. For uploads those coincide; for downloads they do not.
Prudentia's Table 1 is full of downloads.

### G6. `until(sufficient(signal, …))` cannot stop on this intent's own metrics

The caption is explicit: `until` *"stops on the statistical sufficiency of a
**natively reported** signal, never on a computed result."* But Prudentia Exp2's
metrics are computed:

| metric | native? |
|---|---|
| resolution, FPS | ✅ WebRTC `getStats()` |
| **freezes/min** | ❌ *computed* — inter-arrival > `max(3δ, δ+150 ms)` |
| **high-delay packets** | ❌ *computed* — fraction past the ITU 190 ms bar |

So the headline metrics of the experiment cannot be the `until` signal. Our spec
above therefore stops on `throughput` — which is native, and is what Prudentia
actually specifies. **Consistent, but worth making explicit**: the stopping signal
and the reported metric are different quantities, by design.

This is the sharp edge of the paper's deliberate choice to keep metric extraction
outside the contract:

> "pulling metric extraction into the contract would fix a universe of metrics"

Fair — but Prudentia Exp2's **intent *is* its metrics**. "Examine the impact
contention has on resolution, FPS, freezes, and high-delay packets" *is* the
sentence. A spec that cannot name them has compiled the setup but not the
question. The resolution is that the **workflow's capability file** must declare
what it natively reports, and the Meet workflow must emit `getStats()`. Which
brings us to what is missing here.

---

## 5. Required things — capability files and mechanisms

### 5.1 What this repo already has (verified)

| Requirement | Status | Evidence |
|---|---|---|
| Shared bottleneck: HTB + drop-tail FIFO, sized | ✅ | `POST /shape`, `buffer_packets` |
| **Per-workflow `path`** (the Fig 2 "approximate, per-workflow route") | ✅ | `POST /shape/per_app_marks` — per-app netem lanes via src-IP aliases + CONNMARK; **this is exactly the `path` production** |
| Real browser app driving | ✅ | netgent `runtime: browser` via ns1 proxy |
| **Backlogged bulk contender on the shaped path** | ✅ | `runtime: shell` → `nsenter … ip netns exec ns1 iperf3` — verified 7.6/8 Mbps, `local_host=172.16.1.1` |
| `cca` as a structured object | ✅ | 14 CCAnalyzer CCAs modprobe'd; `namespace ∈ {root, ns1, ns2}` |
| **CCA verification** (was it *actually* used?) | ✅ | `/run` returns `congestion_observed` from `ss -tin` inside ns1 — "rather than silently downgraded to cubic". This is Pramana's per-factor *verified* label, already built. |
| Queue telemetry (Fig 11/12/13) | ✅ | `POST /qtrace` — backlog, drops, bytes_sent @ 10 ms |
| Local iperf3 server (⇒ settable sender CCA, G5) | ✅ | `ip netns exec ns2 iperf3 -s`, target `172.16.3.1` |

### 5.2 What is missing — the worklist for this one intent

| # | Gap | Why it blocks the intent |
|---|---|---|
| **R1** | **WebRTC QoE extraction.** `grep getStats\|framesPerSecond\|freeze\|jitterBufferDelay` over netgent → **zero hits**. `run_meet_workflow.json` is `go_to_url ▸ input_text ▸ click_element ▸ wait` — it joins a call and waits. | **The metrics Exp2 is *about* do not exist.** Nothing reports resolution, FPS, freezes, or high-delay packets. This is the single blocking addition. |
| **R2** | `normalize(target)` production + prepare-time base-RTT probe | G1 — without it the spec is substrate-bound and portability is false |
| **R3** | Derived fields: `queue.size = f(capacity, rtt)`, `precision = f(capacity)` | G2, G3 — without them the 8/50 sweep needs two hand-written specs |
| **R4** | Schedule operators on `pressure.load()` | G4 — start order determines the result |
| **R5** | Sender-side `cca` for download flows (or ns2-local server as the mechanism) | G5 — "bulk BBR download" is otherwise unrealizable against an external server |
| **R6** | A 10-minute reference video | Prudentia discards the first/last 2 min of a 10-min run. Our Vimeo clip is **~30 s**, so the discard rule is inapplicable and every number we have is startup-phase. |
| **R7** | Viewport ≥ 1080p for ABR services | browserless' 1280×720 default pins the ABR ladder at ~720p → YouTube demands 2.4 Mbps even on an *unconstrained* 100 Mbps link. Prudentia drove real 4K monitors for exactly this reason. |

R1 and R6 are the two that make the difference between "we ran Prudentia's setup"
and "we measured what Prudentia measured."

### 5.3 Capability files this intent would need

Per the paper, every field is "drawn from a service's declared capability or
rejected at compile." For this one intent:

```yaml
netgent.capability:
  workflows:
    prudentia_meet_rtc:
      runtime: browser
      params: [meeting_code, watch_seconds]
      natively_reports:                 # ← R1: none of this exists today
        - frameHeight | frameWidth      # resolution
        - framesPerSecond
        - freezeCount, totalFreezesDuration
        - jitterBufferDelay, packetsLost
      requires: {viewport: ">=1920x1080"}   # ← R7
  runtimes: [browser, shell]

substrate.capability:
  static:
    capacity_mbps: {min: 0.1, max: 1000}
    queue: {discipline: [pfifo, fq_codel, ...], size_pkts: {...}, ecn: [on, off]}
  path:                                  # per-workflow netem lanes
    latency_ms: {min: 0, max: 2000, per_workflow: true}
    normalize:  {supported: false}       # ← R2
  cca:
    algos: [bbr, bic, cdg, cubic, highspeed, htcp, hybla, illinois,
            nv, reno, scalable, vegas, veno, westwood, yeah]
    namespaces: [root, ns1, ns2]
    verified_by: "ss -tin (congestion_observed)"
    sender_side_for_downloads: false     # ← R5
  telemetry: [pcap, qtrace]
```

The `supported: false` / `false` entries are what a **gate-and-echo compile would
catch**. That is the design working: this intent would be *rejected at compile*
today rather than silently mis-run — which is precisely the failure we hit by hand
(a YouTube workflow that reported `ok` while returning `success: False`, and a 4K
viewport setting that silently never applied).

---

## 6. The honest summary

**The grammar gets the hard parts right.** `path` per workflow is exactly the
per-app netem lane mechanism, and it is the non-obvious piece — we built it and it
works. `Regime = Static ⊗ Dynamic` is the right cut. `until(sufficient(…), min,
max)` maps 1:1 onto Prudentia's ≥10-up-to-30 stopping rule. `identity = H(…)` over
`(workflow, params, path, cca, static, dynamic)` is the right key.

**Its gaps are all one shape:** the grammar states **absolute values** where
Prudentia's intent states **relations** — normalize *to* 50 ms, size *to* 4×BDP,
tighten *until* the CI closes, at a precision *scaled to* capacity. Every ⚠ in §2
is a derived quantity that must be resolved against a measurement of the substrate,
at `prepare`, not against a constant at `compile`.

That is a good problem to have: `collect = deploy; prepare; verify; run; publish`
already has the stages to resolve them, and the paper already promises per-factor
verified/characterized/unverified labels. **The fix is to let derived fields be
first-class in the language rather than folding them into the researcher's head** —
because a constant baked at compile is exactly what makes a spec substrate-bound,
and portability is the claim the whole thin waist rests on.
