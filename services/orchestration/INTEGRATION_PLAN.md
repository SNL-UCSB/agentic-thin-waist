# Orchestration Service: Step-by-Step Integration Plan

This document breaks the Orchestration Service (D5) into 12 incremental steps. Each step produces a working, testable result. Steps build on each other — do them in order.

**Owner**: Haarika
**Port**: 8005
**Estimated total**: ~2 weeks of focused work after NSDI camera-ready

---

## Step 1: Project Structure and Dependencies

**Goal**: Get a runnable FastAPI app that does nothing but respond to health checks.

**What to do**:
1. Create the directory structure:
   ```
   services/orchestration/
   ├── app/
   │   ├── __init__.py
   │   ├── main.py              # FastAPI entry point
   │   ├── api/
   │   │   ├── __init__.py
   │   │   └── intent.py        # Endpoint handlers (stub)
   │   ├── engine/
   │   │   ├── __init__.py
   │   │   ├── claude_client.py  # Anthropic SDK wrapper (stub)
   │   │   ├── intent_parser.py  # Intent → structured form (stub)
   │   │   ├── experiment_generator.py  # Structured → JSON specs (stub)
   │   │   └── executor.py      # Dispatch to Experiment API (stub)
   │   ├── models/
   │   │   ├── __init__.py
   │   │   └── schemas.py       # Pydantic models
   │   ├── prompts/
   │   │   ├── system.md         # System prompt (empty)
   │   │   └── examples.md       # Few-shot examples (empty)
   │   └── knowledge/
   │       ├── parameter_ranges.md
   │       ├── application_defaults.md
   │       ├── ctp_clusters.md
   │       ├── experimental_designs.md
   │       └── constraints.md
   ├── TOOLS.md
   ├── SKILLS.md
   ├── AGENTS.md
   ├── HEARTBEAT.md
   ├── Dockerfile
   ├── requirements.txt
   └── tests/
       ├── __init__.py
       └── test_health.py
   ```

2. Update `requirements.txt`:
   ```
   fastapi>=0.100.0
   uvicorn>=0.23.0
   anthropic>=0.39.0
   httpx>=0.25.0
   pydantic>=2.0.0
   pytest>=7.0.0
   pytest-cov
   pytest-mock
   pytest-asyncio
   ```

3. Create `app/main.py`:
   ```python
   from fastapi import FastAPI

   app = FastAPI(title="Orchestration Service", version="0.1.0")

   @app.get("/health")
   def health():
       return {"status": "healthy", "checks": {}}
   ```

4. Update `Dockerfile`:
   ```dockerfile
   FROM python:3.10-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
   ```

5. Write `tests/test_health.py`:
   ```python
   from fastapi.testclient import TestClient
   from app.main import app

   client = TestClient(app)

   def test_health_returns_200():
       resp = client.get("/health")
       assert resp.status_code == 200
       assert resp.json()["status"] == "healthy"
   ```

**Test**: `pytest tests/test_health.py -v` passes. `uvicorn app.main:app --port 8005` starts.

**Estimated time**: 1-2 hours

---

## Step 2: Pydantic Data Models

**Goal**: Define all the data contracts so the rest of the code has types to work with.

**What to do** — create `app/models/schemas.py`:

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum

class OrchestrationStatus(str, Enum):
    pending = "pending"
    parsing = "parsing"
    generating = "generating"
    validating = "validating"
    executing = "executing"
    complete = "complete"
    failed = "failed"

class ResearchIntent(BaseModel):
    intent: str = Field(..., description="Natural language research goal")
    context: Dict[str, Any] = Field(default_factory=dict)
    preferences: Dict[str, Any] = Field(default_factory=dict)

class GeneratedExperiment(BaseModel):
    experiment_id: str
    capacity_mbps: float
    latency_ms: float
    loss_rate: float = 0.0
    application: str
    duration_seconds: int = 60
    num_trials: int = 1
    cc_algorithm: str = "cubic"
    aqm_policy: str = "fq_codel"
    reasoning: str = ""

