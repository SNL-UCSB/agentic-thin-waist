# Orchestration Service

**Port**: 8005
**Deliverable**: D5 (Agentic Orchestration - Claude + OpenClaw)
**Priority**: MEDIUM
**Status**: To be implemented

## Purpose

The Orchestration Service is the agentic interface that interprets natural language research intents and translates them into concrete experiment specifications. It uses Claude (via Anthropic API) and OpenClaw framework to implement multi-step reasoning about network conditions, applications, and experimental design.

The Orchestration Service:

1. **Accepts research intents** — Natural language descriptions of research goals
2. **Reasons about network conditions** — Translate intent to specific CTPs
3. **Generates experiment specs** — Create JSON experiment definitions
4. **Manages tool/skill declarations** — Define available services as Tools (OpenClaw)
5. **Orchestrates execution** — Dispatch experiments to Experiment API and track results
6. **Interprets complex queries** — Handle multi-step requests (e.g., parameter sweeps)

This service acts as the "smart interface" that bridges researchers and infrastructure.

## Architecture

```
┌──────────────────────────────────────┐
│   Researcher (Natural Language)       │
│   "Compare YouTube vs Zoom at        │
│    10, 25, 50 Mbps with 50ms latency"│
└────────────┬────────────────────────┘
             │ POST /intent
             ▼
┌────────────────────────────────────┐
│  ORCHESTRATION SERVICE (8005)      │
│  Claude + OpenClaw                 │
│  ┌──────────────────────────────┐  │
│  │ Intent Parser                │  │
│  │ Claude Reasoning Engine      │  │
│  │ Tool/Skill Declarations      │  │
│  │ Experiment Generator         │  │
│  └──────────────────────────────┘  │
└────────────┬──────────────────────┘
             │ (through API Gateway)
      ┌──────┴──────┬─────────┐
      ▼             ▼         ▼
  ┌─────────┐ ┌────────┐ ┌──────────┐
  │Experiment│ │Storage │ │CTP       │
  │API :8000 │ │:8004   │ │Service   │
  │          │ │        │ │:8001     │
  └─────────┘ └────────┘ └──────────┘
```

## API Specification

### 1. Submit Research Intent

**Endpoint**: `POST /intent`

**Request**:
```json
{
  "intent": "Compare YouTube vs Zoom at 10, 25, 50 Mbps with 50ms latency",
  "context": {
    "num_trials": 1,
    "duration_seconds": 60,
    "default_latency_ms": 50
  },
  "preferences": {
    "capture_pcap": true,
    "run_immediately": true
  }
}
```

**Response** (202 Accepted):
```json
{
  "orchestration_id": "orch-xyz789",
  "status": "processing",
  "intent": "Compare YouTube vs Zoom at 10, 25, 50 Mbps with 50ms latency",
  "generated_experiments": 6,
  "estimated_duration_minutes": 10
}
```

**Processing Steps**:
1. Parse intent with Claude
2. Identify applications (YouTube, Zoom)
3. Identify capacity values (10, 25, 50)
4. Identify latency value (50)
5. Generate 6 experiments (2 apps × 3 capacities)
6. Return orchestration_id for status tracking

---

### 2. Get Orchestration Status

**Endpoint**: `GET /orchestration/{orchestration_id}`

**Response** (200 OK):
```json
{
  "orchestration_id": "orch-xyz789",
  "status": "executing",
  "progress": {
    "experiments_total": 6,
    "experiments_created": 6,
    "experiments_running": 2,
    "experiments_complete": 1,
    "percent_complete": 30
  },
  "generated_experiments": [
    {
      "experiment_id": "youtube-10mbps-001",
      "status": "complete",
      "results_available": true
    },
    {
      "experiment_id": "youtube-25mbps-001",
      "status": "running",
      "results_available": false
    },
    {
      "experiment_id": "zoom-10mbps-001",
      "status": "pending",
      "results_available": false
    }
  ],
  "estimated_completion": "2026-03-04T10:45:00Z"
}
```

**States**:
- pending — Created, awaiting processing
- parsing — Claude analyzing intent
- generating — Creating experiment specs
- executing — Experiments running
- complete — All experiments done
- failed — Error occurred

---

### 3. Get Orchestration Results

**Endpoint**: `GET /orchestration/{orchestration_id}/results`

