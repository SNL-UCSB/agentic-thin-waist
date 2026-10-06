# The Prudentia intent in Pramana's grammar

The intent from Pramana §2 — *a real Google Meet call playing the reference Big
Buck Bunny video against a bulk BBR download over a shared drop-tail bottleneck of
≈4×BDP at 8 or 50 Mbps with a normalized 50 ms RTT* — compiled into the grammar of
Figure 2.

Maps to **Prudentia Exp2 / Figure 5** (RTC competition, Jan 2024; metric
definitions in Table 2) — not Fig 2, which is the Exp1 all-pairs MmF heatmap. See
§3 for the Exp1 variant.

---

## 1. The intent (natural language, what the researcher writes once)

> Measure how a real Google Meet call's video quality degrades when it competes
> against a bulk BBR download over a shared drop-tail bottleneck of about 4×BDP,
> at 8 Mbps and 50 Mbps, with every service's RTT normalized to 50 ms. The call
> plays the Big Buck Bunny reference video. Report video resolution, frames per
> second, freezes per minute, and the fraction of packets past the ITU 190 ms
> bar. Run each for 10 minutes, discard the first and last 2 minutes, and repeat
> at least 10 times up to 30 until the 95% CI of the median is within ±0.5 Mbps
> at 8 Mbps and ±1.5 Mbps at 50 Mbps.

---

## 2. The compiled specification — Exp2 / Fig 5

```
Evidence      = collect(ExperimentSet)

ExperimentSet = compile(Intent, Answers)
              = { Experiment(c) | c ∈ {8, 50} Mbps }

Experiment    = ⟨Foreground ⊗ Regime⟩ × iterations

# ── Foreground: what is measured ─────────────────────────────────────────
Foreground    = { W_call @ node_client }

W_call        = CLI(chrome) ⊲ NFA(meet_join ▸ play_bbb ▸ hold(600s))
                with path = ⟨latency  = normalize(50ms),
                             jitter   = 0, loss = 0, reorder = 0, dup = 0⟩
                     cca  = ⟨algo = gcc, stack = webrtc⟩        # observed, not set

# ── Regime: the shared bottleneck + the imposed load ──────────────────────
Regime        = Static⟨capacity↓ = c,
                       capacity↑ = c,
                       queue     = ⟨discipline = droptail_fifo,
                                    size       = pow2(4 × BDP(c, 50ms)),
                                    ecn        = off,
                                    mode       = packets⟩⟩
              ⊗ Dynamic⟨pressure = load(W_bulk ↦ node_contender)⟩

W_bulk        = CLI(iperf3 -R) ⊲ NFA(bulk_transfer(600s))
                with path = ⟨latency  = normalize(50ms),
                             jitter   = 0, loss = 0, reorder = 0, dup = 0⟩
                     cca  = ⟨algo = bbr, stack = linux, version = 5.15⟩

# ── Stopping rule ─────────────────────────────────────────────────────────
iterations    = until(sufficient(signal    = throughput,
                                 precision = ±0.5 Mbps  if c = 8
                                             ±1.5 Mbps  if c = 50),
                      min = 10, max = 30)

identity(e)   = H(workflow@sha, params, path, cca, static, dynamic)
collect       = deploy; prepare; verify; run; publish
```

### Derived values

| | 8 Mbps | 50 Mbps |
|---|---|---|
| `BDP(c, 50ms)` @ 1500 B | 33.3 pkt | 208.3 pkt |
| `4 × BDP` | 133 | 833 |
| `queue.size = pow2(·)` | **128 pkt** | **1024 pkt** |
| `precision` | ±0.5 Mbps | ±1.5 Mbps |

The 50 Mbps column reproduces the paper's own stated 1024 pkt, which is what
validates the rule.

### Notes on three clauses

- **`normalize(50ms)`** — Prudentia's intent is not `latency = 50ms` but
  `latency = 50 − base_rtt(service)`, resolved per workflow against a measured
  base RTT. Measured on this substrate: Meet/Google ≈ 3.97 ms → **+46.03**;
  Vimeo/Cloudflare 3.84 ms → **+46.16**; local iperf3 0.15 ms → **+49.85**. The
  constants are substrate-dependent, so normalization belongs at `prepare`, not
  baked at `compile` — otherwise changing only the node mapping silently changes
  the realized RTT.
- **`cca = bbr` on `W_bulk`** — `-R` makes the **server** the sender, so the
  server's CCA governs the flow. Realizing BBR on a *download* requires a sender
  whose CCA you control (e.g. an in-testbed iperf3 server), not the client's.
- **`signal = throughput`** — `until` stops on a natively reported signal. The
  reported *metrics* (freezes/min, high-delay fraction) are computed, so they are
  reported but are not the stopping signal. Throughput is what Prudentia actually
  specifies.

---

## 3. Exp1 / Fig 2 variant — the all-pairs MmF cell

Identical `Regime`. The difference is **what is measured**: Fig 2's matrix scores
both services (rows = contentiousness, columns = sensitivity), so the bulk flow is
Foreground rather than imposed pressure.

```
Foreground    = { W_video @ node_a,
                  W_bulk  @ node_b }

Regime        = Static⟨capacity↓ = c, capacity↑ = c,
                       queue = ⟨droptail_fifo, pow2(4 × BDP(c, 50ms)), ecn=off, packets⟩⟩
              ⊗ Dynamic⟨pressure = ∅⟩
```

The same iperf3 BBR flow is `Dynamic.pressure` in Exp2 and `Foreground` in Exp1.
The production follows the measurement intent, not the traffic.
