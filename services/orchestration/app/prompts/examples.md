INTENT: "Run YouTube at 10 Mbps"
EXTRACTED:
{
  "applications": [
    "youtube"
  ],
  "capacities": [
    10
  ],
  "latencies": None,
  "cc_algorithms": None,
  "aqm_policy": None,
  "ctp_cluster": None,
  "duration_seconds": None,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": [
    "isolated"
  ],
  "reasoning": "The intent is straightforward: run a single YouTube experiment at 10 Mbps. No latency, CC algorithm, AQM policy, cross-traffic, or duration was specified, so defaults will apply: latency=50ms, cc_algorithm=cubic, aqm_policy=fq_codel, duration=60s (YouTube default), num_trials=1. The 10 Mbps capacity is well above the 3 Mbps minimum threshold for YouTube (no constraint violation). No cross-traffic was mentioned, so ctp_cluster is None. This is a simple isolated single-application experiment \u2014 no concurrency or Cartesian expansion is implied."
}
REASONING: "The intent is straightforward: run a single YouTube experiment at 10 Mbps. No latency, CC algorithm, AQM policy, cross-traffic, or duration was specified, so defaults will apply: latency=50ms, cc_algorithm=cubic, aqm_policy=fq_codel, duration=60s (YouTube default), num_trials=1. The 10 Mbps capacity is well above the 3 Mbps minimum threshold for YouTube (no constraint violation). No cross-traffic was mentioned, so ctp_cluster is None. This is a simple isolated single-application experiment — no concurrency or Cartesian expansion is implied."

INTENT: "Test YouTube at 10, 25, 50 Mbps"
EXTRACTED:
{
  "applications": [
    "youtube"
  ],
  "capacities": [
    10,
    25,
    50
  ],
  "latencies": None,
  "cc_algorithms": None,
  "aqm_policy": None,
  "ctp_cluster": None,
  "duration_seconds": None,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": [
    "isolated",
    "isolated",
    "isolated"
  ],
  "reasoning": "The intent clearly specifies a capacity sweep for YouTube at three distinct capacity values: 10, 25, and 50 Mbps. All three are within the valid range [0.1, 10000] Mbps and comfortably above the 3 Mbps minimum recommended for YouTube, so no constraint warnings apply. No latency, CC algorithm, AQM policy, cross-traffic, or duration were specified, so defaults will be applied: latency_ms=50, cc_algorithm=cubic, aqm_policy=fq_codel, duration_seconds=60 (YouTube default). Each capacity value results in one isolated experiment (single application, no concurrent traffic). num_trials defaults to 1. No clarification is needed as the intent is unambiguous."
}
REASONING: "The intent clearly specifies a capacity sweep for YouTube at three distinct capacity values: 10, 25, and 50 Mbps. All three are within the valid range [0.1, 10000] Mbps and comfortably above the 3 Mbps minimum recommended for YouTube, so no constraint warnings apply. No latency, CC algorithm, AQM policy, cross-traffic, or duration were specified, so defaults will be applied: latency_ms=50, cc_algorithm=cubic, aqm_policy=fq_codel, duration_seconds=60 (YouTube default). Each capacity value results in one isolated experiment (single application, no concurrent traffic). num_trials defaults to 1. No clarification is needed as the intent is unambiguous."

INTENT: "Compare YouTube vs Zoom at 25 Mbps"
EXTRACTED:
{
  "applications": [
    "youtube",
    "zoom"
  ],
  "capacities": [
    25
  ],
  "latencies": None,
  "cc_algorithms": None,
  "aqm_policy": None,
  "ctp_cluster": None,
  "duration_seconds": None,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": [
    "isolated",
    "isolated",
    "concurrent"
  ],
  "reasoning": "The user wants to compare YouTube vs Zoom at a fixed 25 Mbps capacity. This is a classic application comparison design. I will include three experiments: one with YouTube in isolation, one with Zoom in isolation, and one concurrent experiment where both run simultaneously so interaction effects can be observed (as required by the behavioral rules when two or more distinct applications are mentioned). Latency defaults to 50 ms, CC to cubic, and AQM to fq_codel per knowledge file defaults. Duration will use each application's default (60s for YouTube, 120s for Zoom). No cross-traffic was specified, so ctp_cluster is None \u2014 no background CTP is added for pure baseline comparison. No clarifications are needed; the intent is clear and the 25 Mbps capacity is well above the minimum thresholds for both YouTube (~3 Mbps) and Zoom (~1.5 Mbps)."
}
REASONING: "The user wants to compare YouTube vs Zoom at a fixed 25 Mbps capacity. This is a classic application comparison design. I will include three experiments: one with YouTube in isolation, one with Zoom in isolation, and one concurrent experiment where both run simultaneously so interaction effects can be observed (as required by the behavioral rules when two or more distinct applications are mentioned). Latency defaults to 50 ms, CC to cubic, and AQM to fq_codel per knowledge file defaults. Duration will use each application's default (60s for YouTube, 120s for Zoom). No cross-traffic was specified, so ctp_cluster is None — no background CTP is added for pure baseline comparison. No clarifications are needed; the intent is clear and the 25 Mbps capacity is well above the minimum thresholds for both YouTube (~3 Mbps) and Zoom (~1.5 Mbps)."

