# Orchestration Service

**Port**: 8005
**Deliverable**: D5 (Agentic Orchestration — Natural Language Intent → Experiment Specs)
**Priority**: CRITICAL
**Status**: Specification Ready
**Lead**: Haarika
**PI**: Prof. Arpit Gupta

## Purpose

The Orchestration Service is the agentic brain of the Agentic Thin Waist. It interprets natural language research intents and translates them into concrete, executable experiment specifications. Built on Claude (Anthropic) as the LLM backbone, this service implements multi-step reasoning about network conditions, applications, and experimental design strategies. Claude reasons through hypotheses about bottlenecks, generates parameter sweeps, and orchestrates complex multi-step experiment workflows.

## Input

Orchestration Service accepts:
- Natural language research intent: "Compare YouTube vs Zoom at 10, 25, 50 Mbps with 50ms latency"
- Context parameters: number of trials, default latency, duration
- Preferences: capture PCAP, desired congestion control algorithms, execution strategy


## Output

Orchestration Service produces:
- Orchestration ID for tracking long-running experiment campaigns
- Generated experiment specifications (JSON): one per bottleneck regime
- Experiment progress tracking: pending, running, complete status
- Final aggregated results: all experiment metrics across parameter sweep
- Claude reasoning steps: extracted intent → parameter sweep → experiment specs

## Interfaces

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/intent` | POST | Submit NL research intent, returns orchestration_id |
| `/orchestration/{id}` | GET | Get orchestration status and experiment progress |
| `/orchestration/{id}/results` | GET | Get aggregated results from all experiments |
| `/orchestration/{id}/reasoning` | GET | Get Claude reasoning steps (for transparency) |
| `/tools` | GET | List available tools (run_experiment, query_results, etc.) |
| `/skills` | GET | List available skills (parameter_sweep, comparison, etc.) |
| `/health` | GET | Health check: Claude API, Experiment API, Telemetry Service |

## YouTube MVP Example

For intent "Generate traffic for YouTube at 100ms base latency and 6 Mbps":
- Claude parses intent → identifies: apps=[youtube], capacity=6Mbps, latency=100ms
- **Clarification step**: Claude surfaces defaults — "AQM policy: fq_codel. Congestion control: cubic. No cross-traffic specified — I have 20 CTP clusters available. Should I use all clusters, a specific subset, or no cross-traffic?" User confirms defaults, selects "high-burstiness clusters only."
- Claude queries CTP Service for cluster taxonomy → identifies 5 high-burstiness clusters
- Generates 5 iterations (one per CTP cluster): youtube-6mbps-100ms-cluster-3, youtube-6mbps-100ms-cluster-7, ...
- Dispatches to Experiment API, returns orchestration_id immediately (202)
- Client polls /orchestration/{id} to track: pending → running → complete
- GET /orchestration/{id}/results returns aggregated results across CTP clusters
- Success criteria: NL in → clarification → N iteration specs out → results aggregated end-to-end

**Composition examples**: For intent "Compare YouTube vs Zoom at 10, 25, 50 Mbps with 50ms latency under CUBIC":
- Claude must determine the **experiment design**: should YouTube and Zoom run in separate iterations (isolated) or concurrently within the same iteration (competing for the same link)?
- **Isolated design** (6 iterations): YouTube-only at 10/25/50 Mbps + Zoom-only at 10/25/50 Mbps. Answers: "How does each app perform in isolation under varying bandwidth?"
- **Concurrent design** (3 iterations): YouTube+Zoom simultaneously at 10/25/50 Mbps. Answers: "How do these apps interact when sharing a bottleneck?" Each iteration runs multiple NetGent workflows on one NetReplica configuration.
- **Full design** (9 iterations): Both isolated and concurrent runs. Answers: "How does each app perform alone vs. when competing?" This is the richest comparison but most expensive.
- Claude should clarify with the researcher which design is intended, since the choice fundamentally changes what the data can answer.

### Core Responsibilities

1. **Natural Language Intent Parsing** — Interpret researcher intent ("Compare YouTube vs Zoom at 10-50 Mbps")
2. **Interactive Clarification** — Surface defaults for unspecified parameters and let the user confirm or override. For example: "Your intent doesn't specify AQM policy — defaulting to fq_codel. You haven't specified cross-traffic — I have 20 CTP clusters available. Want all, a subset, or a specific cluster?" The system should never silently assume underspecified parameters.
3. **Multi-Step Reasoning** — Use Claude to reason about which experiments to run, bottleneck regimes to explore, and how to compose iterations — including whether applications should run in isolation or concurrently within the same iteration
4. **Experiment Specification Generation** — Create JSON experiment definitions and parameter sweeps. An experiment is a research campaign; each generated spec is one iteration (see Experiment API terminology).
5. **CTP-Aware Intent Specification** — Support dynamic attribute specification in intents. A user can say "use cross-traffic from high-burstiness clusters" or "sample 5 CTPs from Cluster A." The Orchestration Service queries the CTP Service's cluster taxonomy and generates iterations with appropriate CTP references.
6. **Tool & Skill Management** — Expose NetReplica/NetGent functions as OpenClaw tools; declare skills for multi-step workflows
7. **Execution Orchestration** — Dispatch iterations to Experiment API, track progress, handle failures
8. **Query & Refinement** — Interpret follow-up queries and refine experimental design iteratively

### Glia Paper Architecture Mapping

- **Glia's Researcher (LLM backbone)** → Claude (via Anthropic API)
- **Glia's Supervisor (high-level skills)** → SKILLS.md (parameter_sweep, application_comparison, network_characterization, etc.)
- **Tools in Glia** → TOOLS.md (run_experiment, query_results, validate_ctp, get_available_applications)
- **Core Loop** → hypothesis → experimentation → analysis → refinement

## Architecture

```
┌──────────────────────────────────────┐
│  Researcher / Scientist               │
│  "Compare YouTube vs Zoom at        │
│   10, 25, 50 Mbps with 50ms latency" │
└────────────┬────────────────────────┘
             │ POST /intent
             ▼