**Response** (200 OK):
```json
{
  "orchestration_id": "orch-xyz789",
  "intent": "Compare YouTube vs Zoom at 10, 25, 50 Mbps with 50ms latency",
  "status": "complete",
  "completed_at": "2026-03-04T10:45:00Z",
  "experiment_results": [
    {
      "experiment_id": "youtube-10mbps-001",
      "application": "youtube",
      "capacity_mbps": 10,
      "latency_ms": 50,
      "qoe_metrics": {
        "video_startup_time_ms": 2500,
        "mean_bitrate_mbps": 8.5,
        "rebuffer_events": 1
      }
    },
    {
      "experiment_id": "youtube-25mbps-001",
      "application": "youtube",
      "capacity_mbps": 25,
      "latency_ms": 50,
      "qoe_metrics": {
        "video_startup_time_ms": 1200,
        "mean_bitrate_mbps": 23.5,
        "rebuffer_events": 0
      }
    },
    {
      "experiment_id": "zoom-10mbps-001",
      "application": "zoom",
      "capacity_mbps": 10,
      "latency_ms": 50,
      "qoe_metrics": {
        "video_quality": "720p",
        "audio_quality": "high",
        "packet_loss_percent": 0.1
      }
    }
  ],
  "summary": {
    "applications_tested": ["youtube", "zoom"],
    "capacities_tested": [10, 25, 50],
    "total_experiments": 6,
    "successful": 6,
    "failed": 0
  }
}
```

---

### 4. List Available Tools

**Endpoint**: `GET /tools`

**Response** (200 OK):
```json
{
  "tools": [
    {
      "tool_name": "run_experiment",
      "service": "Experiment API :8000",
      "description": "Create and run an experiment with given network conditions",
      "parameters": {
        "experiment_id": {"type": "string", "description": "Unique experiment ID"},
        "capacity_mbps": {"type": "number", "description": "Link capacity in Mbps"},
        "latency_ms": {"type": "number", "description": "RTT latency in ms"},
        "application": {"type": "string", "enum": ["youtube", "netflix", "zoom"]},
        "duration_seconds": {"type": "number"}
      }
    },
    {
      "tool_name": "query_results",
      "service": "Storage Service :8004",
      "description": "Query stored experiment results by filters",
      "parameters": {
        "application": {"type": "string"},
        "capacity_min": {"type": "number"},
        "capacity_max": {"type": "number"},
        "limit": {"type": "number"}
      }
    },
    {
      "tool_name": "validate_ctp",
      "service": "CTP Service :8001",
      "description": "Validate that a CTP configuration is valid",
      "parameters": {
        "capacity_mbps": {"type": "number"},
        "latency_ms": {"type": "number"}
      }
    }
  ]
}
```

---

### 5. List Available Skills

**Endpoint**: `GET /skills`

**Response** (200 OK):
```json
{
  "skills": [
    {
      "skill_name": "parameter_sweep",
      "description": "Run multiple experiments across a range of parameters",
      "input_schema": {
        "applications": {"type": "array", "items": {"type": "string"}},
        "capacity_range": {"type": "object", "properties": {"min": {"type": "number"}, "max": {"type": "number"}, "step": {"type": "number"}}},
        "latency_range": {"type": "object"}
      },
      "example": {
        "applications": ["youtube", "zoom"],
        "capacity_range": {"min": 10, "max": 50, "step": 5},
        "latency_range": {"min": 20, "max": 100, "step": 20}
      }
    },
    {
      "skill_name": "application_comparison",
      "description": "Compare multiple applications under the same network conditions",
      "input_schema": {
        "applications": {"type": "array"},
        "capacity_mbps": {"type": "number"},
        "latency_ms": {"type": "number"}
      }
    },
    {
      "skill_name": "baseline_establishment",
      "description": "Establish a baseline by testing with no network constraints",
      "input_schema": {
        "applications": {"type": "array"},
        "duration_seconds": {"type": "number"}
      }
    }
  ]
}
```

---

### 6. Get Claude Reasoning

**Endpoint**: `GET /orchestration/{orchestration_id}/reasoning`

