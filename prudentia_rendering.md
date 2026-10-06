# Prudentia — Experiment-to-Figure Mapping and Experimental Setup

Paper: *Prudentia: Findings of an Internet Fairness Watchdog* (Adithya Abraham Philip, Rukshani Athapathu, Ranysha Ware, Fabian Francis Mkocheko, Alexis Schlomer, Mengrou Shou, Zili Meng, Srinivasan Seshan, Justine Sherry — ACM SIGCOMM 2024).

This document maps every figure and table to the underlying experiment(s) that produced its data, following the "count experiments by distinct data-collection setup" rule.

> ## Correction note (re-analysis under updated rules)
> This rendering was revised after applying the updated "what counts as one experiment" rules. Changes vs. the previous version:
>
> 1. **The bulk experiment ID kept (old Exp1 → new Exp1).** Figs 2, 3, 10, 11, 12, 13 and Table 3 remain one experiment (the main 2023 all-pairs run) — this was already correct. Figs 11/12/13 are BESS-recorded link-utilization / packet-loss / queuing-delay *telemetry off the same runs* (rule 4), and Table 3 is *extracted from Fig 2's data* (rule 3), so none is a new experiment.
> 2. **Figure 4 split into two experiments.** The previous version folded the whole figure into old Exp1. Observation 4 says the "five iPerf BBR flows" comparison came from **"separate experiments"** — a distinct workload (5 concurrent iPerf BBR flows, not the single-flow iPerf baseline in Table 1). So Fig 4 now maps to **Exp1** (the Dropbox-vs-Mega time-series, part of the main all-pairs run) **and** the new **Exp4** (5-flow iPerf BBR competition).
> 3. **Figure 8 now maps to two experiments.** Fig 8a is the 4×BDP queue-occupancy time-series of a NewReno-iPerf-vs-Mega run — a *different signal (queue occupancy) off a run already in the main campaign* (rule 4) → **Exp1**. Fig 8b is the doubled-buffer (8×BDP) run → the new-network-condition experiment **Exp6**. (Previously the whole figure was a single new experiment, old Exp5.)
> 4. **Figure 9 split and cross-linked.** The previous version put Fig 9 in one experiment (old Exp6). Fig 9a compares **2023 vs 2022** measurements of YouTube/Google Drive vs iPerf-BBR: the **2023 bars are part of the main all-pairs run (Exp1)** and the **2022 bars are a separate 2022 collection (new Exp7)**, so Fig 9a maps to **both**. Fig 9b compares **Linux-kernel BBR 4.15 vs 5.15** — a distinct CCA-version collection → new **Exp8**. Fig 9 column therefore carries **Exp1 + Exp7 + Exp8**.
>
> Net renumbering: old Exp1 = new Exp1; old Exp2 = new Exp2; old Exp3 = new Exp3; old Exp4 (bandwidth sweep) = new **Exp5**; old Exp5 (buffer) = new **Exp6** (and Fig 8a now also credited to Exp1); old Exp6 (longitudinal) is now split into new **Exp7** (2022 collection) + new **Exp8** (kernel comparison), with the 2023 half credited to Exp1. New **Exp4** (5-flow iPerf BBR) added.

> **Non-experimental items:**
> - **Figure 1** — the dumbbell testbed topology diagram (illustration, no data).
> - **Table 1** — list of services supported in the testbed (CCA, max throughput, flow count) — definitional.
> - **Table 2** — definitions of the RTC quality metrics (resolution, FPS, freezes/min, high-delay packets) — definitional.
>
> **Shared testbed (all measured experiments):** A **dumbbell topology** with two clients each receiving from one of two live, deployed Internet services; all traffic passes through a **BESS software switch** acting as the controlled bottleneck (sets access-link speed, queue size, added delay; also measures queue occupancy and packet loss). Wired links, no artificial loss/reordering (loss comes from bottleneck queue overflow). **Drop-tail FIFO queue sized ≈ 4×BDP** (rounded to nearest power of two by BESS). **RTT normalized to 50 ms** for all services (extra delay inserted; highest measured service RTT was 40 ms). Two standard bandwidth settings: **8 Mbps ("highly-constrained")** and **50 Mbps ("moderately-constrained")**. Application fidelity via **Google Chrome + Selenium** (cache/cookies wiped between runs); video on **Mac Mini desktops with a desktop-marketed GPU and a real 4K monitor** (headless/virtual displays biased bitrate selection). File-transfer services download the same **10 GB random file**; video/RTC play the **Big Buck Bunny** reference video. Each experiment runs **10 minutes** (first & last 2 min discarded), **≥10 trials up to 30** (until 95% CI of the median within ±0.5 Mbps @8 Mbps / ±1.5 Mbps @50 Mbps), round-robin scheduling, discarding runs with >0.05% external loss. Data reported is from **June–Sept 2023** (RTC from **Jan 2024**; longitudinal/sweep experiments from **2022**).