┌────────────────────────────────────┐
│ ORCHESTRATION SERVICE (8005)       │
│ Claude LLM + OpenClaw Framework    │
│ ┌──────────────────────────────┐   │
│ │ Claude Client                │   │
│ │ ├─ Intent Parser             │   │
│ │ ├─ Reasoning Engine          │   │
│ │ └─ Spec Generator            │   │
│ ├─ Tool Declarations (TOOLS.md)│   │
│ ├─ Skill Declarations (SKILLS) │   │
│ ├─ Health Monitor (HEARTBEAT)  │   │
│ └─ Agent Routing (AGENTS.md)   │   │
│ └──────────────────────────────┘   │
└────────────┬──────────────────────┘
             │ /experiments
             │ /results
             │ /ctps/validate
      ┌──────┼──────┬──────────┐
      ▼      ▼      ▼          ▼
  ┌──────┐┌──────┐┌──────┐ ┌──────────┐
  │Exp   ││CTP   ││Telemetry│ │Analysis  │
  │API   ││Svc   ││Svc   │ │Tools     │
  │:8000 ││:8001 ││:8004 │ │(Future)  │
  └──────┘└──────┘└──────┘ └──────────┘
```

### Key Difference: Specification vs. Execution

The critical insight is that Claude reasonably handles **specification**: translating natural language intent into structured experiment specs. This mirrors how a researcher writes a hypothesis and experimental plan before running it. Claude identifies bottleneck regimes to explore, determines relevant parameter sweeps, and generates the JSON specifications. The downstream Experiment API (D2/D4) and Telemetry Service (D3) handle **execution and persistence**.

## API Specification

### 1. Submit Research Intent

**Endpoint**: `POST /intent`

Submit a natural language research intent. Claude reasons through the intent, generates an experimental design, and returns an orchestration_id for tracking.

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
    "run_immediately": true,
    "desired_cc_algorithms": ["cubic", "bbr"]
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
  "estimated_duration_minutes": 10,
  "estimated_completion": "2026-03-04T11:30:00Z",
  "claude_model": "claude-opus-4-6"
}
```

**Processing Steps**:
1. Claude parses intent with language understanding
2. Claude identifies applications, capacity values, latency values, transport preferences
3. Claude reasons about parameter sweep (Cartesian product or custom selection)
4. Claude generates experiment specifications as JSON
5. Orchestration Service validates specs against CTP Service
6. Specs queued for execution; return orchestration_id for status tracking
7. Experiments dispatched asynchronously to Experiment API

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
      "service": "Telemetry Service :8004",
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
    "telemetry_service": "reachable",
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

