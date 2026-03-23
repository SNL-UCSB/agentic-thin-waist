INTENT: "Run YouTube at 10 Mbps"
EXTRACTED:
{
  "applications": [
    "youtube"
  ],
  "capacities": [
    10
  ],
  "latencies": null,
  "cc_algorithms": null,
  "aqm_policy": null,
  "duration_seconds": null,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": "isolated",
  "reasoning": "The intent is straightforward: run a single YouTube experiment at 10 Mbps. The application is clearly 'youtube' and the capacity is explicitly given as 10 Mbps. No latency, CC algorithm, AQM policy, or duration were specified, so defaults will apply: latency_ms=50, cc_algorithm='cubic', aqm_policy='fq_codel', and duration_seconds=60 (YouTube default). 10 Mbps is well above the 3 Mbps minimum threshold for YouTube, so no constraint warnings are triggered. This is a simple isolated experiment with a single configuration point \u2014 no sweep or comparison is implied."
}
REASONING: "The intent is straightforward: run a single YouTube experiment at 10 Mbps. The application is clearly 'youtube' and the capacity is explicitly given as 10 Mbps. No latency, CC algorithm, AQM policy, or duration were specified, so defaults will apply: latency_ms=50, cc_algorithm='cubic', aqm_policy='fq_codel', and duration_seconds=60 (YouTube default). 10 Mbps is well above the 3 Mbps minimum threshold for YouTube, so no constraint warnings are triggered. This is a simple isolated experiment with a single configuration point — no sweep or comparison is implied."

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
  "latencies": null,
  "cc_algorithms": null,
  "aqm_policy": null,
  "duration_seconds": null,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": "isolated",
  "reasoning": "The intent clearly specifies a capacity sweep for YouTube at three capacity values: 10, 25, and 50 Mbps. This is a standard capacity sweep design pattern. No latency, CC algorithm, AQM policy, or duration were specified, so defaults will be applied: latency=50ms, cc_algorithm=cubic, aqm_policy=fq_codel, and duration=60s (YouTube application default). All three capacity values are well within the valid range [0.1, 10000] Mbps and are appropriate for YouTube (all are above the 3 Mbps warning threshold). No clarification is needed."
}
REASONING: "The intent clearly specifies a capacity sweep for YouTube at three capacity values: 10, 25, and 50 Mbps. This is a standard capacity sweep design pattern. No latency, CC algorithm, AQM policy, or duration were specified, so defaults will be applied: latency=50ms, cc_algorithm=cubic, aqm_policy=fq_codel, and duration=60s (YouTube application default). All three capacity values are well within the valid range [0.1, 10000] Mbps and are appropriate for YouTube (all are above the 3 Mbps warning threshold). No clarification is needed."

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
  "latencies": null,
  "cc_algorithms": null,
  "aqm_policy": null,
  "duration_seconds": null,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": "full",
  "reasoning": "The user explicitly requests an application comparison between YouTube and Zoom at a fixed capacity of 25 Mbps. This is a classic application comparison design pattern: two applications tested under identical network conditions. Capacity is clearly specified at 25 Mbps, which is well above the minimum thresholds for both YouTube (~3 Mbps) and Zoom (~1.5 Mbps), so no constraint warnings apply. Latency is not specified, so the default of 50 ms will be used. CC algorithm defaults to cubic and AQM defaults to fq_codel per system knowledge. Duration is not specified, so application defaults will apply: 60s for YouTube and 120s for Zoom. No cross-traffic is mentioned, so no CTP will be attached. The design is straightforward with only 2 experiments (one per application), making it a small, cost-efficient comparison. No clarifications are needed."
}
REASONING: "The user explicitly requests an application comparison between YouTube and Zoom at a fixed capacity of 25 Mbps. This is a classic application comparison design pattern: two applications tested under identical network conditions. Capacity is clearly specified at 25 Mbps, which is well above the minimum thresholds for both YouTube (~3 Mbps) and Zoom (~1.5 Mbps), so no constraint warnings apply. Latency is not specified, so the default of 50 ms will be used. CC algorithm defaults to cubic and AQM defaults to fq_codel per system knowledge. Duration is not specified, so application defaults will apply: 60s for YouTube and 120s for Zoom. No cross-traffic is mentioned, so no CTP will be attached. The design is straightforward with only 2 experiments (one per application), making it a small, cost-efficient comparison. No clarifications are needed."