---

## Part 1: Experiment-to-Figure/Table Mapping

| Experiment | Fig.1 | Tab.1 | Fig.2 | Fig.3 | Fig.4 | Fig.5 | Tab.2 | Fig.6 | Fig.7 | Fig.8 | Tab.3 | Fig.9 | Fig.10 | Fig.11 | Fig.12 | Fig.13 |
|------------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|--------|--------|--------|--------|
| Exp1 — Main all-pairs throughput competition (video + file transfer + single-flow iPerf), 8 & 50 Mbps, June–Sept 2023 |   |   | ✓ | ✓ | ✓ |   |   |   |   | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Exp2 — RTC competition (Meet, Teams), 8 & 50 Mbps, Jan 2024 |   |   |   |   |   | ✓ |   |   |   |   |   |   |   |   |   |   |
| Exp3 — Web page-load competition, 8 & 50 Mbps |   |   |   |   |   |   |   | ✓ |   |   |   |   |   |   |   |   |
| Exp4 — 5-flow iPerf BBR competition ("separate experiments"), 50 Mbps |   |   |   |   | ✓ |   |   |   |   |   |   |   |   |   |   |   |
| Exp5 — Bandwidth sweep (8–100 Mbps), 2022 |   |   |   |   |   |   |   |   | ✓ |   |   |   |   |   |   |   |
| Exp6 — Buffer-doubling run (8×BDP), NewReno-iPerf vs Mega, 50 Mbps |   |   |   |   |   |   |   |   |   | ✓ |   |   |   |   |   |   |
| Exp7 — 2022 longitudinal collection (standard settings, vs iPerf-BBR Linux 4.15) |   |   |   |   |   |   |   |   |   |   |   | ✓ |   |   |   |   |
| Exp8 — Linux-kernel BBR comparison (4.15 vs 5.15) |   |   |   |   |   |   |   |   |   |   |   | ✓ |   |   |   |   |

(Figure 1, Table 1, and Table 2 are non-experimental and have no ✓ in any row.)

### Shared-data columns (multiple experiments in one column)
- **Fig.4** → **Exp1 + Exp4.** The Dropbox-vs-Mega throughput time-series is part of the main all-pairs run (Exp1); the Dropbox/NewReno/Cubic-vs-**5 iPerf BBR flows** comparison comes from *"separate experiments in the moderately-constrained setting"* (Observation 4) → Exp4.
- **Fig.8** → **Exp1 + Exp6.** Fig 8a is the 4×BDP queue-occupancy telemetry of a NewReno-iPerf-vs-Mega run already in the main campaign (Exp1); Fig 8b is the doubled 8×BDP-buffer run (Exp6).
- **Fig.9** → **Exp1 + Exp7 + Exp8.** Fig 9a: the **2023** vs-iPerf-BBR bars are from the main all-pairs run (Exp1); the **2022** bars are the separate 2022 collection (Exp7). Fig 9b: the **kernel 4.15 vs 5.15** BBR comparison is Exp8.

### Note on Exp1 (single experiment, many views)
Figs 2, 3, 10, 11, 12, 13 and Table 3 are all **different metrics / views of the same 2023 all-pairs throughput-competition run** — MmF share (Fig 2), multi-flow throughput shares (Fig 3), a per-trial-instability scatter (Fig 10), and the BESS-recorded link-utilization / packet-loss / queuing-delay heatmaps (Figs 11/12/13, "a complete heatmap in Appendix B"). Table 3's transitivity examples are explicitly *"extracted from the set of results in Fig 2"* (Observation 14). None of these collects new data, so they share one Experiment ID. Portions of Figs 4, 8, and 9 also draw on this same run (see shared-data columns).

---

## Part 2: Experiment Details

