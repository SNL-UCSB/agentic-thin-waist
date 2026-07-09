# CCAnalyzer — Experiment-to-Figure Mapping and Experimental Setup

Paper: *CCAnalyzer: An Efficient and Nearly-Passive Congestion Control Classifier* (Ware et al., ACM SIGCOMM '24).

This document maps every figure and table to the underlying experiment(s) that produced its data, and reconstructs the experimental setup for each experiment from all locations in the paper.

> **Note on non-experimental items:** **Table 1** (CCA classifier desirable properties) is a conceptual comparison table — it presents no measured data. **Figure 2** (testbed diagram) is a system/methodology diagram, not an experiment. Both are listed as columns below for completeness but map to no experiment.

> **Correction note (data-reuse vs. new collection):** An earlier version of this mapping created separate experiments for **Fig. 10** (truncated traces), **Fig. 11 / Table 2** (DTW distance distributions), **Fig. 12** (open-set on Azure-East), **Fig. 17** (efficiency), and **Fig. 23** (training-sample examples). Those are **not** new experiments — they are re-analyses, truncations, sub-selections, or alternate-telemetry views of data already collected in the **main classification collection (Exp6)** and, for the baseline comparison, the **baseline-tools collection (Exp8)**. The only genuinely new data collection in that region of the paper is the **AWS-Ohio open-set tuning set (Exp7)**, which is used to *set* the Table 2 thresholds. Comparison figures that plot both CCAnalyzer's own traces and a baseline tool's traces are marked in **all** contributing experiment rows.

---

## Part 1: Experiment-to-Figure/Table Mapping

| Experiment | Fig.1 | Tab.1 | Fig.2 | Fig.3 | Fig.4 | Fig.5 | Fig.6 | Fig.7 | Fig.8 | Fig.9 | Fig.10 | Fig.11 | Tab.2 | Fig.12 | Fig.13 | Fig.14 | Fig.15 | Fig.16 | Fig.17 | Fig.18 | Tab.3 | Fig.19 | Fig.20 | Fig.21 | Fig.22 | Tab.4 | Fig.23 | Fig.24 |
|------------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|--------|--------|-------|--------|--------|--------|--------|--------|--------|--------|-------|--------|--------|--------|--------|-------|--------|--------|
| Exp1  | ✓ |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
| Exp2  |   |   |   | ✓ |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
| Exp3  |   |   |   |   | ✓ |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
| Exp4  |   |   |   |   |   | ✓ |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
| Exp5  |   |   |   |   |   |   | ✓ |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
| Exp6  |   |   |   |   |   |   |   | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |   | ✓ | ✓ | ✓ | ✓ |   |   |   |   |   |   |   | ✓ |   |
| Exp7  |   |   |   |   |   |   |   |   |   |   |   |   | ✓ |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
| Exp8  |   |   |   |   |   |   |   |   |   |   |   |   |   |   | ✓ | ✓ | ✓ | ✓ | ✓ |   |   |   |   |   |   |   |   |   |
| Exp9  |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   | ✓ | ✓ | ✓ | ✓ |   |   |   |   | ✓ |
| Exp10 |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   | ✓ |   |   |
| Exp11 |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   | ✓ | ✓ |   |   |   |

(Table 1 and Figure 2 are non-experimental and have no ✓ in any row.)

**Shared-data columns (a column with more than one ✓ means the figure/table draws on multiple collections):**
- **Table 2** = Exp6 (AWS-Virginia training-sample distances feed the quantile) **+** Exp7 (AWS-Ohio leave-one-out run that sets the threshold).
- **Fig. 14, 15, 16, 17** = Exp6 (CCAnalyzer's own queue-occupancy traces, a 4-setting subset of the Azure-East testing data) **+** Exp8 (the Gordon/IG baseline traces collected for the same comparison). **Fig. 13** shows *only* Gordon's votes, so it maps to **Exp8 alone** — it does not use Exp6 data.

---

## Part 2: Experiment Details

### Shared testbed / methodology (applies to most experiments unless noted)

- **Testbed:** CCAnalyzer testbed installed on **CloudLab servers in Wisconsin, USA** (Fig. 2). A custom switch with a deliberately slowed egress link forces a bottleneck; the switch records when packets are enqueued, dequeued, or dropped. The switch is implemented with the **BESS software switch**. The client issues **pipelined HTTP requests via h2load** to utilize the available bandwidth.
- **Ground-truth servers:** Linux servers on **AWS (Virginia)** = *training* data, and **Microsoft Azure ('East')** = *testing* data.
  - **Training Set (AWS-Virginia):** Ubuntu 22.04.2, Linux kernel 5.19, RTT to testbed 22 ms, **3 samples per CCA**.
  - **Testing Set (Azure-East):** Ubuntu 20.04.6, Linux kernel 5.15, sRTT to testbed 24 ms, **5 samples per CCA**.
- **Available bandwidth (measured with iperf):** testbed client ↔ AWS = 500 Mbps; testbed client ↔ Azure = 920 Mbps.
- **CCAs:** the **15 built-in wide-area CCAs in Linux** (BBR = BBRv1 only). Set: BBR, BIC, CDG, Cubic, Highspeed, HTCP, Hybla, Illinois, New Vegas (NV), NewReno, Scalable, Vegas, Veno, Westwood, Yeah. (The `ip`/`dctcp` algorithms are excluded.)
- **Classifier:** 1-Nearest-Neighbor with Dynamic Time Warping (1NN-DTW) over bottleneck-queue-occupancy time series; TNN (threshold-NN) extension for open-set/unknown detection.
- **Trace lengths:** training traces collected via iperf for 120 s (only ~20 s needed); testing traces via wget of a 100 MB Apache-hosted file for 60 s.
- **Queue management:** Not specified explicitly (a basic FIFO queue of a chosen size implemented in BESS; BESS requires queue size to be a power of 2, set to the power of 2 closest to 1 BDP). No AQM (e.g., DropTail/FQ-CoDel/PIE) is named.
- **Cross traffic:** None mentioned for the controlled testbed experiments (Not specified).
- **Network-setting naming:** `<bw>bw-<rtt>rtt-<queue>q`, e.g., `5bw-85rtt-64q` = 5 Mbps, 85 ms RTT, 64-packet queue.

---

### Exp1 — Illustrative real queue-occupancy traces (TCP sawtooth motivation)
- **Figures/Tables:** Figure 1
- **Objective:** Show that four CCAs have visually distinct bottleneck queue-occupancy behavior (motivation).
- **Application/Workload:** Real TCP connections (queue-occupancy traces collected from real connections on the testbed).
- **Congestion control:** New Reno, BBR, Cubic, BIC (four CCAs).
- **Duration:** Time series shown over 0–50 s.
- **Emulator/Testbed:** CCAnalyzer testbed (BESS bottleneck switch).
- **Bandwidth / Base latency / Queue size / Queue mgmt / Cross traffic / # flows / Repetitions / Dataset / Hardware:** Not specified for this figure.
- **Missing information:** Exact bandwidth, RTT, queue size, number of flows, and which server generated these specific traces are not stated.

### Exp2 — ED-vs-DTW distance illustration (usps.com vs Cubic training sample)
- **Figures/Tables:** Figure 3
- **Objective:** Illustrate why Euclidean distance (one-to-one mapping) fails and DTW (one-to-many mapping) succeeds for comparing same-CCA traces.
- **Application/Workload:** A measured queue-occupancy trace from the website **usps.com** compared against a **Cubic training sample**.
- **Congestion control:** Cubic (training sample); usps.com's CCA assumed Cubic.
- **Metric:** Euclidean distance = 2.47 (Fig. 3a); DTW distance = 0.76 (Fig. 3b).
- **Emulator/Testbed:** CCAnalyzer testbed; usps.com trace from the measurement study.
- **Bandwidth / RTT / Queue size / Duration / Repetitions:** Not specified for this figure.
- **Missing information:** Network setting (bw/RTT/queue) used to collect the usps.com trace and the Cubic training trace is not stated here.

### Exp3 — RTT distribution of Top 10K websites (ping measurement)
- **Figures/Tables:** Figure 4
- **Objective:** Measure the distribution of ping (RTT) times to the Top 10K websites to choose a representative testbed RTT; most websites are within 275 ms.
- **Application/Workload:** ICMP ping to the Top 10K websites.
- **Dataset:** Google Chrome CrUX Report Top 10K websites (Feb 2023 bucket, ~70% of Chrome page loads), identified by origin.
- **Result:** CDF of ping time; 275 ms covers most websites.
- **Emulator/Testbed:** CCAnalyzer testbed (Fig. 2).
- **Bandwidth / Queue size / Congestion control / Repetitions / Duration:** Not applicable / Not specified.
- **Missing information:** Number of ping repetitions per site not stated.

### Exp4 — Effect of queue size on Cubic queue occupancy (5 Mbps, 275 ms)
- **Figures/Tables:** Figure 5
- **Objective:** Show how Cubic queue-occupancy traces change with queue size, motivating the ~1 BDP queue-size choice.
- **Application/Workload:** wget download from Azure-East server (testbed measurement).
- **Bandwidth:** 5 Mbps.
- **Base latency / RTT:** 275 ms.
- **Queue size:** Four values — 32, 128, 512, 1024 packets (128 packets ≈ 1 BDP in this setting).
- **Congestion control:** Cubic.
- **Duration:** ~0–60 s (time-series x-axis).
- **Topology:** Single bottleneck (BESS switch).
- **Emulator/Testbed:** CCAnalyzer testbed; server = Azure-East.
- **# flows:** 1 (single connection per trace).
- **Cross traffic:** None (Not specified).
- **Repetitions:** Not specified for this illustrative figure.

### Exp5 — Effect of queue size on BBR queue occupancy (5 Mbps, 275 ms)
- **Figures/Tables:** Figure 6
- **Objective:** Same as Exp4 but for BBR — show BBR's queue occupancy across queue sizes (BBR uses very little of the queue when it is too large).
- **Application/Workload:** wget download from Azure-East server.
- **Bandwidth:** 5 Mbps.
- **Base latency / RTT:** 275 ms.
- **Queue size:** 32, 128, 512, 1024 packets.
- **Congestion control:** BBR (BBRv1).
- **Duration:** ~0–60 s.
- **Topology:** Single bottleneck (BESS switch).
- **Emulator/Testbed:** CCAnalyzer testbed; server = Azure-East.
- **# flows:** 1.
- **Cross traffic:** None (Not specified).
- **Repetitions:** Not specified for this illustrative figure.

### Exp6 — Main 1NN-DTW classification data collection (AWS-Virginia training + Azure-East testing)
- **Figures/Tables:** Figure 7, Figure 8, Figure 9, Figure 10, Figure 11, Table 2 (shared with Exp7), Figure 12, Figure 14, Figure 15, Figure 16 (shared with Exp8), Figure 17 (shared with Exp8), Figure 23
- **This is the single collection campaign behind the bulk of §3–§4.** All of the figures below are different analyses / truncations / sub-selections / alternate-telemetry views of the **same** collected trace set (AWS-Virginia training samples + Azure-East testing samples, 15 CCAs, 9 network settings). No new data is collected for any of them.
- **Objective(s), by analysis:**
  - **Fig. 7** — per-setting classification accuracy of CCAnalyzer (1NN-DTW) for all 15 CCAs across the 9 network settings (overall 96%, 649/675).
  - **Fig. 8** — a correctly labeled BBR testing trace next to its nearly identical closest BBR training trace (10bw-130rtt setting), illustrating interpretability.
  - **Fig. 9** — DTW distances of one BBR testing sample to all training CCAs (10bw-130rtt); BBR closest, then CDG/Vegas.
  - **Fig. 10** — *trace-length sensitivity.* The **same** testing traces re-classified individually (no voting) after being **truncated** to 10, 20, 30, 40, 50 s, in the 4 most accurate settings; near-perfect accuracy at ≥20 s. **(Not a new experiment — truncation of already-collected traces.)**
  - **Fig. 11** — CDF of pairwise DTW distances among the **AWS-Virginia training samples**, split into same-CCA vs. different-CCA pairs (5bw-85rtt-64q); motivates the unknown-detection threshold. **(Re-analysis of the training data already collected here.)**
  - **Table 2** — the chosen quantile of the same-CCA distribution (from Fig. 11 / this training data) that yields each per-setting threshold T. The threshold *values* are set using the separate AWS-Ohio run (Exp7); the underlying same-CCA distances come from this experiment's training data.
  - **Fig. 12** — open-set validation on the **Azure-East testing set**: for each CCA, its training samples are removed and the tool checks whether that CCA's Azure-East testing traces are correctly marked unknown. After voting across the 4 settings, only CDG, BIC, Scalable are misclassified as known. **(Uses this experiment's Azure-East testing data — not a new collection.)**
  - **Fig. 14 / 15 / 16** — CCAnalyzer's contribution to the baseline comparison (individual per-CCA votes, the three-tool accuracy comparison, and interpretable queue-occupancy traces) is its 4-setting Azure-East subset from this collection. Shared with Exp8 (Gordon/IG data).
  - **Fig. 17** — CCAnalyzer's efficiency numbers (bytes transferred, wall-clock time) are computed from the **pcaps of these same trace collections** — a different telemetry view (pcap byte counts / timing) of the same runs, not a new experiment. Shared with Exp8 (Gordon).
  - **Fig. 23** (Appendix D) — example training-sample queue-occupancy traces for all 15 CCAs at 5bw-85rtt-64q, drawn directly from this experiment's **AWS-Virginia training set**.
- **Application/Workload:** Training = iperf flows (AWS-Virginia); Testing = wget download of a 100 MB Apache-hosted file (Azure-East). CCAnalyzer efficiency (Fig. 17) collects 4 traces per CCA (one per accurate setting).
- **Bandwidth:** 5, 10, 15 Mbps (across the 9 settings).
- **Base latency / RTT:** 85, 130, 275 ms (across the 9 settings).
- **Queue size:** ≈1 BDP per setting (64–512 packets).
- **9 network settings:** 5bw-85rtt-64q, 5bw-130rtt-64q, 5bw-275rtt-128q, 10bw-85rtt-128q, 10bw-130rtt-128q, 10bw-275rtt-256q, 15bw-85rtt-256q, 15bw-130rtt-256q, 15bw-275rtt-512q. **4 most accurate settings** (used for voting in Fig. 10/12/14–17): 10bw-130rtt-128q, 10bw-85rtt-128q, 5bw-130rtt-64q, 5bw-85rtt-64q.
- **Congestion control:** All 15 Linux CCAs.
- **# samples / Repetitions:** 3 training samples per CCA (AWS-Virginia); 5 testing samples per CCA (Azure-East) × 15 CCAs × 9 settings = **675 testing samples** for Fig. 7 (accuracy 96%). CCAnalyzer efficiency uses 4 traces per CCA.
- **Duration:** Testing traces 60 s (only ~20 s used); training ~20 s of the 120 s iperf runs. Fig. 8/23 shown over 0–20 s; Fig. 10 truncations 10–50 s.
- **Classifier:** 1NN-DTW (closed-set); TNN-DTW with per-setting threshold T (open-set, Fig. 12).
- **Topology:** Single bottleneck (server → Internet → NAT → BESS node → client).
- **Emulator/Testbed:** CloudLab-Wisconsin testbed; AWS-Virginia (train) and Azure-East (test).
- **Cross traffic:** None (Not specified).
- **Misclassifications noted:** Illinois → Westwood; BBR → Vegas/low-latency CCAs.

### Exp7 — AWS-Ohio open-set threshold-tuning collection
- **Figures/Tables:** Table 2 (shared with Exp6)
- **Objective:** *Set* the per-setting DTW distance threshold T used for unknown detection. Because there is no ground truth for novel-CCA deployment, the authors **emulate unknowns** by running leave-one-CCA-out classification and sweeping T (~1–15) to balance false-knowns vs. false-unknowns.
- **Why this is a distinct experiment:** it uses the existing AWS-Virginia training data as the reference set but runs classification on a **new testing set collected from a server in the AWS-Ohio region** — a genuinely new data-collection campaign (different cloud region), not a re-analysis of Exp6's traces.
- **Application/Workload:** wget/testbed testing traces collected against the **AWS-Ohio** server; AWS-Virginia training samples as the reference library.
- **Method:** Leave-one-out per CCA over all 15 CCAs; vary T; thresholds reported in Table 2 (quantile → distance): 10bw-130rtt-128q 0.90→4.41; 10bw-85rtt-128q 0.94→6.45; 5bw-130rtt-64q 0.90→9.73; 5bw-85rtt-64q 0.95→6.68.
- **Network settings:** The 4 accurate settings.
- **Congestion control:** All 15 Linux CCAs.
- **Emulator/Testbed:** CCAnalyzer testbed; AWS-Virginia (train), **AWS-Ohio (test)**.
- **Repetitions / Duration:** Not explicitly restated (uses the standard per-CCA sample sets and trace durations).
- **Cross traffic:** None (Not specified).

### Exp8 — Baseline-tools comparison collection (Gordon + Inspector Gadget)
- **Figures/Tables:** Figure 13, Figure 14, Figure 15, Figure 16 (Fig. 14–16 shared with Exp6), Figure 17 (shared with Exp6)
- **Objective:** Compare CCAnalyzer against the prior classifiers **Gordon** and **Inspector Gadget (IG)** on the same servers — accuracy (Fig. 15), per-trace individual votes for Gordon (Fig. 13) and CCAnalyzer (Fig. 14), interpretability of IG CWND traces vs CCAnalyzer queue-occupancy traces (Fig. 16), and efficiency in bytes/time (Fig. 17).
- **What data is *new* here:** the **Gordon CWND-estimator traces** and the **IG traces** collected by installing those tools on clients in the **CloudLab Utah** testbed and downloading a **100 MB file from the Azure-East Apache web server**. (IG replication additionally used AWS servers to generate its own train+test.) CCAnalyzer's own traces in these figures are the 4-setting Azure-East subset already collected in **Exp6** — hence Fig. 14–17 are marked in both rows.
- **Congestion control:** All 15 Linux CCAs (Gordon does not support CDG, Hybla, NV, Westwood → 13 supported; Fig. 17 efficiency compares over the 13 Gordon-supported CCAs).
- **# samples / Repetitions:**
  - CCAnalyzer: each CCA classified **5 times** → **20 queue-occupancy samples per CCA** (5 × 4 settings), vote across 4 settings.
  - Gordon: **5 times** → **75 CWND trace samples per CCA**, vote across 15 trials.
  - IG: each CCA classified **20 times**.
- **Results:** CCAnalyzer = 100% accuracy over all 15 CCAs (correctly marks CDG/Hybla/NV unknown); IG = 100% in its own faithful setup, 73%/74% over 15/12 CCAs (AWS train+test); Gordon = correct on most loss-based CCAs but misclassifies all Highspeed and Illinois as BBR. Efficiency (Fig. 17): CCAnalyzer mean **68 MB** total (4 traces) / ~**2 min** vs. Gordon **456 MB** (std 186) / min 2.6 min–**max 130 min**; IG ≤ 2 MB / ≤ 90 s. CCAnalyzer ≈ 15% fewer bytes and 40× faster than Gordon (85% fewer bytes figure also cited).
- **Fig. 16 specifics:** IG CWND traces (Cubic, HTCP) over ~0–30 RTTs vs CCAnalyzer queue-occupancy traces (Cubic, HTCP) over 0–20 s.
- **Emulator/Testbed:** CloudLab-Utah (Gordon/IG clients) + AWS-Virginia (CCAnalyzer training) + Azure-East (web server).
- **Cross traffic:** None (Not specified).

### Exp9 — Measurement study: classifying & clustering Top 10K websites
- **Figures/Tables:** Figure 18, Table 3, Figure 19, Figure 20, Figure 24
- **Objective:** Classify the CCAs of the Top 10K websites by CDN, detect new CCAs (BBRv3), and cluster unknown traces (Table 3); visualize CDN clustering dendrograms (Fig. 18 portion, Fig. 24 full), a suspected BBRv3 Google trace (Fig. 19), and non-CDN unknown traces (Fig. 20).
- **Note on reference data:** classification uses the Exp6 **AWS-Virginia training set** as its reference library, but the traces plotted/analyzed here are **new h2load measurements of real websites** — a new collection campaign — so this maps to Exp9, not Exp6.
- **Application/Workload:** **h2load** issuing parallel HTTP requests to download enough data (5 Mbps and 10 Mbps targets); **findcdn** used to identify the hosting CDN; **wget** used where only one CDN result.
- **Dataset:** CrUX Top 10K websites (Feb 2023 bucket), identified by origin.
- **Bandwidth settings:** 5 Mbps, 10 Mbps. **Bandwidth-utilization threshold:** 80% (trace invalid below; "All Invalid" if all traces for a site fail). **RTT limit:** 85 ms.
- **Network settings:** 4 accurate settings with voting; then agglomerative ('average'-linkage) clustering within each CDN and across all sites, using the Table 2 distance thresholds.
- **Coverage (Table 3 / text):** 34% unresponsive, 13% RTT > 85 ms, 9% all-invalid (low bandwidth); 1635 unknown before clustering (1035 after). Per-CDN counts in Table 3 (Akamai, Cloudflare, Cloudfront, Fastly, Google, Other, No-CDN; total 10,000).
- **Figure specifics:**
  - Fig. 18: portion of dendrogram for **Fastly** websites in **5bw-85rtt-128q** (vertical line = distance threshold).
  - Fig. 24: full dendrogram of Fastly clustering, **5bw-85rtt-128q**.
  - Fig. 19: suspected **BBRv3** trace from a Google website (**scholar.google.com**), settings **10bw-130rtt-128q** (left) and **10bw-85rtt-128q** (right), 0–20 s. 102 Google CDN sites relabeled BBRv3.
  - Fig. 20: example unknown traces from non-CDN sites (**newyork.craigslist.org**, **douyu.com**), 0–20 s.
- **Emulator/Testbed:** CCAnalyzer testbed; AWS-Virginia training data as reference.
- **Repetitions:** 4 traces per website (one per setting), voting across them.
- **Findings:** Widespread BBRv1 deployment (Cloudflare, Akamai); Fastly still Cubic; ~362 Cloudflare sites relabeled BBR after clustering, ~105 Fastly unknowns relabeled Cubic.

### Exp10 — Inspector Gadget (IG) measurement on Top 10K websites
- **Figures/Tables:** Table 4 (Appendix C)
- **Objective:** Apply the re-implemented IG to the Top 10K websites and report how few can be classified (IG requires a downloadable object ≥ 1.5 MB).
- **Application/Workload:** IG web crawler attempting to find large-enough objects on each site (crawls up to 500 links per website).
- **Dataset:** Top 10K websites.
- **Results (Table 4 counts):** BBR 71, Cubic 25, Yeah 10, Highspeed 5, BIC 2 (113 classified); "Not large enough object" 9533; "Trace collection fail" 354; Total 10,000. Only **113 websites** successfully classified (~1%).
- **Emulator/Testbed:** Re-implemented IG (could not run published code at scale).
- **Bandwidth / RTT / Queue / Repetitions:** Not specified.

### Exp11 — Low-bandwidth limitation study (0.3 Mbps, 275 ms) on CloudLab
- **Figures/Tables:** Figure 21, Figure 22
- **Objective:** Address coverage limitations by finding a low-bandwidth, high-RTT setting that still produces distinguishable traces; show example training traces (Fig. 21) and accuracy across queue sizes and trace lengths (Fig. 22).
- **Application/Workload:** iperf training + testing traces collected entirely on CloudLab servers (server = CloudLab machine).
- **Bandwidth:** 0.3 Mbps (found by decreasing bandwidth 0.1 Mbps at a time until traces became distinctive).
- **Base latency / RTT:** 275 ms.
- **Queue sizes tested (Fig. 22):** 8, 16, 32, 64, 128, 256, 512 packets (~1 BDP = 16 packets works well).
- **Trace lengths tested (Fig. 22):** 20, 30, 40, 50, 60 s (100% accuracy for traces as short as 20 s).
- **Fig. 21 specifics:** Example training traces at **0.3bw-275rtt-16q** for Reno, Westwood, BBR, Cubic, 0–60 s.
- **Congestion control:** All 15 Linux CCAs.
- **# samples / Repetitions:** Split into **3 training + 2 testing samples per CCA** (all from CloudLab).
- **Emulator/Testbed:** CloudLab server (both training and testing).
- **Cross traffic:** None (Not specified).

---

## Notes and Caveats

- **Data reuse vs. new collection (the key correction).** The main classification collection (**Exp6**) is analyzed many ways: raw accuracy (Fig. 7–9), *truncated* traces (Fig. 10), *distances among its training samples* (Fig. 11 / same-CCA quantile in Table 2), *open-set re-classification of its Azure-East testing set* (Fig. 12), *pcap byte/time telemetry* of the same runs (Fig. 17), and *example training traces* (Fig. 23). None of these collect new data, so all map to Exp6. Only a change of **setup** creates a new experiment: the **AWS-Ohio** tuning set (Exp7), the **Gordon/IG** trace collection (Exp8), the **Top 10K h2load** study (Exp9), the **IG crawl** (Exp10), and the **0.3 Mbps CloudLab** study (Exp11).
- **Multi-experiment columns.** Table 2 (Exp6 + Exp7) and Fig. 14/15/16/17 (Exp6 + Exp8) each combine data from two collections, so both contributing experiments are checked. Fig. 13 uses only Gordon's data → Exp8 alone.
- **Reference/training data is not, by itself, a mapping.** A figure maps to the experiment whose collected data is the *subject being plotted/analyzed*, not to every experiment whose data merely serves as a trained-model reference library. The Top 10K measurement study (Exp9) uses the AWS-Virginia training set as reference but plots new website traces, so it maps to Exp9, not Exp6.
- **Queue management (AQM):** Never named explicitly. The bottleneck is a fixed-size FIFO queue in BESS (size forced to a power of 2 near 1 BDP). DropTail/FQ-CoDel/PIE are not mentioned → *Not specified* throughout.
- **Topology:** The only topology shown is the single-bottleneck path in Fig. 2. No multi-flow dumbbell with cross traffic is described.
- **Cross traffic:** No controlled cross-traffic experiments; background flows are mentioned only as a real-Internet phenomenon DTW must tolerate.
- **Table 4 total:** component counts (113 classified + 9533 + 354) sum to 10,000, consistent with the Top 10K dataset.
</content>
</invoke>
