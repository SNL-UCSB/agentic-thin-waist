# Cross-Parameter Constraints

Claude SHOULD use these constraints to **warn about or reject** unphysical or low-value experiment configurations.  
Warnings mean "allowed but probably not useful"; hard violations mean "do not propose unless the user insists".

## Application-Specific Constraints

- If `capacity_mbps < 1` and `application = zoom`: **WARN** — Zoom typically requires \(\~1.5 Mbps\) minimum for reasonable video quality.
- If `capacity_mbps < 5` and `application = netflix`: **WARN** — Netflix minimum for SD is \(\~3 Mbps\); HD requires significantly more.
- If `capacity_mbps < 3` and `application = youtube`: **WARN** — YouTube may drop to very low resolutions or stall frequently.
- If `capacity_mbps < 2` and `application in [twitch, google-meet, discord]`: **WARN** — real-time / live workloads will likely degrade.

## Latency Constraints

- If `latency_ms > 300` and `application in [zoom, google-meet, discord]`: **WARN** — real-time communication degrades severely.
- If `latency_ms > 500` and `application in [youtube, netflix, twitch]`: **WARN** — interactive control (seek, pause) feels very sluggish.
- If `latency_ms > 1000`: **WARN** for all applications — this is an extreme regime; use only for stress tests.

## Duration and Trial Constraints

- If `duration_seconds < 30` and `application in [youtube, netflix, twitch]`:
  - **WARN** — flows may not reach steady state; avoid unless explicitly studying startup transients.
- If `duration_seconds < 20` and `application in [zoom, google-meet, discord]`:
  - **WARN** — too short to capture meaningful conferencing behavior.
- If `num_trials > 10` AND the number of distinct capacity values is `> 5`:
  - **WARN** — this likely generates \> 50 experiments; make sure the user understands the cost.

## Extreme Loss Regimes

- If `loss_rate > 10` and `application in [zoom, google-meet, discord]`: **WARN** — call quality will be extremely poor.
- If `loss_rate > 20` and `application in [youtube, netflix, twitch]`: **WARN** — streaming performance will collapse (constant rebuffering).
- If `loss_rate > 50`: **WARN** for all applications — treat as a pathological stress test only.

## General Guidance

Claude SHOULD:

- Prefer **useful** regimes (reasonable capacity/latency/loss) unless the user explicitly asks for stress tests.
- Surface these constraints in natural language explanations (e.g., "This configuration is technically allowed but likely unusable for Zoom").
- Ask the user for clarification when proposed parameters appear to violate multiple constraints.