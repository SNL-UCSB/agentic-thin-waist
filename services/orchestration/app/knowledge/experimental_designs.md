# Experimental Designs

This file documents **common experimental design patterns** that Claude can use when translating high-level intents into concrete experiment sets.

## Capacity Sweeps

- **Goal**: Understand how an application's QoE changes as link capacity varies.
- **Pattern**: Fix latency, AQM, and CC; vary capacity over a set of values.
- **Example**: "Test YouTube at 5, 10, 25, 50 Mbps."
- **Design**:
  - applications: \[youtube\]
  - capacities: e.g., \[5, 10, 25, 50\]
  - latencies: default (e.g., 50 ms) unless specified
  - cc_algorithms: default (cubic) unless specified

## Latency Sweeps

- **Goal**: Measure sensitivity to propagation / queueing delay.
- **Pattern**: Fix capacity, AQM, and CC; vary latency.
- **Example**: "How does Zoom behave between 20ms and 300ms?"
- **Design**:
  - applications: \[zoom\]
  - capacities: e.g., \[10\] Mbps
  - latencies: e.g., \[20, 50, 100, 200, 300\] ms

## CC Algorithm Comparisons

- **Goal**: Compare congestion control algorithms under identical network and application conditions.
- **Pattern**: Fix capacity, latency, AQM, and application; vary CC.
- **Example**: "Compare CUBIC vs BBR for YouTube at 10 Mbps."
- **Design**:
  - applications: \[youtube\]
  - capacities: \[10\] Mbps
  - latencies: \[50\] ms (default) or user-specified
  - cc_algorithms: e.g., \[cubic, bbr\]

## Application Comparisons

- **Goal**: Compare multiple applications under the same network conditions.
- **Pattern**: Fix capacity, latency, AQM, and CC; vary application.
- **Example**: "Compare YouTube vs Zoom at 25 Mbps."
- **Design**:
  - applications: \[youtube, zoom\]
  - capacities: \[25\] Mbps
  - latencies: default or user-specified

## Full Cartesian Designs

- **Goal**: Explore the full interaction of multiple parameters (apps × capacities × latencies × CCs).
- **Pattern**: Cartesian product over all provided lists.
- **Example**: "YouTube and Zoom at 10, 25, 50 Mbps."
- **Design**:
  - applications: \[youtube, zoom\]
  - capacities: \[10, 25, 50\] Mbps
  - latencies: default or user-specified
  - cc_algorithms: default or user-specified

Claude SHOULD:

- Prefer **simpler designs** (capacity or latency sweeps, CC comparisons) when the user intent is vague.
- Only propose full Cartesian designs when the user explicitly asks for exhaustive exploration or when the parameter space is small.
- Estimate the **number of resulting experiments** and call out when a design is unusually large.