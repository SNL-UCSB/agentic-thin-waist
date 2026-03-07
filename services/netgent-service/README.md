# NetGent Service

**Port**: 8003
**Deliverable**: D2 (Application Workflow Engine)
**Leads**: Eugene + Jaber
**PI**: Prof. Arpit Gupta
**Priority**: HIGH
**Status**: Specification Ready

## Purpose

NetGent is the application workflow execution engine. It handles **all host-level application processes** — both browser-based interactions (YouTube, Netflix, Zoom, Twitch via NFA/Selenium) and non-browser processes (ping, NDT speed tests, iperf3, shell commands). The service compiles natural-language workflow specifications into executable NFA (nondeterministic finite automaton) state machines for browser automation, and provides direct execution wrappers for shell-based tools. NetGent measures Quality of Experience (QoE) metrics during workflow execution under shaped network conditions.

NetGent also maintains the **active application registry**: the authoritative list of applications the system currently supports. The controller (Experiment API) queries this registry before dispatching any iteration. Adding support for a new application is an out-of-band process — it requires implementing the NFA workflow or shell wrapper and registering it in the registry. This is explicitly scoped out of the real-time thin waist pipeline.

## Input

NetGent accepts:
- Natural language workflow specifications: "Watch YouTube for 60 seconds, measuring startup time and rebuffer events"
- Application type: youtube, netflix, zoom, twitch, discord, google-meet, ndt-speedtest, puffer, ping, iperf3
- Timeout settings: maximum execution duration
- LLM model specification (optional): inject custom LLM for NFA compilation
- Capture preferences: HAR file, console logs, screenshots
- Shell command specifications (for non-browser workflows): command, arguments, duration, output parsing rules

## Output

NetGent produces:
- WorkflowResult: execution status, states traversed, total duration
- QoE metrics: video startup time (ms), mean bitrate (Mbps), rebuffer events, bitrate changes, resolution
- Artifacts: HAR file (network timeline), console logs, screenshots at key states
- NFA details: states traversed, transitions, state count
- Execution traces: timing of each state, any errors or warnings