INTENT: "Compare CUBIC vs BBR for YouTube at 10 Mbps"
EXTRACTED:
{
  "applications": [
    "youtube"
  ],
  "capacities": [
    10
  ],
  "latencies": null,
  "cc_algorithms": [
    "cubic",
    "bbr"
  ],
  "aqm_policy": null,
  "duration_seconds": null,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": "isolated",
  "reasoning": "The intent is a classic CC algorithm comparison design: fix the application (YouTube) and capacity (10 Mbps), then vary the CC algorithm across cubic and BBR. Latency is not specified, so the default of 50 ms will be used. AQM policy is not specified, so the default fq_codel will be used. Duration is not specified, so the YouTube application default of 60s will be used. num_trials defaults to 1. The 10 Mbps capacity is well above the YouTube minimum (~3 Mbps), so no constraint warnings apply. This is a clean, interpretable isolated comparison with only 2 experiments, directly answering how CUBIC vs BBR affects YouTube QoE under identical network conditions."
}
REASONING: "The intent is a classic CC algorithm comparison design: fix the application (YouTube) and capacity (10 Mbps), then vary the CC algorithm across cubic and BBR. Latency is not specified, so the default of 50 ms will be used. AQM policy is not specified, so the default fq_codel will be used. Duration is not specified, so the YouTube application default of 60s will be used. num_trials defaults to 1. The 10 Mbps capacity is well above the YouTube minimum (~3 Mbps), so no constraint warnings apply. This is a clean, interpretable isolated comparison with only 2 experiments, directly answering how CUBIC vs BBR affects YouTube QoE under identical network conditions."

INTENT: "How does Netflix perform?"
EXTRACTED:
{
  "applications": [
    "netflix"
  ],
  "capacities": null,
  "latencies": null,
  "cc_algorithms": null,
  "aqm_policy": null,
  "duration_seconds": 60,
  "num_trials": 1,
  "clarification_needed": [
    "No capacity range specified \u2014 what link speeds should be tested? Common choices: a sweep at 3, 5, 10, 25, 50 Mbps (covering SD through 4K regimes), a single mid-range point (e.g. 25 Mbps), or a custom range.",
    "No latency specified \u2014 should a default of 50 ms be used, or is a latency sweep (e.g. 20, 50, 100, 200 ms) desired?",
    "No congestion control algorithm specified \u2014 should the default (cubic) be used, or is a CC comparison (e.g. cubic vs. bbr) part of the goal?",
    "No cross-traffic / background load specified \u2014 should experiments run in isolation, or with a representative CTP (e.g. ctp_low_background for typical home use)?"
  ],
  "design_type": "needs_clarification",
  "reasoning": "The intent 'How does Netflix perform?' implies a performance characterization study for the netflix application. The default duration of 60s (from application_defaults) is applied. However, the question is highly underspecified: no capacity range, latency regime, CC algorithm, AQM policy, or cross-traffic profile is given. Without at least a capacity range, it is impossible to design a meaningful experiment \u2014 Netflix requires at minimum ~3 Mbps for SD and significantly more for HD/4K, so the capacity axis is critical to the research question. A capacity sweep (e.g. 3, 5, 10, 25, 50 Mbps) would be the most natural first design, but this needs user confirmation. All other parameters are left null pending clarification, and defaults (cubic CC, fq_codel AQM) would be applied to any generated experiments."
}
REASONING: "The intent 'How does Netflix perform?' implies a performance characterization study for the netflix application. The default duration of 60s (from application_defaults) is applied. However, the question is highly underspecified: no capacity range, latency regime, CC algorithm, AQM policy, or cross-traffic profile is given. Without at least a capacity range, it is impossible to design a meaningful experiment — Netflix requires at minimum ~3 Mbps for SD and significantly more for HD/4K, so the capacity axis is critical to the research question. A capacity sweep (e.g. 3, 5, 10, 25, 50 Mbps) would be the most natural first design, but this needs user confirmation. All other parameters are left null pending clarification, and defaults (cubic CC, fq_codel AQM) would be applied to any generated experiments."

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
  "latencies": null,
  "cc_algorithms": null,
  "aqm_policy": null,
  "duration_seconds": null,
  "num_trials": 1,
  "clarification_needed": [],
  "design_type": "full",
  "reasoning": "The intent clearly specifies two applications (YouTube and Zoom) and three capacity values (10, 25, 50 Mbps), which maps directly to a full Cartesian design pattern from the experimental designs knowledge file. This will produce 6 experiments (2 apps \u00d7 3 capacities). Latency is not specified, so the default of 50 ms will be used. CC algorithm is not specified, so the default of 'cubic' will be used. AQM policy is not specified, so the default of 'fq_codel' will be used. Duration will use per-application defaults: 60s for YouTube and 120s for Zoom. No cross-traffic (CTP) was mentioned, so none will be applied. No clarification is needed \u2014 the intent is unambiguous and the resulting experiment set is small and well-defined."
}
REASONING: "The intent clearly specifies two applications (YouTube and Zoom) and three capacity values (10, 25, 50 Mbps), which maps directly to a full Cartesian design pattern from the experimental designs knowledge file. This will produce 6 experiments (2 apps × 3 capacities). Latency is not specified, so the default of 50 ms will be used. CC algorithm is not specified, so the default of 'cubic' will be used. AQM policy is not specified, so the default of 'fq_codel' will be used. Duration will use per-application defaults: 60s for YouTube and 120s for Zoom. No cross-traffic (CTP) was mentioned, so none will be applied. No clarification is needed — the intent is unambiguous and the resulting experiment set is small and well-defined."