### Exp1 — Main all-pairs throughput competition (video, file-transfer, and single-flow iPerf baseline services)
- **Figures/Tables:** Figure 2, Figure 3, Figure 4 (Dropbox-vs-Mega time-series only), Figure 8 (panel a, 4×BDP), Figure 9 (panel a, 2023 bars), Figure 10, Figure 11, Figure 12, Figure 13, Table 3
- **Objective:** Measure fairness (max-min-fair share achieved by an "incumbent" when a "contender" competes) for all pairs of throughput-intensive services, and the resulting link utilization, loss, and queuing delay.
- **Services (Table 1):** Video — YouTube (BBRv1.1, ≤13 Mbps, 1 flow), Netflix (NewReno, ≤8 Mbps, 4 flows, run on Safari), Vimeo (BBR, ≤14 Mbps, 2 flows); File transfer — Dropbox (BBRv1.0, 1 flow), Google Drive (BBRv3, 1 flow), OneDrive (Cubic, ≤45 Mbps external cap, 1 flow), Mega (BBR, 5 flows); Baselines — iPerf BBRv1.0 / Cubic / NewReno (each Linux 5.15, 1 flow). File transfers download the same 10 GB random file; video plays Big Buck Bunny.
- **Bandwidth settings:** 8 Mbps (highly-constrained) and 50 Mbps (moderately-constrained).
- **Base latency / RTT:** 50 ms (normalized). **Queue:** Drop-tail FIFO ≈ 4×BDP (power-of-two nearest). **Topology:** dumbbell via BESS.
- **Trials / duration:** 10-min runs (first/last 2 min discarded); ≥10 trials up to 30 until 95% CI of the median within ±0.5 Mbps (8 Mbps) / ±1.5 Mbps (50 Mbps); a full all-pairs trial ≈ 20 hours; ~2 weeks to iterate all pairs in both settings. Period June–Sept 2023.
- **Per-figure focus & results:**
  - **Fig 2:** Heatmap of median MmF share (incumbent) for all video×bulk pairs, both settings. Median losing service got 69% (highly-constrained) / 86% (moderately-constrained) of its MmF share; worst case OneDrive vs Mega = 16% (50 Mbps). Rows = contentiousness, columns = sensitivity (YouTube generally sensitive & uncontentious).
  - **Fig 3:** Effect of concurrent flows (Mega 5, Netflix 4, Vimeo 2 flows) on single-flow services, both settings; Netflix/Mega contentious only in the highly-constrained setting (application-limited at 50 Mbps).
  - **Fig 4 (Dropbox vs Mega panel):** Throughput time-series of Dropbox vs Mega (moderately-constrained) showing Mega's 5-flow "batch/burst" pattern; Dropbox ramps up between bursts to obtain ~90% of fair share. (The 5-iPerf-BBR-flow comparison in the same figure is Exp4.)
  - **Fig 8 (panel a):** Queue-occupancy time-series (NewReno pkts, Mega pkts, total pkts) at the standard **4×BDP (1024 packet)** buffer, moderately-constrained — showing link under-utilization when NewReno competes with Mega. Queue occupancy is a BESS-recorded signal off this main-campaign run, not a new run.
  - **Fig 9 (panel a, 2023 bars):** Throughput of YouTube and Google Drive vs iPerf-BBR (Linux 4.15) — the 2023 measurement is from this main all-pairs run.
  - **Fig 10:** Per-trial throughput (single trials) showing instability — OneDrive vs Cubic and Dropbox vs Cubic (unstable) vs YouTube vs YouTube (stable).
  - **Fig 11:** Median link-utilization heatmap (Appendix B.1) — ≥95% in most pairs; <85% when Mega competes with NewReno/Cubic/OneDrive (50 Mbps) and some video-vs-video pairs (8 Mbps).
  - **Fig 12:** Packet-loss-rate heatmap (Appendix B.2) — Mega induces most loss (8% in 8 Mbps), Netflix 4%; single-flow BBR-vs-BBR pairs have ~0 loss; near-0% at 50 Mbps.
  - **Fig 13:** Average queuing-delay heatmap per incumbent×contender (Appendix B.3; median over trials).
  - **Table 3:** Non-transitivity examples **extracted from Fig 2 data** — (Mega→NewReno→Vimeo @50 Mbps), (Cubic→Dropbox→NewReno @8 Mbps), (BBR→OneDrive→YouTube @50 Mbps).
- **Additional setup details:** All services run "solo" first to detect upstream throttling; OneDrive is the one service externally throttled to 45 Mbps.
- **Missing information:** Exact per-pair trial counts vary (10–30).