## Interfaces

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/workflows/execute` | POST | Execute workflow from NL specification |
| `/workflows/compile` | POST | Compile NL spec to NFA state machine |
| `/workflows/validate` | POST | Validate spec without execution |
| `/workflows/{id}` | GET | Get workflow result and QoE metrics |
| `/workflows/available` | GET | **Active application registry** — list all supported applications and their capabilities |
| `/health` | GET | Health check: browser driver, LLM service |

### Active Application Registry (`GET /workflows/available`)

This endpoint is the **source of truth** for what applications the system supports. The controller (Experiment API) queries this before dispatching any iteration. Response includes application name, execution type (browser or shell), supported QoE metrics, and any prerequisites (credentials, URLs, etc.).

Adding a new application requires: (1) implementing the NFA workflow or shell wrapper, (2) registering it in the application registry, and (3) deploying the updated service. This is an out-of-band development process, not something that happens during experiment execution.

## YouTube MVP Example

For YouTube watch-video-60s under bottleneck:
- compile(): Claude parses spec → NFA with states: init, navigate youtube.com, search/select video, play, watch 60s, collect stats
- execute(): Selenium drives browser through states on shaped network (10/25/50 Mbps)
- During execution: capture HAR file, monitor Stats for Nerds metrics
- Success criteria: workflow completes, startup_time extracted, rebuffer_events measured, HAR file contains full timeline

### Key Innovation

The novel contribution of NetGent is **NFA compilation from natural-language specifications**. Rather than hand-coding workflows, users describe desired application interactions as NL prompts, which the service compiles into deterministic state machines executable via Selenium/Puppeteer.

### Core Abstractions

- **NFA Model**: States correspond to observable interface conditions; transitions encode permissible user interactions
- **LangGraph StateGraph**: Internal execution uses four-node state machine for compilation, validation, execution, and result collection
- **LLM Abstraction**: Uses `BaseChatModel` for swappable language models (per-call injection for OpenClaw integration)
- **Workflow Result**: Complete execution outcome including states traversed, QoE metrics, artifacts, and timing

---

## API Reference

### POST /workflows/execute

Execute a workflow from natural-language specification.

**Request**:
```json
{
  "spec": "Watch YouTube for 60 seconds, measuring startup time and rebuffer events",
  "timeout": 120,
  "application": "youtube",
  "llm_model": "gpt-4",
  "headless": true,
  "capture_artifacts": true
}
```

**Response** (202 Accepted):
```json
{
  "workflow_id": "wf-uuid-001",
  "status": "executing",
  "start_time": "2026-03-04T10:00:00Z",
  "estimated_completion": "2026-03-04T10:02:05Z"
}
```

### POST /workflows/compile

Compile NL specification to executable NFA state machine.

**Request**:
```json
{
  "spec": "Navigate to Netflix, log in, select a show, play for 30 seconds"
}
```

**Response** (200 OK):
```json
{
  "workflow_id": "wf-compiled-abc123",
  "states": [
    {"id": "init", "action": "initialize_browser"},
    {"id": "navigate", "action": "goto", "url": "https://netflix.com"},
    {"id": "login", "action": "enter_credentials", "selectors": ["email", "password"]},
    {"id": "select", "action": "click_video"},
    {"id": "play", "action": "wait", "duration": 30}
  ],
  "transitions": [
    {"from": "init", "to": "navigate"},
    {"from": "navigate", "to": "login"},
    {"from": "login", "to": "select"},
    {"from": "select", "to": "play"}
  ],
  "estimated_duration_seconds": 35,
  "validation_status": "passed"
}
```

### POST /workflows/validate

Validate workflow specification for correctness and completeness.

**Request**:
```json
{
  "spec": "Click button with selector #play-btn, then wait 60 seconds"
}
```

**Response** (200 OK):
```json
{
  "valid": true,
  "errors": [],
  "warnings": [
    "No video element selection found; ensure video loads before wait"
  ],
  "estimated_duration_seconds": 62,
  "state_count": 3
}
```

### GET /workflows/{id}

Retrieve workflow result by execution ID.

**Response** (200 OK):
```json
{
  "workflow_id": "wf-uuid-001",
  "status": "completed",
  "states_executed": ["init", "navigate", "search", "play", "watch", "close"],
  "duration": 65.2,
  "nfa": {
    "states": 6,
    "transitions": 5,
    "initial_state": "init",
    "accepting_states": ["close"]
  },
  "artifacts": {
    "har_file": "s3://artifacts/wf-uuid-001.har",
    "console_log": "s3://artifacts/wf-uuid-001.log",
    "screenshots": ["s3://artifacts/wf-uuid-001-state1.png"]
  },
  "qoe_metrics": {
    "video_startup_time_ms": 2500,
    "mean_bitrate_mbps": 8.5,
    "rebuffer_events": 1,
    "rebuffer_duration_ms": 2000,
    "bitrate_changes": 3,
    "max_bitrate_mbps": 9.5,
    "min_bitrate_mbps": 4.2
  },
  "errors": []
}
```

### GET /health

Health check endpoint.

**Response** (200 OK):
```json
{
  "status": "healthy",
  "checks": {
    "browser_driver": "available",
    "llm_service": "responsive",
    "workflow_engine": "operational",
    "telemetry_service": "connected"
  },
  "uptime_seconds": 3600
}
```

---

## Supported Applications

### Browser-Based (NFA + Selenium/CDP)

| Application | NFA Support | QoE Metrics | Notes |
|-------------|-------------|------------|-------|
| YouTube | Full | Startup, bitrate, rebuffers | Login-free |
| Netflix | Full | Startup, resolution, rebuffers | Requires credentials |
| Zoom | Full | Video quality, audio quality, packet loss | Requires URL/token |
| Twitch | Full | Startup, bitrate, chat interaction | Live & VOD support |
| Puffer | Full | Bitrate, ABR decisions, QoE | Research platform |
| Google Meet | Full | Video quality, connection state | Real-time metrics |
| Discord | Partial | Voice quality, connection state | Limited video QoE |

### Host-Level Processes (Shell Execution)

| Application | Execution Type | Metrics | Notes |
|-------------|---------------|---------|-------|
| NDT speedtest | Shell (ndt-client) | Upload, download, latency, loss | No browser needed |
| ping | Shell | RTT, packet loss, jitter | Standard ICMP ping |
| iperf3 | Shell | Throughput, jitter, packet loss | Client/server mode |

All host-level processes that generate network traffic or measure network properties belong in NetGent's scope. If a workflow involves running something on the host machine under shaped network conditions, NetGent owns it.

---

## NetGentAPI Class

Core API for programmatic workflow management.

```python
class NetGentAPI:
    def execute_workflow(
        self,
        spec: str,
        timeout: int = 120,
        llm: Optional[BaseChatModel] = None
    ) -> WorkflowResult:
        """Execute workflow from NL spec with optional LLM override."""

    def compile_nfa(self, spec: str) -> NFA:
        """Compile spec to NFA state machine."""

    def validate_workflow(self, spec: str) -> ValidationResult:
        """Validate spec without execution."""

    def health_check(self) -> HealthStatus:
        """Return service health."""

    def detect_interface_changes(self, url: str) -> List[InterfaceChange]:
        """Detect DOM changes to improve selector robustness."""
