# Parameter Ranges

These ranges define the **allowed** space Claude should use when proposing experiments.  
Anything outside these bounds should be treated as invalid and either rejected or explicitly justified.

| Parameter         | Min   | Max   | Default | Unit    |
|------------------|-------|-------|---------|---------|
| capacity_mbps    | 0.1   | 10000 | 25      | Mbps    |
| latency_ms       | 0     | 10000 | 50      | ms      |
| loss_rate        | 0     | 100   | 0       | %       |
| duration_seconds | 10    | 3600  | 60      | seconds |
| num_trials       | 1     | 100   | 1       | count   |
| buffer_packets   | 1     | 100000| 1000    | packets |

Claude SHOULD:

- Keep capacity values within \[0.1, 10000\] Mbps.
- Keep latency values within \[0, 10000\] ms.
- Keep loss rates within \[0, 100\]%.
- Prefer the defaults when the user has not specified a value.

## Congestion Control Algorithms

Valid congestion control (CC) algorithms:

- cubic (default)
- bbr
- reno
- htcp
- vegas
- bic

Claude SHOULD:

- Default to **cubic** when no CC algorithm is specified.
- Never invent CC algorithms that are not in this list.

## AQM Policies

Valid Active Queue Management (AQM) policies:

- pfifo (packet FIFO; `tc` has no qdisc literally named `fifo` — always emit `pfifo`)
- codel
- pie
- fq_codel (default)

Claude SHOULD:

- Default to **fq_codel** when no AQM policy is specified.
- Treat unknown AQM names as invalid and ask for clarification.