**Response** (200 OK):
```json
{
  "orchestration_id": "orch-xyz789",
  "reasoning_steps": [
    {
      "step": 1,
      "action": "parse_intent",
      "input": "Compare YouTube vs Zoom at 10, 25, 50 Mbps with 50ms latency",
      "output": {
        "applications": ["youtube", "zoom"],
        "capacities": [10, 25, 50],
        "latency": 50
      },
      "reasoning": "Intent asks for comparison between two applications at three capacity points"
    },
    {
      "step": 2,
      "action": "generate_experiments",
      "output": [
        {
          "experiment_id": "youtube-10mbps-001",
          "capacity_mbps": 10,
          "latency_ms": 50,
          "application": "youtube"
        },
        "... 5 more experiments ..."
      ],
      "reasoning": "Cartesian product of [youtube, zoom] × [10, 25, 50] = 6 experiments"
    }
  ],
  "claude_model": "claude-opus-4-6",
  "total_tokens_used": 2341
}
```

---

### 7. Health Check

**Endpoint**: `GET /health`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "checks": {
    "claude_api": "connected",
    "experiment_api": "reachable",
    "storage_service": "reachable",
    "ctp_service": "reachable"
  },
  "model": "claude-opus-4-6"
}
```

## Dataclass Contracts

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

@dataclass
class ResearchIntent:
    """Natural language research goal."""
    intent: str
    context: Dict[str, Any] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GeneratedExperiment:
    """Experiment spec generated from intent."""
    experiment_id: str
    capacity_mbps: float
    latency_ms: float
    loss_rate: float
    application: str
    duration_seconds: int
    num_trials: int
    reasoning: str  # Claude's explanation

@dataclass
class OrchestrationRequest:
    """Submitted orchestration request."""
    orchestration_id: str
    intent: str
    status: str
    generated_experiments: List[str]
    created_at: str

@dataclass
class ReasoningStep:
    """Single step in Claude's reasoning."""
    step: int
    action: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    reasoning: str
```

## Configuration Files

### TOOLS.md

This file declares all available tools for Claude + OpenClaw:

```markdown
# Available Tools for Network Research Orchestration

## run_experiment(experiment_id, capacity_mbps, latency_ms, application, duration_seconds)
Create and run an experiment with specific network conditions.
- experiment_id (str): Unique ID for the experiment
- capacity_mbps (float): Link capacity in Mbps
- latency_ms (float): RTT latency in milliseconds
- application (str): "youtube", "netflix", "zoom", etc.
- duration_seconds (int): Experiment duration

## query_results(application, capacity_min, capacity_max, latency_min, latency_max)
Query stored results by filters.
Returns: List of ExperimentResult objects with QoE metrics.

## validate_ctp(capacity_mbps, latency_ms, loss_rate, aqm_policy)
Validate that network conditions are feasible.
Returns: {valid: bool, warnings: List[str]}

## get_available_applications()
List supported applications.
Returns: ["youtube", "netflix", "zoom", "twitch", "discord", "google-meet", ...]

## list_experiments()
Get all experiments and their status.
```

### SKILLS.md

This file declares high-level skills that combine multiple tools:

```markdown
# Available Skills for Multi-Step Workflows

## parameter_sweep
Run multiple experiments across a range of parameters.
Input:
  - applications: ["youtube", "zoom"]
  - capacity_range: {min: 10, max: 50, step: 5}
  - latency_range: {min: 20, max: 100, step: 20}
Generates: (2 apps) × (9 capacities) × (5 latencies) = 90 experiments

## application_comparison
Compare applications under identical conditions.
Input:
  - applications: ["youtube", "zoom"]
  - capacity_mbps: 25
  - latency_ms: 50
Generates: 2 experiments, same network conditions

## baseline_establishment
Test with minimal constraints to establish baseline performance.
Input:
  - applications: ["youtube"]
  - duration_seconds: 120
Generates: 1 experiment with 100 Mbps, 10ms latency (ideal conditions)

## network_characterization
Sweep both capacity and latency systematically.
Input:
  - applications: ["youtube"]
  - capacity_values: [5, 10, 25, 50, 100]
  - latency_values: [10, 25, 50, 100]
Generates: 20 experiments in factorial design
```

## Service Dependencies

| Service | Endpoint | Purpose |
|---------|----------|---------|
| Experiment API | POST /experiments | Create and execute experiments |
| Storage Service | GET /results | Query existing results |
| CTP Service | POST /ctps/validate | Validate network configs |

## Testing Criteria

### Unit Tests
- Intent parsing for various phrasings
- Parameter sweep generation (cartesian products)
- Reasoning step logging