```

### LLM Injection (Per-Call)

**Feature**: Pass LLM instance per-call for OpenClaw integration.

```python
# Use default LLM
result = api.execute_workflow("Watch YouTube for 60s")

# Override with custom LLM
from langchain.chat_models import ChatOpenAI
custom_llm = ChatOpenAI(model="gpt-4-turbo")
result = api.execute_workflow("Watch YouTube for 60s", llm=custom_llm)
```

### Interface Change Detection

**Feature**: Detect DOM mutations to handle dynamic interfaces.

```python
changes = api.detect_interface_changes("https://youtube.com")
# Returns: [
#   InterfaceChange(selector="#search", change_type="added"),
#   InterfaceChange(selector=".video-player", change_type="modified")
# ]
```

---

## Data Structures

### WorkflowResult

Complete execution outcome.

```python
@dataclass
class WorkflowResult:
    workflow_id: str
    status: str  # "executing" | "completed" | "failed" | "timeout"
    states_executed: List[str]
    artifacts: Dict[str, str]  # Keys: "har_file", "console_log", "screenshots"
    duration: float
    errors: List[str]
    nfa: Optional[Dict[str, Any]] = None
    qoe_metrics: Optional[Dict[str, float]] = None
```

### NFA

Nondeterministic finite automaton structure.

```python
@dataclass
class NFA:
    states: List[State]
    transitions: List[Transition]
    initial_state: str
    accepting_states: List[str]

@dataclass
class State:
    id: str
    action: str  # "navigate", "click", "wait", "screenshot", etc.
    parameters: Dict[str, Any]

@dataclass
class Transition:
    from_state: str
    to_state: str
    condition: Optional[str] = None
```

### ValidationResult

Result of spec validation.

```python
@dataclass
class ValidationResult:
    valid: bool
    errors: List[str]
    warnings: List[str]
    state_count: int
    estimated_duration_seconds: float
```

---

## Architecture

```
┌─────────────────────────────────────────┐
│     User / Orchestrator (Port 8000)     │
└──────────────────┬──────────────────────┘
                   │ POST /workflows/execute
                   ▼
