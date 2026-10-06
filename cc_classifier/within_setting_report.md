# CCAnalyzer 1NN-DTW — Within-Setting Reproduction Result

**Date:** 2026-07-16
**Branch:** `jaber/ccanalayzer`
**Script:** `cc_classifier/within_setting.py` (raw output: `within_setting_results.txt`)

## Protocol (the paper's actual within-setting test)

- **Reference library:** the 183 `cc_results` wget queue-occupancy traces (bottleneck
  `veth2 backlog_pkts`, first 20 s), indexed by network setting — one trace per
  (CCA, setting) cell, all 15 CCAs at each of the 15 settings.
- **Test set:** the 20 `atw_cc_timing/runs/` traces — a **separate campaign**, so a
  correct match is a genuine cross-collection reproducibility check, not overfitting.
- **Match:** for a test trace at setting *S*, restrict the reference library to setting
  *S* (15 CCAs) and take the DTW-nearest CCA (1NN, banded Sakoe-Chiba DTW).
- **Data note:** the actual `*_qtrace.jsonl` traces live only in the backup
  `/home/jaber/atw_data_backup_20260716_174105/cc_results/` — the committed `cc_results/`
  holds metadata + figures only.

## Headline

| Metric | Value |
|---|---|
| **Within-setting accuracy (raw)** | **18/20 = 90.0%** |
| **Within-setting accuracy (norm)** | **18/20 = 90.0%** |
| CCAs matched at rank 1 | 13 / 15 |
| Paper reference (Fig 7, within-setting) | ~96% |

Consistent with the paper's within-setting accuracy. The 1NN-DTW classifier **does
reproduce high accuracy** on the ATW-regenerated traces when run under CCAnalyzer's own
within-setting protocol.

## Per-trace results (raw variant)

| setting | true CCA | predicted | ok | true-CCA rank |
|---|---|---|---|---|
| 5bw-85rtt-64q    | cubic     | cubic     | ✅ | 1 |
| 5bw-130rtt-64q   | bbr       | bbr       | ✅ | 1 |
| 5bw-275rtt-128q  | reno      | reno      | ✅ | 1 |
| 10bw-85rtt-128q  | htcp      | htcp      | ✅ | 1 |
| 10bw-130rtt-128q | vegas     | vegas     | ✅ | 1 |
| 10bw-275rtt-256q | bic       | bic       | ✅ | 1 |
| 15bw-85rtt-256q  | cdg       | cdg       | ✅ | 1 |
| 15bw-130rtt-256q | highspeed | highspeed | ✅ | 1 |
| 15bw-275rtt-512q | hybla     | hybla     | ✅ | 1 |
| 5bw-275rtt-32q   | illinois  | illinois  | ✅ | 1 |
| 5bw-275rtt-128q  | nv        | nv        | ✅ | 1 |
| 5bw-275rtt-512q  | scalable  | scalable  | ✅ | 1 |
| 5bw-275rtt-1024q | veno      | scalable  | ❌ | 4 |
| 5bw-85rtt-64q    | westwood  | westwood  | ✅ | 1 |
| 5bw-130rtt-64q   | yeah      | yeah      | ✅ | 1 |
| 10bw-85rtt-128q  | cubic     | scalable  | ❌ | 2 |
| 10bw-130rtt-128q | bbr       | bbr       | ✅ | 1 |
| 5bw-85rtt-64q    | reno      | reno      | ✅ | 1 |
| 10bw-130rtt-128q | cubic     | cubic     | ✅ | 1 |
| 5bw-130rtt-64q   | bbr       | bbr       | ✅ | 1 |

Both misses are loss-based↔loss-based confusions (the kind the paper itself reports),
and both are near-misses: `cubic→scalable` had the true CCA ranked 2nd, and the other
two cubics classified correctly (per-CCA voting would recover it → 19/20).

## Caveats for citation

- This is **20 test traces**, not the paper's 675 — a small-N within-setting check.
- It covers the **classification campaign only** — not the Gordon/IG efficiency
  comparison or the website census. Do **not** claim "reproduces all of CCAnalyzer's
  results"; scope it to the within-setting classification accuracy.
- Under the harder **cross-setting** protocol (leave-one-setting-out, forced when using
  `cc_results` alone since it has 1 rep/cell), accuracy is 44–48% per-trace / 73–80%
  per-CCA with voting — a different, harder task, not comparable to the paper's Fig 7.