### Exp2 — Real-time communication (RTC) competition
- **Figures/Tables:** Figure 5 (metric definitions in Table 2)
- **Objective:** Measure QoE degradation of RTC services (Google Meet, Microsoft Teams) when competing with other services.
- **Services:** Google Meet (GCC, WebRTC, ≤1.5 Mbps, 1 flow), Microsoft Teams (unknown CCA, WebRTC, ≤2.6 Mbps, 1 flow) as incumbents vs. the throughput services as contenders. RTC plays the Big Buck Bunny reference video.
- **Metrics (Table 2):** video resolution, average FPS, freezes per minute (WebRTC freeze definition: inter-arrival > max(3δ, δ+150 ms)), fraction of high-delay packets (> ITU 190 ms RTT).
- **Bandwidth settings:** 8 Mbps and 50 Mbps. **RTT:** 50 ms. **Queue:** 4×BDP. Same dumbbell/BESS testbed.
- **Period:** January 2024.
- **Results:** In the moderately-constrained setting both perform well except on latency; in the highly-constrained setting many competitors cause QoE degradation. Meet degrades more in resolution but less in FPS than Teams; loss-based CCAs (and Mega) push 40–90% of packets past the 190 ms RTT bar; trade-offs differ by metric.
- **Missing information:** Trial counts for RTC not separately stated; higher-order QoE (VMAF/SSIM) deferred to future work.

### Exp3 — Web page-load-time competition
- **Figures/Tables:** Figure 6
- **Objective:** Measure how competing traffic inflates above-the-fold page load time (PLT) for webpages.
- **Webpages:** youtube.com, news.google.com, wikipedia.org (BBRv1.0/BBRv3.0 servers; variable flow counts). PLT measured via Google **SpeedIndex** (time for 95% of the above-the-fold region), pages loaded on a 4K display.
- **Procedure:** start contender, wait 30 s, load page in a fresh Chrome instance (cache/cookies wiped), repeat page load 10× with 45 s gaps; each trial repeated ≥5× → ≥50 data points per (webpage, contender) pair.
- **Contenders shown:** vs Mega, vs Cubic, vs Netflix, vs BBR, and Solo. Both bandwidth settings.
- **Results:** Competing traffic can double PLT at 50 Mbps and triple it at 8 Mbps (+4 s and +14 s worst case). youtube.com (image-heavy) worst affected (8 s → 21 s median vs Mega/Netflix, +162%); Wikipedia (text) least affected; BBR contenders least harmful at 50 Mbps.
- **Missing information:** Exact per-cell variance beyond reported medians.