INTENT: "YouTube at 10 Mbps with high-burstiness cross-traffic"
EXTRACTED:
{
  "applications": [
    "youtube"
  ],
  "capacities": [
    10
  ],
  "latencies": null,
  "cc_algorithms": null,
  "aqm_policy": null,
  "duration_seconds": null,
  "num_trials": 1,
  "clarification_needed": [
    "The intent mentions 'high-burstiness cross-traffic' which maps to the CTP cluster 'ctp_mobile_bursty' (bursty mobile traffic, medium avg load) or possibly 'ctp_chatty_apps' (many small interactive flows, high burstiness). Please confirm which best matches your intent, or whether both should be tested.",
    "Latency is not specified. Should the default of 50ms be used, or is a specific propagation delay regime of interest?",
    "CC algorithm is not specified. Should the default (cubic) be used, or is a comparison across multiple CC algorithms desired?",
    "Number of trials is not specified. The default is 1, but for cross-traffic experiments more trials (e.g., 3\u20135) are often advisable to reduce variance from bursty interference."
  ],
  "design_type": "needs_clarification",
  "reasoning": "The intent is clear about the application (YouTube) and capacity (10 Mbps). The phrase 'high-burstiness cross-traffic' maps to a CTP cluster \u2014 the best candidates from the documented taxonomy are 'ctp_mobile_bursty' (high burstiness, medium avg load) or 'ctp_chatty_apps' (high burstiness, low-medium avg load). Both have high burstiness but differ in average load, which affects how much they compete with YouTube. Clarification is needed to select the right cluster. Latency, CC algorithm, and AQM policy are unspecified; defaults (50ms, cubic, fq_codel) can be applied but should be confirmed. Since cross-traffic introduces run-to-run variance, increasing num_trials beyond the default of 1 is advisable."
}
REASONING: "The intent is clear about the application (YouTube) and capacity (10 Mbps). The phrase 'high-burstiness cross-traffic' maps to a CTP cluster — the best candidates from the documented taxonomy are 'ctp_mobile_bursty' (high burstiness, medium avg load) or 'ctp_chatty_apps' (high burstiness, low-medium avg load). Both have high burstiness but differ in average load, which affects how much they compete with YouTube. Clarification is needed to select the right cluster. Latency, CC algorithm, and AQM policy are unspecified; defaults (50ms, cubic, fq_codel) can be applied but should be confirmed. Since cross-traffic introduces run-to-run variance, increasing num_trials beyond the default of 1 is advisable."

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
  "duration_seconds": 60,
  "num_trials": 3,
  "clarification_needed": [],
  "design_type": "isolated",
  "reasoning": "All parameters are fully and explicitly specified in the intent. Application is 'youtube', capacity is 10 Mbps (within valid range [0.1, 10000]), latency is 50 ms (within valid range [0, 10000]), CC algorithm is 'cubic' (valid), AQM policy is 'fq_codel' (valid and also the default), duration is 60 seconds (matches YouTube's application default and is within [10, 3600]), and num_trials is 3 (within [1, 100]). No constraints are violated: 10 Mbps is well above the 3 Mbps YouTube warning threshold, and 50 ms latency is well within acceptable bounds. This is a single, fully-specified isolated experiment configuration requiring no clarification."
}
REASONING: "All parameters are fully and explicitly specified in the intent. Application is 'youtube', capacity is 10 Mbps (within valid range [0.1, 10000]), latency is 50 ms (within valid range [0, 10000]), CC algorithm is 'cubic' (valid), AQM policy is 'fq_codel' (valid and also the default), duration is 60 seconds (matches YouTube's application default and is within [10, 3600]), and num_trials is 3 (within [1, 100]). No constraints are violated: 10 Mbps is well above the 3 Mbps YouTube warning threshold, and 50 ms latency is well within acceptable bounds. This is a single, fully-specified isolated experiment configuration requiring no clarification."