INTENT: "Compare CUBIC vs BBR for YouTube at 10 Mbps with a ctp between 2 and 5Mbps"
EXTRACTED:
{
  "applications": [
    "youtube"
  ],
  "capacities": [
    10
  ],
  "latencies": None,
  "cc_algorithms": [
    "cubic",
    "bbr"
  ],
  "aqm_policy": None,
  "ctp_cluster": None,
  "ctp_capacity_range": {
    "lower_value": 2,
    "higher_value": 5
  },
  "duration_seconds": None,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": [
    "isolated",
    "isolated"
  ],
  "reasoning": "The intent is a CC algorithm comparison with an explicit CTP capacity band. CUBIC and BBR are compared for YouTube at 10 Mbps bottleneck capacity, while CTP selection is constrained to 2–5 Mbps via ctp_capacity_range. This keeps shaping capacity and CTP query range separate. Latency and AQM are unspecified so defaults apply. No clarification is needed."
}
REASONING: "The intent is a CC algorithm comparison with an explicit CTP capacity band. CUBIC and BBR are compared for YouTube at 10 Mbps bottleneck capacity, while CTP selection is constrained to 2–5 Mbps via ctp_capacity_range. This keeps shaping capacity and CTP query range separate. Latency and AQM are unspecified so defaults apply. No clarification is needed."

INTENT: "How does Netflix perform?"
EXTRACTED:
{
  "applications": [
    "netflix"
  ],
  "capacities": None,
  "latencies": None,
  "cc_algorithms": None,
  "aqm_policy": None,
  "ctp_cluster": None,
  "duration_seconds": 60,
  "num_trials": 1,
  "clarification_needed": [
    "No capacity range specified \u2014 what link speeds are of interest? Common options: (a) a capacity sweep at [3, 5, 10, 25, 50] Mbps to explore SD/HD/4K thresholds, (b) a fixed 'typical home' capacity around 25 Mbps, or (c) a low-bandwidth stress test at [1, 3, 5] Mbps.",
    "No latency specified \u2014 should latency be held at the default (50 ms), or do you want a latency sweep (e.g., [20, 50, 100, 200] ms) to study buffering behaviour under varying propagation delay?",
    "No cross-traffic specified \u2014 should experiments run in isolation (no CTP), or with a typical home background load (ctp_low_background) or a competing video stream (ctp_video_moderate)?",
    "No congestion control algorithm specified \u2014 default (cubic) will be used unless you want a CC comparison (e.g., cubic vs bbr).",
    "No number of trials specified \u2014 default of 1 will be used; more trials (e.g., 3\u20135) would improve statistical reliability.",
    "The intent is very open-ended ('How does Netflix perform?'). Clarifying the independent variable of interest (capacity, latency, loss, CC algorithm, or cross-traffic) would allow a much more focused and cost-efficient design."
  ],
  "design_type": [
    "needs_clarification"
  ],
  "reasoning": "The intent 'How does Netflix perform?' implies a Netflix QoE characterisation experiment but leaves every network parameter unspecified. The only firm inference is the application (netflix) and its default duration (60 s per the application_defaults knowledge file). All other axes \u2014 capacity, latency, loss, CC algorithm, AQM policy, and cross-traffic \u2014 are undefined, making it impossible to produce a well-scoped experiment set without further clarification. A full Cartesian sweep across all reasonable parameter values would likely exceed 50 experiments and may not answer a focused question. The design is therefore flagged as 'needs_clarification' until at least the primary independent variable and capacity range are specified. Once clarified, the most likely design pattern will be a capacity sweep (testing Netflix across SD/HD/4K-relevant bandwidths) or a latency sweep, both of which are well-supported by the experimental_designs knowledge file."
}
REASONING: "The intent 'How does Netflix perform?' implies a Netflix QoE characterisation experiment but leaves every network parameter unspecified. The only firm inference is the application (netflix) and its default duration (60 s per the application_defaults knowledge file). All other axes — capacity, latency, loss, CC algorithm, AQM policy, and cross-traffic — are undefined, making it impossible to produce a well-scoped experiment set without further clarification. A full Cartesian sweep across all reasonable parameter values would likely exceed 50 experiments and may not answer a focused question. The design is therefore flagged as 'needs_clarification' until at least the primary independent variable and capacity range are specified. Once clarified, the most likely design pattern will be a capacity sweep (testing Netflix across SD/HD/4K-relevant bandwidths) or a latency sweep, both of which are well-supported by the experimental_designs knowledge file."