### Exp4 — Five-flow iPerf BBR competition (a genuinely separate collection)  
### IMPORTANT: Probably should not consider this cause they just mentioned in a separate study we checked that but did not show the results in the figure. But in general, it is good to have that.
- **Figures/Tables:** Figure 4 (the "vs 5 iPerf BBR flows" comparison)
- **Objective:** Test whether Mega's five-flow behavior matches that of five iPerf BBR flows (isolating application-level batching from raw multi-flow BBR).
- **Setup:** *"In separate experiments in the moderately-constrained setting"* (Observation 4), Dropbox, NewReno, and Cubic each compete against **five concurrent iPerf BBR flows** (distinct from Table 1's single-flow iPerf baseline). Standard testbed, **50 Mbps**, 50 ms RTT, 4×BDP queue.
- **Results:** Dropbox gets only 33% of its MmF share vs 5 BBR flows (but ~90% vs Mega → Mega less contentious than raw BBR here); NewReno/Cubic get 80–90% vs 5 BBR flows (but 22–27% vs Mega → Mega more contentious than raw BBR). Explains Mega's bursty batching effect.
- **Missing information:** Trial counts and whether the 8 Mbps setting was also run (only the 50 Mbps result is reported).

### Exp5 — Bandwidth sweep (one-off, 2022)
- **Figures/Tables:** Figure 7
- **Objective:** Examine how fairness evolves as the bottleneck bandwidth changes (beyond the two standard settings).
- **Setup:** All-pairs experiments at a **range of bottleneck bandwidths between 8 Mbps and 100 Mbps** (axis ticks at 20/40/60/80/100 Mbps); highlighted pair = YouTube (incumbent) vs Dropbox (contender). Standard 50 ms RTT, 4×BDP queue.
- **Period:** 2022 experiments (footnote 8: "based on experiments from the 2022 period referred to in §3.2").
- **Results:** Fairness generally improves with more bandwidth but non-monotonically — YouTube's MmF share vs Dropbox *decreases* from 8→50 Mbps, and its raw throughput drops from 30→50 Mbps, before becoming fair beyond ~70 Mbps.
- **Missing information:** Exact set of bandwidth points sampled beyond the stated 8–100 Mbps range and axis ticks (reported as a range, not enumerated — none invented).

### Exp6 — Buffer-doubling run (8×BDP)
- **Figures/Tables:** Figure 8 (panel b, 8×BDP)
- **Objective:** Show buffer sizing significantly changes fairness/utilization outcomes.
- **Setup:** Repeat competition experiments with the buffer doubled to **8×BDP (2048 packets)** — for NewReno-based iPerf vs Mega, in the **moderately-constrained (50 Mbps)** setting. Queue-occupancy time-series (NewReno pkts, Mega pkts, total pkts). (The companion 4×BDP baseline panel, Fig 8a, belongs to Exp1's main-campaign run.)
- **Results:** With 8×BDP, Mega vs NewReno/Cubic no longer under-utilizes the link (>95% utilization; NewReno/Cubic rise from 22%/27% to >92%/97% of fair share). But NewReno's share vs Cubic drops from 60% to 28% (8 Mbps) with larger buffers, and queuing delay increases for all.
- **Missing information:** Trial counts for this one-off; other service pairs at 8×BDP.

### Exp7 — 2022 longitudinal collection (standard settings)
- **Figures/Tables:** Figure 9 (panel a, 2022 bars)
- **Objective:** Show that service-side deployment changes over time alter fairness properties (motivating a live watchdog).
- **Setup:** Standard testbed and settings, YouTube / Google Drive as incumbents vs **iPerf BBR on Linux 4.15**, measured during the **2022** period. Compared in Fig 9a against the 2023 measurement of the same pairs (Exp1).
- **Results:** YouTube +172% and Google Drive +46% throughput vs iPerf-BBR in 2023 relative to 2022, coinciding with BBRv3 deployment on Google Drive and YouTube QUIC-stack tuning.
- **Missing information:** Full set of pairs re-measured longitudinally; exact trial counts for the 2022 period.

### Exp8 — Linux-kernel BBR comparison (4.15 vs 5.15)
- **Figures/Tables:** Figure 9 (panel b)
- **Objective:** Show OS kernel updates to BBR change fairness properties even within "BBRv1."
- **Setup:** Standard testbed, YouTube / Dropbox / Google Drive as incumbents vs iPerf **BBR** built on **Linux kernel 4.15 vs 5.15** (both nominally "BBRv1"). Standard 50 ms RTT, 4×BDP, both bandwidth settings implied by the standard testbed.
- **Results:** The 5.15 BBR is less contentious than 4.15 against Dropbox/Google Drive but more contentious against YouTube — an "innocent" kernel upgrade measurably changes fairness.
- **Missing information:** Exact trial counts per kernel version; whether both bandwidth settings were run.

---

## Notes and Caveats
- **Count-by-setup rationale:** Most of the paper's figures (2, 3, 10, 11, 12, 13 and Table 3, plus parts of 4/8/9) are *different metrics/views of the single 2023 all-pairs throughput-competition run* (Exp1) — MmF share, time-series, per-trial spread, utilization/loss/delay telemetry, transitivity extraction — so they share one Experiment ID. New experiments appear only where the **collection setup genuinely changes**: a different application class + metrics (RTC → Exp2; web PLT → Exp3), a distinct 5-flow-BBR workload ("separate experiments" → Exp4), a swept bottleneck bandwidth in 2022 (Exp5), a changed buffer size (Exp6), a separate 2022 collection vs iPerf-BBR-4.15 (Exp7), and a kernel-version comparison (Exp8).
- **Alternate-telemetry / re-processing rule applied:** Figs 11/12/13 (link-util, loss, queuing-delay) and Fig 8a (queue occupancy) are BESS-recorded signals off already-executed Exp1 runs — no new packets sent → same experiment. Table 3 is derived by re-selecting Fig 2's values → same experiment.
- **Comparison / shared-data rule applied:** Fig 4 (Exp1 + Exp4), Fig 8 (Exp1 + Exp6), and Fig 9 (Exp1 + Exp7 + Exp8) each draw on more than one collection campaign and therefore have a ✓ in every contributing row.
- **Precision on numbers:** Bandwidths are the paper's exact two settings (8 Mbps, 50 Mbps); the sweep in Exp5 is reported as the stated 8–100 Mbps range (axis ticks 20/40/60/80/100) — intermediate points are not enumerated, so none are invented. Buffer sizes are stated exactly (4×BDP = 1024 packets, 8×BDP = 2048 packets). RTT normalized to 50 ms.
- **Congestion control** is a *reported property of each service* (Table 1), not a knob the authors sweep — except the iPerf baselines (single-flow BBR/Cubic/NewReno on Linux 5.15), the 5-flow-BBR set (Exp4), and the kernel-version comparison (Exp8).
- **Figure 1 / Table 1 / Table 2** are illustration/definitional and map to no experiment.