## Parameter Knowledge Files

A key architectural element of the Orchestration Service is the **parameter knowledge files** — a set of domain knowledge documents (markdown) that ground Claude's reasoning about experiment parameters. These files define:

- **Acceptable ranges** for every parameter: capacity (0.1–10000 Mbps), latency (0–10000 ms), buffer sizes, etc.
- **Default values** and their rationale: why fq_codel is the default AQM, why 60 seconds is the default duration
- **Application-specific defaults**: YouTube workflows default to 60s, Zoom defaults to 120s, speed tests to 30s
- **CTP cluster taxonomy**: descriptions of available CTP clusters, their characteristics (burstiness, intensity, temporal correlation), and when to use each
- **Constraint relationships**: e.g., "if capacity < 5 Mbps and application = zoom, warn that video quality will degrade"
- **Common experimental designs**: standard parameter sweeps, baseline configurations, comparison patterns

These files live in `knowledge/` within the orchestration service directory and are loaded into Claude's context (via system prompt or tool context) when processing intents. They prevent Claude from generating physically impossible or experimentally meaningless configurations, and they ensure that underspecified intents get reasonable defaults.

```
services/orchestration/
├── knowledge/
│   ├── parameter_ranges.md      # Valid ranges for all experiment parameters
│   ├── application_defaults.md  # Per-application default configurations
│   ├── ctp_clusters.md          # CTP cluster taxonomy and descriptions
│   ├── experimental_designs.md  # Common experiment patterns and templates
│   └── constraints.md           # Cross-parameter constraints and warnings
```

## Configuration Files & Deliverables

### TOOLS.md — Available Tools for Claude

Declares all primitive operations available to Claude (via OpenClaw). Each tool wraps a service endpoint.

```markdown
# Available Tools for Network Research Orchestration

## run_experiment(experiment_id, capacity_mbps, latency_ms, application, duration_seconds, cc_algorithm?)
Create and run an experiment with specific network conditions.
- experiment_id (str): Unique ID
- capacity_mbps (float): Link capacity in Mbps
- latency_ms (float): RTT latency in milliseconds
- application (str): "youtube", "netflix", "zoom", "twitch", "discord", "google-meet"
- duration_seconds (int): Experiment duration in seconds
- cc_algorithm (str, optional): "cubic", "bbr", "reno", "htcp", default "cubic"
Returns: {experiment_id, status, estimated_completion}

## query_results(application?, capacity_min?, capacity_max?, latency_min?, latency_max?, cc_algorithm?)
Query stored results by filters.
Returns: List of ExperimentResult objects with QoE metrics and contextual trees.

## validate_ctp(capacity_mbps, latency_ms, loss_rate, aqm_policy)
Validate that network conditions are feasible on available CTP nodes.
Returns: {valid: bool, ctp_cluster_id: str, warnings: List[str]}

## get_available_applications()
List supported applications and their workflow specs.
Returns: {applications: [name, workflow_spec, supported_metrics]}

## get_available_cc_algorithms()
List supported congestion control algorithms.
Returns: ["cubic", "bbr", "reno", "htcp", "vegas", "bic"]

## list_experiments(status?, limit?)
Get experiments and their status. Useful for checking progress before new experiments.
Returns: List[{experiment_id, status, progress, created_at}]
```

### SKILLS.md — High-Level Multi-Step Workflows

Declares composite skills that Claude can use to orchestrate multi-step experiment plans.

```markdown
# Available Skills for Multi-Step Workflows

## parameter_sweep
Run experiments across ranges of parameters (Cartesian product).
Input:
  - applications: ["youtube", "zoom"]
  - capacity_range: {min: 10, max: 50, step: 5}
  - latency_range: {min: 20, max: 100, step: 20}
  - cc_algorithms: ["cubic", "bbr"] (optional)
Behavior: Generates (2 apps) × (9 capacities) × (5 latencies) [× 2 CCs] experiments

## application_comparison
Compare multiple applications under identical network conditions.
Input:
  - applications: ["youtube", "zoom", "discord"]
  - capacity_mbps: 25
  - latency_ms: 50
  - cc_algorithm: "cubic" (optional)
Behavior: Creates one experiment per application, same network config

## baseline_establishment
Test applications with minimal constraints (ideal network) to establish upper bounds.
Input:
  - applications: ["youtube", "zoom"]
  - duration_seconds: 120
Behavior: Generates 2 experiments with 1000 Mbps, 5ms latency, FIFO AQM

## network_characterization
Factorial sweep of capacity and latency to characterize bottleneck regimes.
Input:
  - applications: ["youtube"]
  - capacity_values: [5, 10, 25, 50, 100]
  - latency_values: [10, 25, 50, 100]
Behavior: Generates 5 × 4 = 20 experiments covering regime space

## replicate_study
Replicate a published study or prior experiment set.
Input:
  - study_name: "name of study to replicate"
  - num_trials: number of trials per condition
Behavior: Executes pre-defined experiment matrix from study definition
```