INTENT: "YouTube and Zoom at 10, 25, 50 Mbps"
EXTRACTED:
{
  "applications": [
    "youtube",
    "zoom"
  ],
  "capacities": [
    10,
    25,
    50
  ],
  "latencies": None,
  "cc_algorithms": None,
  "aqm_policy": None,
  "ctp_cluster": None,
  "duration_seconds": None,
  "num_trials": 1,
  "clarification_needed": [
    "Latency is not specified \u2014 will default to 50 ms per parameter_ranges defaults. Clarify if a different latency regime is intended.",
    "It is ambiguous whether YouTube and Zoom should run in isolation (separate experiments) or concurrently (together on the same link). The system prompt requires at least one concurrent experiment when two applications are mentioned, but the primary intent may be an application comparison. Please confirm whether concurrent experiments are desired in addition to isolated ones.",
    "No CC algorithm specified \u2014 will default to cubic. Clarify if a CC comparison is part of the intent.",
    "No AQM policy specified \u2014 will default to fq_codel.",
    "No cross-traffic specified \u2014 no CTP will be applied. Clarify if background traffic should be included.",
    "No number of trials specified \u2014 will default to 1. Clarify if more trials are needed for statistical confidence."
  ],
  "design_type": [
    "isolated",
    "isolated",
    "isolated",
    "isolated",
    "isolated",
    "isolated",
    "concurrent",
    "concurrent",
    "concurrent"
  ],
  "reasoning": "The intent specifies two applications (YouTube and Zoom) and three capacity values (10, 25, 50 Mbps), strongly suggesting a full Cartesian application comparison design: each app tested in isolation at each of the three capacity points (6 isolated experiments total). Per the behavioral rules, since two distinct applications are mentioned, at least one concurrent experiment is also required to observe interaction effects \u2014 one concurrent experiment per capacity point is added (3 concurrent experiments), yielding 9 experiments total. Latency defaults to 50 ms, CC defaults to cubic, AQM defaults to fq_codel, no cross-traffic, 1 trial per configuration. Duration will follow application defaults (YouTube: 60s, Zoom: 120s). A constraint check notes that at 10 Mbps, both YouTube and Zoom are well above their minimum viable capacity thresholds, so no warnings are triggered."
}
REASONING: "The intent specifies two applications (YouTube and Zoom) and three capacity values (10, 25, 50 Mbps), strongly suggesting a full Cartesian application comparison design: each app tested in isolation at each of the three capacity points (6 isolated experiments total). Per the behavioral rules, since two distinct applications are mentioned, at least one concurrent experiment is also required to observe interaction effects — one concurrent experiment per capacity point is added (3 concurrent experiments), yielding 9 experiments total. Latency defaults to 50 ms, CC defaults to cubic, AQM defaults to fq_codel, no cross-traffic, 1 trial per configuration. Duration will follow application defaults (YouTube: 60s, Zoom: 120s). A constraint check notes that at 10 Mbps, both YouTube and Zoom are well above their minimum viable capacity thresholds, so no warnings are triggered."

INTENT: "YouTube at 10 Mbps with high-burstiness cross-traffic"
EXTRACTED:
{
  "applications": [
    "youtube"
  ],
  "capacities": [
    10
  ],
  "latencies": None,
  "cc_algorithms": None,
  "aqm_policy": None,
  "ctp_cluster": "ctp_mobile_bursty",
  "duration_seconds": None,
  "num_trials": 1,
  "clarification_needed": [
    "Latency is not specified \u2014 will default to 50 ms. Should a latency sweep or a specific value be used instead?",
    "Number of trials is not specified \u2014 defaulting to 1. More trials (e.g., 3\u20135) are recommended for statistical reliability, especially with bursty cross-traffic.",
    "Should CC algorithm or AQM policy be varied, or are defaults (cubic / fq_codel) acceptable?"
  ],
  "design_type": [
    "isolated"
  ],
  "reasoning": "The intent clearly specifies YouTube as the application and 10 Mbps as the link capacity. 'High-burstiness cross-traffic' maps directly to the documented CTP cluster 'ctp_mobile_bursty', which is characterized as high-burstiness with medium average load \u2014 the best match among available clusters. No latency, CC algorithm, AQM policy, or duration were specified, so defaults will apply (50 ms, cubic, fq_codel, 60s). This is a single isolated YouTube experiment with one specific CTP, so the design type is 'isolated'. The 10 Mbps capacity is above the 3 Mbps warning threshold for YouTube, so no constraint violations are triggered. A note is raised about using only 1 trial with bursty cross-traffic, since variability may be high and more trials would improve reliability."
}
REASONING: "The intent clearly specifies YouTube as the application and 10 Mbps as the link capacity. 'High-burstiness cross-traffic' maps directly to the documented CTP cluster 'ctp_mobile_bursty', which is characterized as high-burstiness with medium average load — the best match among available clusters. No latency, CC algorithm, AQM policy, or duration were specified, so defaults will apply (50 ms, cubic, fq_codel, 60s). This is a single isolated YouTube experiment with one specific CTP, so the design type is 'isolated'. The 10 Mbps capacity is above the 3 Mbps warning threshold for YouTube, so no constraint violations are triggered. A note is raised about using only 1 trial with bursty cross-traffic, since variability may be high and more trials would improve reliability."