┌─────────────────────────────────────────┐
│      NetGent Service (Port 8003)        │
│  ┌───────────────────────────────────┐  │
│  │  API Layer                        │  │
│  │  - execute_workflow()             │  │
│  │  - compile_nfa()                  │  │
│  │  - validate_workflow()            │  │
│  │  - health_check()                 │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  LangGraph StateGraph (4 nodes)   │  │
│  │  1. Compile: NL → NFA             │  │
│  │  2. Validate: Check NFA           │  │
│  │  3. Execute: Run Selenium/CDP     │  │
│  │  4. Collect: Metrics + Artifacts  │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │  Execution Engine                 │  │
│  │  - Selenium/Puppeteer             │  │
│  │  - Browser pool management        │  │
│  │  - Screenshot capture             │  │
│  │  - Interface change detection     │  │
│  └───────────────────────────────────┘  │
└──────────────────┬──────────────────────┘
         ┌─────────┴──────────┬──────────────┐
         ▼                    ▼              ▼
    ┌─────────┐         ┌─────────┐   ┌──────────┐
    │ Browser │         │  LLM    │   │ Storage  │
    │ Drivers │         │ Service │   │ Service  │
    │Chrome   │         │ (OpenAI)│   │ (S3/GCS) │
    │Firefox  │         └─────────┘   └──────────┘
    └─────────┘
```

---

## Implementation Notes

### Four-Node LangGraph StateGraph

The execution pipeline uses LangGraph's StateGraph with four sequential nodes:

1. **Compile Node**: Invoke LLM to parse NL spec into NFA
2. **Validate Node**: Check NFA for completeness, cycles, and coverage
3. **Execute Node**: Run NFA states via Selenium/CDP, collect artifacts
4. **Collect Node**: Extract QoE metrics, store results, generate reports

### Per-Call LLM Injection

```python
def execute_workflow(spec: str, llm: Optional[BaseChatModel] = None):
    llm = llm or self.default_llm
    # Pass llm to Compile node
    graph.invoke({"spec": spec, "llm": llm})
```

### Browser Pool

Maintains reusable Chrome/Firefox instances to avoid overhead:
- Preallocate 5 browsers at startup
- Reuse browsers across workflows
- Clean cookies/cache between runs
- Graceful shutdown on timeout

### QoE Metric Extraction

HAR file analysis extracts:
- **Startup time**: Time from request to first video frame
- **Bitrate**: Analyze video segment sizes and duration
- **Rebuffers**: Gaps between video segment completions
- **Resolution**: Parse manifest files or CDP protocol

---

## Testing Strategy

> **Unit tests for this service live in `services/netgent-service/tests/`.** Run them with `pytest services/netgent-service/tests/ -v`.

### Unit Tests
- NFA compilation from NL specs
- State transition validation
- Selector robustness
- Timeout handling

### Integration Tests
- End-to-end YouTube workflow (60s, 70s execution)
- Netflix login + playback
- Zoom meeting join
- Multi-app concurrent execution
- Artifact storage verification

### Performance Tests
- Compilation < 1s per spec
- Execution within 10% of target duration
- QoE extraction < 5s
- Browser startup < 3s

---

## Configuration

**Environment Variables**:
```bash
NETGENT_PORT=8003
NETGENT_TIMEOUT_DEFAULT=120
LLM_API_KEY=<OpenAI API key>
LLM_MODEL=gpt-4-turbo
STORAGE_BUCKET=gs://netgent-artifacts
BROWSER_POOL_SIZE=5
```

---

## References

- BQT+ Documentation: ISP interface NFA modeling
- LangGraph: https://github.com/langchain-ai/langgraph
- Selenium WebDriver: https://www.selenium.dev/documentation/
- Chrome DevTools Protocol: https://chromedevtools.github.io/devtools-protocol/
- HAR Spec: http://www.softwareishard.com/blog/har-12-spec/

---

**Last Updated**: 2026-03-07
**Status**: Specification Ready
**Next Phase**: Integration with BQT+ orchestrator, OpenClaw LLM routing