### Integration Tests
- "Compare YouTube vs Zoom at 10, 25, 50 Mbps" generates 6 experiments
- "Parameter sweep: 10-50 Mbps in 10 Mbps steps, YouTube" generates 5 experiments
- Generated experiments are valid (pass CTP validation)
- Multi-step intents generate correct experiment counts
- Orchestration tracking follows all experiments to completion

### Performance Tests
- Intent parsing < 2s
- Experiment generation < 1s per experiment
- Full orchestration of 10 experiments < 2 minutes wall-clock

## Implementation Guide

### Step 1: Project Structure
```bash
services/orchestration/
├── Dockerfile
├── requirements.txt
├── TOOLS.md
├── SKILLS.md
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── intent.py
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── claude_client.py    # Anthropic API integration
│   │   ├── intent_parser.py    # Intent → structured form
│   │   ├── experiment_generator.py  # Structured → experiments
│   │   └── executor.py         # Run experiments
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── system.md           # Claude system prompt
│   │   └── examples.md         # Few-shot examples
│   └── models/
│       └── __init__.py
└── tests/
    ├── __init__.py
    └── test_*.py
```

### Step 2: Claude Integration
```python
# app/engine/claude_client.py
from anthropic import Anthropic

class ClaudeOrchestrator:
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-opus-4-6"

    def parse_intent(self, intent: str) -> Dict:
        """Use Claude to interpret natural language intent."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system="You are a network research orchestrator...",
            messages=[
                {"role": "user", "content": f"Parse this research intent:\n{intent}"}
            ]
        )
        # Parse response JSON
        return json.loads(response.content[0].text)
```

### Step 3: Intent Parser
```python
# app/engine/intent_parser.py
class IntentParser:
    def parse(self, intent: str) -> Dict:
        """Convert intent to structured parameters."""
        # Use Claude to extract:
        # - applications
        # - capacity values
        # - latency values
        # - other parameters

        return {
            "applications": ["youtube", "zoom"],
            "capacities": [10, 25, 50],
            "latencies": [50],
            "duration_seconds": 60
        }
```

### Step 4: Experiment Generator
```python
# app/engine/experiment_generator.py
class ExperimentGenerator:
    def generate(self, parsed_intent: Dict) -> List[GeneratedExperiment]:
        """Create experiment specs from parsed intent."""
        experiments = []
        for app in parsed_intent["applications"]:
            for capacity in parsed_intent["capacities"]:
                for latency in parsed_intent["latencies"]:
                    exp = GeneratedExperiment(
                        experiment_id=f"{app}-{capacity}mbps-{latency}ms-001",
                        capacity_mbps=capacity,
                        latency_ms=latency,
                        application=app,
                        duration_seconds=parsed_intent["duration_seconds"]
                    )
                    experiments.append(exp)
        return experiments
```

### Step 5: Execution Manager
```python
# app/engine/executor.py
class ExecutionManager:
    def __init__(self, experiment_api_url: str):
        self.experiment_api = ExperimentAPIClient(experiment_api_url)

    async def execute_experiments(self, experiments: List[GeneratedExperiment]):
        """Dispatch experiments and track progress."""
        for exp in experiments:
            response = await self.experiment_api.create_experiment(
                experiment_id=exp.experiment_id,
                capacity_mbps=exp.capacity_mbps,
                latency_ms=exp.latency_ms,
                application=exp.application,
                duration_seconds=exp.duration_seconds
            )
            # Track execution...
```

## Prompt Template (prompts/system.md)

```
You are a network research orchestration agent. Your role is to interpret
natural language research intents and generate concrete experiment specifications.

CONTEXT:
- Available applications: youtube, netflix, zoom, twitch, discord, google-meet
- Capacity range: 0.1 to 10000 Mbps
- Latency range: 0 to 10000 ms
- Supported AQM policies: fifo, codel, pie, fq_codel

TASK:
Given a research intent, extract:
1. Applications to test
2. Capacity values (Mbps) or ranges
3. Latency values (ms) or ranges
4. Duration (seconds)
5. Number of trials
6. Other parameters

OUTPUT:
Return a JSON object with the extracted parameters.

EXAMPLES:
[See examples.md]
```

## References

- Anthropic Claude API: https://docs.anthropic.com/claude/reference/
- OpenClaw framework: [Internal SNL-UCSB documentation]
- Prompt engineering: https://docs.anthropic.com/claude/docs/prompt-engineering
- Python async/await: https://docs.python.org/3/library/asyncio.html

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Implementation (Week 5)