INTENT: "Run iperf3 and wget together at 25 Mbps with 50ms latency under cubic"
EXTRACTED:
{
  "applications": [
    "iperf3",
    "wget"
  ],
  "application_type": "shell",
  "capacities": [
    25
  ],
  "latencies": [
    50
  ],
  "cc_algorithms": [
    "cubic"
  ],
  "aqm_policy": None,
  "ctp_cluster": None,
  "duration_seconds": 30,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": [
    "concurrent"
  ],
  "reasoning": "The user explicitly says 'together', indicating concurrent execution on the same bottleneck. Both iperf3 and wget are shell applications. A single concurrent experiment at 25 Mbps, 50 ms latency, under cubic is generated. No isolated experiments are needed since the user specifically asked for them together."
}
REASONING: "The user explicitly says 'together', indicating concurrent execution on the same bottleneck. Both iperf3 and wget are shell applications. A single concurrent experiment at 25 Mbps, 50 ms latency, under cubic is generated. No isolated experiments are needed since the user specifically asked for them together."

INTENT: "Compare YouTube and NDT at 10 and 50 Mbps, both alone and together"
EXTRACTED:
{
  "applications": [
    "youtube",
    "ndt"
  ],
  "application_type": "mixed",
  "capacities": [
    10,
    50
  ],
  "latencies": None,
  "cc_algorithms": None,
  "aqm_policy": None,
  "ctp_cluster": None,
  "duration_seconds": None,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": [
    "full"
  ],
  "reasoning": "The user says 'both alone and together', which maps to design_type 'full' — generating both isolated experiments (each app separately) and concurrent experiments (both apps on the same bottleneck). YouTube is a browser app and NDT is a shell tool, so application_type is 'mixed'. At 2 capacities × 2 apps isolated + 2 capacities concurrent = 6 experiments total."
}
REASONING: "The user says 'both alone and together', which maps to design_type 'full' — generating both isolated experiments (each app separately) and concurrent experiments (both apps on the same bottleneck). YouTube is a browser app and NDT is a shell tool, so application_type is 'mixed'. At 2 capacities × 2 apps isolated + 2 capacities concurrent = 6 experiments total."

INTENT: "YouTube, 10 Mbps, 50ms, CUBIC, fq_codel, 60s, 3 trials"
EXTRACTED:
{
  "applications": [
    "youtube"
  ],
  "capacities": [
    10
  ],
  "latencies": [
    50
  ],
  "cc_algorithms": [
    "cubic"
  ],
  "aqm_policy": "fq_codel",
  "ctp_cluster": None,
  "duration_seconds": 60,
  "num_trials": 3,
  "clarification_needed": [],
  "design_type": [
    "isolated"
  ],
  "reasoning": "All parameters are explicitly and fully specified by the user: application is YouTube, capacity is 10 Mbps (within valid range [0.1, 10000]), latency is 50 ms (within valid range [0, 10000]), CC algorithm is CUBIC (valid), AQM policy is fq_codel (valid default), duration is 60s (matches YouTube application default), and num_trials is 3. No cross-traffic profile was mentioned so ctp_cluster is None. There is only a single application with a single configuration point, so this is a straightforward isolated experiment. No constraint violations: 10 Mbps is well above the 3 Mbps YouTube warning threshold, and 50 ms latency is well within acceptable bounds. No clarification is needed."
}
REASONING: "All parameters are explicitly and fully specified by the user: application is YouTube, capacity is 10 Mbps (within valid range [0.1, 10000]), latency is 50 ms (within valid range [0, 10000]), CC algorithm is CUBIC (valid), AQM policy is fq_codel (valid default), duration is 60s (matches YouTube application default), and num_trials is 3. No cross-traffic profile was mentioned so ctp_cluster is None. There is only a single application with a single configuration point, so this is a straightforward isolated experiment. No constraint violations: 10 Mbps is well above the 3 Mbps YouTube warning threshold, and 50 ms latency is well within acceptable bounds. No clarification is needed."