### AGENTS.md — Agent Routing & Role Distribution

Defines how Claude routes reasoning across the Researcher/Supervisor pattern.

```markdown
# Agent Routing & Roles

## Researcher Agent (Claude LLM backbone)
Responsible for:
- Interpreting natural language intent
- Reasoning about experimental design
- Decomposing intent into testable hypotheses
- Selecting appropriate skills and tools
- Iterative refinement based on results

## Supervisor Layer (Skills in SKILLS.md)
Responsible for:
- Executing multi-step experiment workflows
- Managing parameter sweeps and combinations
- Enforcing constraints and validations
- Tracking experiment progress
- Collecting and reporting results

## Routing Logic
- Simple intent (one application, fixed capacity) → route to run_experiment tool directly
- Parameter sweep intent → route to parameter_sweep skill
- Comparison intent → route to application_comparison skill
- Open-ended intent ("characterize YouTube") → route to network_characterization skill
```

### HEARTBEAT.md — Health Monitoring & Execution Tracking

Defines health checks and orchestration monitoring.

```markdown
# Orchestration Health Monitoring

## /health endpoint
Returns: {status, claude_api_healthy, experiment_api_reachable, telemetry_service_reachable, ctp_service_reachable, active_orchestrations_count, uptime_seconds}

## Experiment Tracking
Track status of dispatched experiments: pending → running → complete/failed
Monitor for: timeouts, failures, resource exhaustion

## Claude API Health
Monitor: API connectivity, rate limits, token usage, latency
Alert on: API errors, quota issues, degraded performance

## Orchestration Lifecycle
1. Intent submitted (202 Accepted)
2. Claude parses and generates specs (status: processing)
3. Specs validated against CTP Service (status: validating)
4. Experiments queued and dispatched (status: executing)
5. Results collected from Telemetry Service (status: complete)
```

## Service Dependencies

| Service | Endpoint | Purpose |
|---------|----------|---------|
| Experiment API | POST /experiments, GET /experiments/{id} | Create and monitor experiments |
| Telemetry Service | GET /results, POST /results | Query and store results |
| CTP Service | POST /ctps/validate | Validate network configurations |
| Claude API (Anthropic) | https://api.anthropic.com | LLM reasoning backbone |

## Testing Criteria

> **Unit tests for this service live in `services/orchestration/tests/`.** Run them with `pytest services/orchestration/tests/ -v`.

### Unit Tests
- Claude intent parsing for various phrasings and contexts
- Parameter sweep generation (Cartesian product logic)
- Experiment ID generation and naming consistency
- Reasoning step serialization and logging
- Tool declaration parsing and validation
- Skill routing logic (intent → appropriate skill/tool)

### Integration Tests
- "Compare YouTube vs Zoom at 10, 25, 50 Mbps" → generates exactly 6 valid experiment specs
- "Parameter sweep: 10-50 Mbps in 10 Mbps steps, YouTube" → generates 5 experiments
- "Characterize YouTube under CUBIC and BBR" → generates 2 × N experiments (2 CCs)
- Generated experiments pass CTP Service validation
- Multi-step intents generate correct experiment matrix size
- Orchestration tracking follows all generated experiments from pending → complete
- Queries against Telemetry Service retrieve results correctly
- Claude reasoning steps logged and retrievable

### Performance Tests
- Claude intent parsing and spec generation < 3s for simple intent
- Parameter sweep generation < 1s per 20 experiments
- Full orchestration of 10 experiments dispatched < 1 minute (wall-clock)
- Orchestration status query < 500ms
- Health check < 200ms

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

## System Prompt & Reasoning Template

The Claude system prompt guides the reasoning behavior:

