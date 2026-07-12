# Intent Token Usage

Per-intent Anthropic (orchestrator LLM) token accounting. One section per submitted intent.

## orch-be550ec2 — 2026-07-12T03:03:43Z

- **Intent:** Run a wget download from https://speed.cloudflare.com/__down?bytes=10485760 over a 10 Mbps bottleneck with 20 ms added latency, pfifo queue, the queue size of 200 packets and cubic congestion control. One trial, 30 seconds
- **Provider / Model:** anthropic / claude-sonnet-4-6
- **Status:** complete
- **Orchestrator LLM calls:** 3
- **Input tokens:** 14611
- **Output tokens:** 1281
- **Total tokens:** 15892
- **Experiments generated:** 1
- **Parsed params:** cc=['cubic']  capacities_mbps=[10.0]  latencies_ms=[20.0]  aqm=pfifo  buffer_packets=200  num_trials=1  duration_s=30  applications=['wget']  application_type=shell
- **Per-model breakdown:** claude-sonnet-4-6: in=14611 out=1281 total=15892 calls=3

```json
{
  "orchestration_id": "orch-be550ec2",
  "timestamp": "2026-07-12T03:03:43Z",
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "status": "complete",
  "llm_calls": 3,
  "input_tokens": 14611,
  "output_tokens": 1281,
  "total_tokens": 15892,
  "experiments_generated": 1,
  "by_model": {
    "claude-sonnet-4-6": {
      "input": 14611,
      "output": 1281,
      "total": 15892,
      "calls": 3
    }
  }
}
```

## orch-96008194 — 2026-07-12T03:29:43Z

- **Intent:** Run a wget download from https://speed.cloudflare.com/__down?bytes=10485760 over a 10 Mbps bottleneck with 20 ms added latency, pfifo queue, the queue size of 200 packets and cubic congestion control. One trial, 30 seconds
- **Provider / Model:** anthropic / claude-sonnet-4-6
- **Status:** complete
- **Orchestrator LLM calls:** 3
- **Input tokens:** 14611
- **Output tokens:** 1252
- **Total tokens:** 15863
- **Experiments generated:** 1
- **Parsed params:** cc=['cubic']  capacities_mbps=[10.0]  latencies_ms=[20.0]  aqm=pfifo  buffer_packets=200  num_trials=1  duration_s=30  applications=['wget']  application_type=shell
- **Per-model breakdown:** claude-sonnet-4-6: in=14611 out=1252 total=15863 calls=3
- **Per-call breakdown:**
  1. `parse_intent` (claude-sonnet-4-6): in=12282 out=605 total=12887
  2. `choose_workflow` (claude-sonnet-4-6): in=1259 out=279 total=1538
  3. `choose_workflow` (claude-sonnet-4-6): in=1070 out=368 total=1438

```json
{
  "orchestration_id": "orch-96008194",
  "timestamp": "2026-07-12T03:29:43Z",
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "status": "complete",
  "llm_calls": 3,
  "input_tokens": 14611,
  "output_tokens": 1252,
  "total_tokens": 15863,
  "experiments_generated": 1,
  "by_model": {
    "claude-sonnet-4-6": {
      "input": 14611,
      "output": 1252,
      "total": 15863,
      "calls": 3
    }
  },
  "calls": [
    {
      "label": "parse_intent",
      "model": "claude-sonnet-4-6",
      "input": 12282,
      "output": 605,
      "total": 12887
    },
    {
      "label": "choose_workflow",
      "model": "claude-sonnet-4-6",
      "input": 1259,
      "output": 279,
      "total": 1538
    },
    {
      "label": "choose_workflow",
      "model": "claude-sonnet-4-6",
      "input": 1070,
      "output": 368,
      "total": 1438
    }
  ]
}
```