class OrchestrationResponse(BaseModel):
    orchestration_id: str
    status: OrchestrationStatus
    intent: str
    generated_experiments: int
    estimated_duration_minutes: Optional[float] = None
    claude_model: str = "claude-sonnet-4-6"

class ReasoningStep(BaseModel):
    step: int
    action: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    reasoning: str

class OrchestrationProgress(BaseModel):
    orchestration_id: str
    status: OrchestrationStatus
    progress: Dict[str, Any]
    generated_experiments: List[Dict[str, Any]]

class OrchestrationResult(BaseModel):
    orchestration_id: str
    intent: str
    status: OrchestrationStatus
    experiment_results: List[Dict[str, Any]]
    summary: Dict[str, Any]
```

**Test**: Write `tests/test_models.py` — construct each model with sample data, verify validation works, verify invalid data is rejected.

**Estimated time**: 1-2 hours

---

## Step 3: Claude API Connection

**Goal**: Send a message to Claude and get a response back. Nothing domain-specific yet.

**What to do** — create `app/engine/claude_client.py`:

```python
import os
from anthropic import Anthropic

class ClaudeClient:
    def __init__(self, api_key: str = None, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = Anthropic(api_key=self.api_key)
        self.model = model

    def send(self, user_message: str, system_prompt: str = "") -> str:
        """Send a single message to Claude and return the text response."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )
        return response.content[0].text
```

**Key decisions**:
- Default to `claude-sonnet-4-6` for development (faster, cheaper). Switch to `claude-sonnet-4-6` for production.
- API key from environment variable, never hardcoded.
- Start simple — no tool use, no streaming, no conversation history. Those come later.

**Test**: Write `tests/test_claude_client.py`:
- Mock the Anthropic SDK to avoid real API calls in CI
- Test that `ClaudeClient` raises `ValueError` when no API key is set
- Test that `send()` returns a string
- Manual test (not in CI): `python -c "from app.engine.claude_client import ClaudeClient; print(ClaudeClient().send('What is a network bottleneck?'))"`

**Estimated time**: 1-2 hours

---

## Step 4: System Prompt — Teaching Claude About the Thin Waist

**Goal**: Write the system prompt that makes Claude understand bottleneck regimes, experiment specs, and the thin waist architecture.

**What to do** — create `app/prompts/system.md`:

The system prompt should include:
1. **Role definition**: "You are a network experiment designer for the Agentic Thin Waist platform..."
2. **Domain concepts**: bottleneck regimes, static vs dynamic attributes, CTPs, iterations vs experiments
3. **Available parameters and valid ranges** (loaded from knowledge files):
   - Applications: youtube, netflix, zoom, twitch, discord, google-meet, ndt, ping, iperf3
   - Capacity: 0.1–10000 Mbps
   - Latency: 0–10000 ms
   - CC algorithms: cubic, bbr, reno, htcp, vegas, bic
   - AQM policies: fifo, codel, pie, fq_codel
4. **Output format**: JSON with specific schema matching `GeneratedExperiment`
5. **Behavioral rules**:
   - Never silently assume unspecified parameters — ask for clarification
   - Always explain reasoning
   - Generate physically meaningful configurations only

Then write a loader in `app/engine/claude_client.py`:
```python
def _load_system_prompt(self) -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "system.md"
    knowledge_dir = Path(__file__).parent.parent / "knowledge"

    prompt = prompt_path.read_text()
    for knowledge_file in sorted(knowledge_dir.glob("*.md")):
        prompt += f"\n\n# {knowledge_file.stem}\n\n"
        prompt += knowledge_file.read_text()
    return prompt
```

**Test**: Send 3 sample intents with the system prompt and manually verify Claude's responses make sense:
- "Run a YouTube test at 10 Mbps" → should extract app=youtube, capacity=10
- "Compare CUBIC vs BBR" → should ask what application and what capacity range
- "What happens to Zoom at 500ms latency?" → should note this is very high latency

**Estimated time**: 3-4 hours (prompt iteration is the bottleneck)

---

## Step 5: Intent Parser — Structured Extraction from Natural Language

**Goal**: Given a natural language intent, produce a structured dict of extracted parameters.

**What to do** — create `app/engine/intent_parser.py`:

```python
import json
from app.engine.claude_client import ClaudeClient

class IntentParser:
    def __init__(self, claude_client: ClaudeClient):
        self.claude = claude_client

    def parse(self, intent: str) -> dict:
        """Use Claude to extract structured parameters from NL intent."""
        extraction_prompt = f"""
        Extract experiment parameters from this research intent.
        Return ONLY a JSON object with these fields:
        - applications: list of application names
        - capacities: list of capacity values in Mbps (or null if not specified)
        - latencies: list of latency values in ms (or null if not specified)
        - cc_algorithms: list of CC algorithms (or null if not specified)
        - aqm_policy: string (or null if not specified)
        - duration_seconds: integer (or null if not specified)
        - num_trials: integer (default 1)
        - clarification_needed: list of strings describing what needs clarification
        - design_type: "isolated" | "concurrent" | "full" | "needs_clarification"
        - reasoning: string explaining your interpretation

        Intent: {intent}
        """
        response = self.claude.send(extraction_prompt)

        # Extract JSON from Claude's response
        # (Claude may wrap it in markdown code blocks)
        json_str = self._extract_json(response)
        return json.loads(json_str)

    def _extract_json(self, text: str) -> str:
        """Extract JSON from Claude's response, handling code blocks."""
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return text[start:end].strip()
        if "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return text[start:end].strip()
        return text.strip()
```

**Test**: Write `tests/test_intent_parser.py`:
- Mock ClaudeClient to return predetermined JSON for known intents
- Test extraction of apps, capacities, latencies from simple intents
- Test that ambiguous intents produce `clarification_needed` entries
- Test `_extract_json` with code-block and plain-text responses

**Estimated time**: 2-3 hours

---

## Step 6: Few-Shot Examples

**Goal**: Improve Claude's output quality with worked examples of intent → experiment mapping.

**What to do** — create `app/prompts/examples.md`:

Include 6-8 examples covering these patterns:

| Pattern | Example Intent | Expected Output |
|---------|---------------|-----------------|
| Simple single-app | "Run YouTube at 10 Mbps" | 1 experiment, no clarification |
| Parameter sweep | "Test YouTube at 10, 25, 50 Mbps" | 3 experiments |
| Multi-app comparison | "Compare YouTube vs Zoom at 25 Mbps" | 2 experiments (isolated) or 1 (concurrent) — needs clarification |
| CC algorithm comparison | "Compare CUBIC vs BBR for YouTube at 10 Mbps" | 2 experiments |
| Ambiguous intent | "How does Netflix perform?" | clarification_needed: capacity, latency |
| Full Cartesian | "YouTube and Zoom at 10, 25, 50 Mbps" | 6 isolated + 3 concurrent = 9 (full design) |
| CTP-aware intent | "YouTube at 10 Mbps with high-burstiness cross-traffic" | N experiments (one per matching CTP cluster) |
| Explicit parameters | "YouTube, 10 Mbps, 50ms, CUBIC, fq_codel, 60s, 3 trials" | 1 experiment, 3 trials, no clarification |

Each example should show:
```
INTENT: "..."
EXTRACTED:
{json}
REASONING: "..."
```

Integrate into system prompt or pass as conversation history before the user's intent.

**Test**: Compare Claude's output quality with and without few-shot examples for 5 test intents. Output should be more consistent and require fewer clarifications.

**Estimated time**: 2-3 hours

---

## Step 7: Experiment Spec Generator

**Goal**: Turn the parsed intent (structured dict) into a list of `GeneratedExperiment` objects.

**What to do** — create `app/engine/experiment_generator.py`:

```python
from itertools import product
from typing import List
from app.models.schemas import GeneratedExperiment

class ExperimentGenerator:
    def generate(self, parsed_intent: dict) -> List[GeneratedExperiment]:
        """Generate experiment specs from parsed intent parameters."""
        apps = parsed_intent.get("applications", [])
        capacities = parsed_intent.get("capacities", [25])  # default
        latencies = parsed_intent.get("latencies", [50])     # default
        cc_algorithms = parsed_intent.get("cc_algorithms", ["cubic"])
        aqm_policy = parsed_intent.get("aqm_policy", "fq_codel")
        duration = parsed_intent.get("duration_seconds", 60)
        num_trials = parsed_intent.get("num_trials", 1)
        reasoning = parsed_intent.get("reasoning", "")

        experiments = []
        counter = 1
        for app, cap, lat, cc in product(apps, capacities, latencies, cc_algorithms):
            exp = GeneratedExperiment(
                experiment_id=f"{app}-{cap}mbps-{lat}ms-{cc}-{counter:03d}",
                capacity_mbps=cap,
                latency_ms=lat,
                application=app,
                cc_algorithm=cc,
                aqm_policy=aqm_policy,
                duration_seconds=duration,
                num_trials=num_trials,
                reasoning=reasoning,
            )
            experiments.append(exp)
            counter += 1
        return experiments
```

This is pure logic — no API calls, no side effects. Easy to test.

**Test**: Write `tests/test_experiment_generator.py`:
- "YouTube at 10, 25, 50 Mbps" → 3 experiments
- "YouTube + Zoom at 10, 25 Mbps" → 4 experiments (Cartesian)
- "YouTube, CUBIC + BBR, 10 Mbps" → 2 experiments
- Verify experiment_id naming convention
- Verify defaults are applied for unspecified parameters

**Estimated time**: 1-2 hours

---

## Step 8: FastAPI Endpoints — POST /intent and Status Tracking

**Goal**: Wire up the FastAPI endpoints so the full flow works end-to-end (with mocked downstream services).

**What to do** — create `app/api/intent.py`:

```python
import uuid
from fastapi import APIRouter, BackgroundTasks
from app.models.schemas import (
    ResearchIntent, OrchestrationResponse, OrchestrationProgress,
    OrchestrationResult, OrchestrationStatus
)
from app.engine.intent_parser import IntentParser
from app.engine.experiment_generator import ExperimentGenerator
from app.engine.claude_client import ClaudeClient

router = APIRouter()

# In-memory store for orchestration requests (replace with DB later)
ORCHESTRATIONS: dict = {}

@router.post("/intent", response_model=OrchestrationResponse, status_code=202)
async def submit_intent(request: ResearchIntent, background_tasks: BackgroundTasks):
    orch_id = f"orch-{uuid.uuid4().hex[:8]}"
    ORCHESTRATIONS[orch_id] = {
        "orchestration_id": orch_id,
        "intent": request.intent,
        "status": OrchestrationStatus.pending,
        "experiments": [],
        "reasoning_steps": [],
        "results": [],
    }

    background_tasks.add_task(process_intent, orch_id, request)

    return OrchestrationResponse(
        orchestration_id=orch_id,
        status=OrchestrationStatus.pending,
        intent=request.intent,
        generated_experiments=0,
    )

async def process_intent(orch_id: str, request: ResearchIntent):
    """Background task: parse → generate → validate → dispatch."""
    orch = ORCHESTRATIONS[orch_id]
    try:
        # Step 1: Parse
        orch["status"] = OrchestrationStatus.parsing
        claude = ClaudeClient()
        parser = IntentParser(claude)
        parsed = parser.parse(request.intent)

        # Step 2: Generate
        orch["status"] = OrchestrationStatus.generating
        generator = ExperimentGenerator()
        experiments = generator.generate(parsed)
        orch["experiments"] = [e.model_dump() for e in experiments]

        # Step 3: Validate (against CTP Service — stub for now)
        orch["status"] = OrchestrationStatus.validating

        # Step 4: Dispatch (to Experiment API — stub for now)
        orch["status"] = OrchestrationStatus.executing

        # Mark complete
        orch["status"] = OrchestrationStatus.complete

    except Exception as e:
        orch["status"] = OrchestrationStatus.failed
        orch["error"] = str(e)

@router.get("/orchestration/{orch_id}", response_model=OrchestrationProgress)
async def get_status(orch_id: str):
    ...

@router.get("/orchestration/{orch_id}/results")
async def get_results(orch_id: str):
    ...

@router.get("/orchestration/{orch_id}/reasoning")
async def get_reasoning(orch_id: str):
    ...
```

Register the router in `app/main.py`:
```python
from app.api.intent import router
app.include_router(router)
```

**Test**: Write `tests/test_intent_api.py`:
- `POST /intent` returns 202 with an orchestration_id
- `GET /orchestration/{id}` returns status
- `GET /orchestration/{id}/results` returns results after completion
- Use mocked ClaudeClient to avoid real API calls

**Estimated time**: 3-4 hours

---

## Step 9: OpenClaw Tool Declarations (TOOLS.md)

**Goal**: Declare all downstream service endpoints as tools that Claude can invoke.

**What to do**:

1. Create `TOOLS.md` with tool declarations (content already defined in the README spec — copy and adapt the 6 tools: `run_experiment`, `query_results`, `validate_ctp`, `get_available_applications`, `get_available_cc_algorithms`, `list_experiments`).

2. Create a tool loader in `app/engine/tools.py`:
   ```python
   def load_tools() -> list[dict]:
       """Load tool declarations from TOOLS.md and return as Claude tool_use format."""
       # Parse TOOLS.md into Anthropic's tool schema format:
       # [{"name": "run_experiment", "description": "...", "input_schema": {...}}, ...]
   ```

3. Update `ClaudeClient.send()` to pass tools:
   ```python
   def send_with_tools(self, user_message: str, system_prompt: str, tools: list) -> dict:
       response = self.client.messages.create(
           model=self.model,
           max_tokens=2048,
           system=system_prompt,
           tools=tools,
           messages=[{"role": "user", "content": user_message}]
       )
       # Handle tool_use responses — Claude may request a tool call
       # Return both text content and any tool_use blocks
   ```

4. Implement the tool execution loop:
   ```python
   def handle_tool_call(self, tool_name: str, tool_input: dict) -> dict:
       """Route a tool call to the appropriate downstream service."""
       if tool_name == "run_experiment":
           return self.experiment_api_client.create(tool_input)
       elif tool_name == "validate_ctp":
           return self.ctp_client.validate(tool_input)
       elif tool_name == "get_available_applications":
           return self.netgent_client.list_available()
       ...
   ```

**Key concept**: Claude decides WHICH tools to call based on the intent. The orchestration service EXECUTES those tool calls against real service endpoints. This is the core of the agentic loop.

**Test**:
- Verify TOOLS.md parses into valid Anthropic tool schema
- Mock downstream services and verify tool routing works
- Test that Claude selects appropriate tools for simple intents

**Estimated time**: 4-5 hours

---

## Step 10: OpenClaw Skill Definitions (SKILLS.md)

**Goal**: Declare multi-step workflows that compose multiple tool calls.

**What to do**:

1. Create `SKILLS.md` (content already defined in the README spec — 5 skills: `parameter_sweep`, `application_comparison`, `baseline_establishment`, `network_characterization`, `replicate_study`).

2. Create a skill executor in `app/engine/skills.py`:
   ```python
   class SkillExecutor:
       def execute_parameter_sweep(self, params: dict) -> list[GeneratedExperiment]:
           """Cartesian product of apps × capacities × latencies × CCs."""
           ...

       def execute_application_comparison(self, params: dict) -> list[GeneratedExperiment]:
           """Same network config, multiple apps."""
           ...

       def execute_baseline(self, params: dict) -> list[GeneratedExperiment]:
           """High capacity, low latency — establish upper bounds."""
           ...
   ```

3. Wire skills into the intent processing pipeline:
   - Claude parses intent → selects a skill (or direct tool call)
   - Skill executor generates the experiment list
   - Experiments are dispatched to the Experiment API

4. Expose via `GET /tools` and `GET /skills` endpoints.

**Test**:
- `parameter_sweep` with 2 apps × 3 capacities × 2 CCs = 12 experiments
- `application_comparison` with 3 apps at fixed config = 3 experiments
- `baseline_establishment` with 2 apps = 2 experiments at 1000 Mbps / 5ms
- Verify skill routing: "Compare YouTube vs Zoom" → `application_comparison`

**Estimated time**: 3-4 hours

---

## Step 11: Parameter Knowledge Files

**Goal**: Ground Claude's reasoning with domain knowledge so it doesn't generate impossible configurations.

**What to do** — populate the `knowledge/` directory:

### `knowledge/parameter_ranges.md`
```markdown
# Parameter Ranges

| Parameter | Min | Max | Default | Unit |
|-----------|-----|-----|---------|------|
| capacity_mbps | 0.1 | 10000 | 25 | Mbps |
| latency_ms | 0 | 10000 | 50 | ms |
| loss_rate | 0 | 100 | 0 | % |
| duration_seconds | 10 | 3600 | 60 | seconds |
| num_trials | 1 | 100 | 1 | count |
| buffer_packets | 1 | 100000 | 1000 | packets |

## Congestion Control Algorithms
cubic (default), bbr, reno, htcp, vegas, bic

## AQM Policies
fifo, codel, pie, fq_codel (default)
```

### `knowledge/application_defaults.md`
```markdown
# Application Defaults

| Application | Default Duration | Type | Key QoE Metrics |
|-------------|-----------------|------|-----------------|
| youtube | 60s | Browser (NFA) | startup_time, rebuffer_events, bitrate |
| netflix | 60s | Browser (NFA) | startup_time, rebuffer_events, bitrate |
| zoom | 120s | Browser (NFA) | video_quality, audio_quality, packet_loss |
| ndt | 30s | Shell | download_mbps, upload_mbps, latency_ms |
| ping | 30s | Shell | rtt_min, rtt_avg, rtt_max, packet_loss |
| iperf3 | 30s | Shell | throughput_mbps, jitter_ms, packet_loss |
```

### `knowledge/ctp_clusters.md`
Document available CTP clusters with their characteristics — burstiness level, intensity, temporal correlation. This will be populated with real data from the CTP Service once it's running.

### `knowledge/constraints.md`
```markdown
# Cross-Parameter Constraints

- If capacity < 1 Mbps and application = zoom: WARN — Zoom requires ~1.5 Mbps minimum
- If capacity < 5 Mbps and application = netflix: WARN — Netflix minimum for SD is ~3 Mbps
- If latency > 300ms and application = zoom: WARN — real-time communication degrades severely
- If duration < 30s and application in [youtube, netflix]: WARN — may not reach steady state
- If num_trials > 10 and capacities > 5: WARN — this will generate >50 experiments
```

### `knowledge/experimental_designs.md`
Document common patterns (capacity sweeps, latency sweeps, CC comparisons, baseline establishment).

**Test**: Load all knowledge files into the system prompt. Verify:
- Claude rejects "YouTube at 0 Mbps" (out of range)
- Claude warns about "Zoom at 500ms latency" (constraint violation)
- Claude uses correct default duration per application

**Estimated time**: 3-4 hours

---

## Step 12: Experiment Dispatch and Result Aggregation

**Goal**: Wire the orchestration service to actually call the Experiment API and Telemetry Service.

**What to do**:

1. Create HTTP clients in `app/engine/executor.py`:
   ```python
   import httpx

   class ExperimentAPIClient:
       def __init__(self, base_url: str = "http://localhost:8000"):
           self.base_url = base_url
           self.client = httpx.AsyncClient(timeout=30.0)

       async def create_experiment(self, spec: dict) -> dict:
           resp = await self.client.post(f"{self.base_url}/experiments", json=spec)
           resp.raise_for_status()
           return resp.json()

       async def get_status(self, experiment_id: str) -> dict:
           resp = await self.client.get(f"{self.base_url}/experiments/{experiment_id}")
           return resp.json()

   class TelemetryClient:
       def __init__(self, base_url: str = "http://localhost:8004"):
           self.base_url = base_url
           self.client = httpx.AsyncClient(timeout=30.0)

       async def get_results(self, experiment_id: str) -> dict:
           resp = await self.client.get(
               f"{self.base_url}/results",
               params={"experiment_id": experiment_id}
           )
           return resp.json()

   class CTPClient:
       def __init__(self, base_url: str = "http://localhost:8001"):
           ...

       async def validate(self, spec: dict) -> dict:
           resp = await self.client.post(f"{self.base_url}/ctps/validate", json=spec)
           return resp.json()
   ```

2. Update `process_intent()` to use real clients:
   - Validate each experiment spec against CTP Service
   - Dispatch validated specs to Experiment API
   - Poll for completion
   - Fetch results from Telemetry Service
   - Aggregate into `OrchestrationResult`

3. Add retry logic and error handling:
   - Timeout after configurable duration (default 10 minutes per experiment)
   - Mark individual experiments as failed without failing the whole orchestration
   - Log all Claude reasoning steps for transparency

4. Update `GET /health` to check downstream service connectivity:
   ```python
   @app.get("/health")
   async def health():
       checks = {}
       for name, url in [("experiment_api", "http://localhost:8000/health"),
                          ("ctp_service", "http://localhost:8001/health"),
                          ("telemetry_service", "http://localhost:8004/health")]:
           try:
               resp = await httpx.AsyncClient().get(url, timeout=5.0)
               checks[name] = "reachable" if resp.status_code == 200 else "degraded"
           except Exception:
               checks[name] = "unreachable"
       return {"status": "healthy" if all(v == "reachable" for v in checks.values()) else "degraded", "checks": checks}
   ```

**Test**:
- Integration test with mocked downstream services (use `respx` or `httpx` mocking)
- Verify experiment dispatch, status polling, and result aggregation
- Verify partial failure handling (3 of 6 experiments succeed)

**Implementation note (D5 `executor.py`)**: Per-iteration tool pipeline is **CTP validate** (optional, via `validate_ctp`) → **Experiment API** `POST /experiments` (pending; Telemetry DB when wired) → **substrate** `shape` → **substrate** `capture` → telemetry query → **PATCH** experiment status. See `tests/test_executor_pipeline.py`.

**Estimated time**: 4-5 hours

---

## Summary: Step Dependencies

```
Step 1: Project structure + health check
  ↓
Step 2: Pydantic models
  ↓
Step 3: Claude API connection
  ↓
Step 4: System prompt ←── Step 11: Knowledge files (can be done in parallel)
  ↓
Step 5: Intent parser
  ↓
Step 6: Few-shot examples
  ↓
Step 7: Experiment generator
  ↓
Step 8: FastAPI endpoints (POST /intent, status tracking)
  ↓
Step 9: OpenClaw tool declarations (TOOLS.md)
  ↓
Step 10: OpenClaw skill definitions (SKILLS.md)
  ↓
Step 12: Experiment dispatch + result aggregation
```

Steps 1-3 are **foundation** (can be done in one day).
Steps 4-7 are **core logic** (intent → specs pipeline).
Steps 8-10 are **API layer** (making it a proper service).
Steps 11-12 are **integration** (connecting to real services).

## What Can Be Done Without Other Services

Steps 1-10 can all be developed **independently** against mocked downstream services. Only Step 12 requires actual running services (Experiment API, CTP Service, Telemetry). This means Haarika can make significant progress even before the other services are ready.

---

**Last Updated**: 2026-03-11
**Status**: Plan Ready