```
You are Claude, the Researcher agent in the Agentic Thin Waist network research system.
Your role is to interpret natural language research intents and generate concrete,
executable experiment specifications.

CONTEXT:
- Available applications: youtube, netflix, zoom, twitch, discord, google-meet, twitch
- Capacity range: 0.1 to 10000 Mbps
- Latency range: 0 to 10000 ms
- Supported congestion control: cubic, bbr, reno, htcp, vegas, bic
- Supported AQM policies: fifo, codel, pie, fq_codel
- Available skills: parameter_sweep, application_comparison, baseline_establishment,
  network_characterization, replicate_study

CORE LOOP:
1. Parse intent: What does the researcher want to test?
2. Identify bottleneck regimes: What network conditions are interesting?
3. Reason about parameter sweep: Cartesian product or custom exploration?
4. Generate specs: Create JSON experiment definitions
5. Select skill/tool: parameter_sweep? run_experiment? baseline_establishment?
6. Return orchestration_id for tracking

EXTRACTION TASK:
Given a research intent, extract:
1. Applications to test
2. Capacity values (Mbps) or ranges
3. Latency values (ms) or ranges
4. Congestion control algorithms (optional)
5. AQM policies (optional)
6. Duration (seconds)
7. Number of trials
8. Reasoning: Why these choices?

OUTPUT FORMAT:
Return a JSON object with extracted parameters, then explain your reasoning.

EXAMPLES:
Intent: "Compare YouTube vs Zoom at 10, 25, 50 Mbps with 50ms latency"
→ applications: ["youtube", "zoom"], capacities: [10, 25, 50], latencies: [50], trials: 1
→ Reasoning: Cartesian product → 2 × 3 = 6 experiments
→ Skill: application_comparison (3 capacities, 2 apps)

Intent: "Characterize YouTube under CUBIC and BBR across 5-100 Mbps"
→ applications: ["youtube"], capacity_range: {min: 5, max: 100, step: 10},
  cc_algorithms: ["cubic", "bbr"]
→ Reasoning: Factorial design exploring bottleneck regimes
→ Skill: parameter_sweep
```

The prompt emphasizes reasoning about **why** experiments matter (bottleneck regimes, QoE transitions) not just mechanically generating combinations.

## Implementation Notes

### Critical Timeline
- **Haarika has NSDI camera-ready deadline this week** — D5 ramps up heavily after that milestone
- Design review and validation needed before Haarika fully focuses on implementation
- Coordinate with Prof. Gupta on prompt engineering and Claude integration patterns

### Key Implementation Decisions

1. **Claude as Specification Engine**: Claude generates experiment JSON specs; it does not execute them directly. This separation preserves safety and auditability.

2. **OpenClaw Integration**: Use OpenClaw's tool/skill system to expose TOOLS.md and SKILLS.md to Claude. The framework handles routing and execution tracking.

3. **Async Experiment Dispatch**: Experiments are queued asynchronously. The POST /intent endpoint returns immediately (202) with an orchestration_id. Status polling via GET /orchestration/{orchestration_id}.

4. **CTP Validation**: Before dispatching, validate all generated experiments against the CTP Service (POST /ctps/validate). Reject specs that violate constraints.

5. **Result Aggregation**: Once experiments complete, aggregate results from Telemetry Service (D3) and present to user via GET /orchestration/{orchestration_id}/results.

### Testing Strategy

- **Unit tests** on Claude prompt behavior (various intent phrasings)
- **Integration tests** with mock Experiment API and Telemetry Service
- **E2E tests** with actual network testbed (coordinated with D2/D4 schedule)
- **Prompt ablation** to measure impact of reasoning guidance

## References

- Anthropic Claude API: https://docs.anthropic.com/claude/reference/
- Glia Paper: Glia: Synergizing LLM and Internet Agents (MIT)
- OpenClaw Framework: [Internal SNL-UCSB documentation]
- Prompt Engineering Best Practices: https://docs.anthropic.com/claude/docs/prompt-engineering
- Python Async Patterns: https://docs.python.org/3/library/asyncio.html

---

**Last Updated**: 2026-03-07
**Status**: Specification Ready (High Priority)
**Next Milestone**: Implementation (Weeks 3–4, after Haarika's NSDI deadline)
**Contact**: Haarika (Lead), Prof. Arpit Gupta (PI)
