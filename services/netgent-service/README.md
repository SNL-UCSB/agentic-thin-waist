# NetGent Service

**Port**: 8003
**Deliverable**: D2 (Application Execution Layer)
**Priority**: HIGH
**Status**: To be implemented

## Purpose

The NetGent Service executes application-level workflows (NFA-based browser automation) to generate application-specific traffic patterns and measure quality-of-experience (QoE) metrics. It bridges network conditions (from Substrate Worker) with application-level user experiences by simulating real user behavior on websites and streaming platforms.

The NetGent Service:

1. **Compiles workflows** — Convert NFA specifications to executable browser automations
2. **Executes applications** — Run YouTube, Netflix, Zoom under controlled network conditions
3. **Measures QoE metrics** — Capture video startup time, rebuffer events, bitrate
4. **Manages browser instances** — Coordinate Selenium/Puppeteer automation
5. **Stores artifacts** — Save workflow logs, screenshots, network traces

This service integrates with existing NetGent NFA-based workflow engine developed at SNL-UCSB.

## Architecture

```
┌──────────────────────────────┐
│  Experiment API (8000)       │
│  or Orchestration (8005)     │
└────────────┬─────────────────┘
             │ POST /workflows/execute
             ▼
┌──────────────────────────────┐
│  NETGENT SERVICE (8003)      │
│  NFA-Based Browser Automation│
│  ┌────────────────────────┐  │
│  │ Workflow Compiler      │  │
│  │ Selenium/Puppeteer     │  │
│  │ QoE Metric Extractors  │  │
│  │ Artifact Collection    │  │
│  └────────────────────────┘  │
└──────────────┬────────────────┘
               │
      ┌────────┴─────────┐
      ▼                  ▼
  ┌─────────┐      ┌──────────────┐
  │ Browser │      │ Storage      │
  │Chrome   │      │ Service      │
  │Firefox  │      │ :8004        │
  └─────────┘      └──────────────┘
```

## API Specification

### 1. List Available Workflows

**Endpoint**: `GET /workflows/available`

**Response** (200 OK):
```json
{
  "workflows": [
    {
      "workflow_id": "youtube-watch-60s",
      "application": "youtube",
      "description": "Watch YouTube video for 60 seconds, measure QoE",
      "expected_duration_seconds": 65,
      "states": ["init", "navigate", "search", "play", "watch", "close"],
      "qoe_metrics": ["startup_time_ms", "bitrate_mbps", "rebuffers"]
    },
    {
      "workflow_id": "zoom-meeting-5m",
      "application": "zoom",
      "description": "Join Zoom meeting for 5 minutes",
      "expected_duration_seconds": 310,
      "states": ["init", "connect", "join", "active", "end"],
      "qoe_metrics": ["video_quality", "audio_quality", "packet_loss"]
    },
    {
      "workflow_id": "netflix-watch-30s",
      "application": "netflix",
      "description": "Watch Netflix video for 30 seconds",
      "expected_duration_seconds": 35,
      "states": ["init", "login", "select", "play", "watch"],
      "qoe_metrics": ["startup_time_ms", "resolution_p", "rebuffers"]
    }
  ],
  "total": 3
}
```

**Supported Applications**:
- youtube — Watch video (login-free)
- youtube-premium — Premium account with recommendations
- netflix — Streaming with login
- zoom — Video conferencing
- twitch — Streaming platform
- discord — Voice/video chat
- google-meet — Video conferencing
- skype — Legacy video chat
- teams — Microsoft Teams meeting

---

### 2. Execute Workflow

**Endpoint**: `POST /workflows/execute`

**Request**:
```json
{
  "workflow_id": "youtube-watch-60s",
  "experiment_id": "youtube-10mbps-001",
  "application": "youtube",
  "duration_seconds": 60,
  "timeout_seconds": 120,
  "headless": true,
  "record_har": true,
  "record_video": false,
  "network_interface": "eth0"
}
```

**Response** (202 Accepted):
```json
{
  "workflow_execution_id": "exec-xyz789",
  "status": "executing",
  "workflow_id": "youtube-watch-60s",
  "experiment_id": "youtube-10mbps-001",
  "start_time": "2026-03-04T10:00:00Z",
  "estimated_completion": "2026-03-04T10:01:05Z"
}
```

---

### 3. Get Workflow Status

**Endpoint**: `GET /workflows/{workflow_execution_id}`

**Response** (200 OK):
```json
{
  "workflow_execution_id": "exec-xyz789",
  "status": "executing",
  "progress": {
    "current_state": "watch",
    "states_completed": ["init", "navigate", "search", "play"],
    "percent_complete": 75
  },
  "elapsed_seconds": 45
}
```

**States**:
- pending — created, waiting to start
- executing — actively running
- paused — suspended (for debugging)
- completed — finished successfully
- failed — error occurred
- timeout — exceeded timeout_seconds

---

### 4. Get Workflow Results

**Endpoint**: `GET /workflows/{workflow_execution_id}/results`

**Response** (200 OK):
```json
{
  "workflow_execution_id": "exec-xyz789",
  "workflow_id": "youtube-watch-60s",
  "experiment_id": "youtube-10mbps-001",
  "status": "completed",
  "start_time": "2026-03-04T10:00:00Z",
  "end_time": "2026-03-04T10:01:05Z",
  "duration_seconds": 65.2,
  "states_executed": ["init", "navigate", "search", "play", "watch", "close"],
  "qoe_metrics": {
    "video_startup_time_ms": 2500,
    "mean_bitrate_mbps": 8.5,
    "bitrate_changes": 3,
    "rebuffer_events": 1,
    "rebuffer_duration_ms": 2000,
    "stall_duration_ms": 2000,
    "mean_watched_bitrate_mbps": 8.2,
    "max_bitrate_mbps": 9.5,
    "min_bitrate_mbps": 4.2
  },
  "artifacts": {
    "har_file": "/data/artifacts/exec-xyz789.har",
    "console_log": "/data/artifacts/exec-xyz789.log",
    "screenshot_count": 5,
    "screenshots": ["/data/artifacts/exec-xyz789-state1.png"]
  },
  "errors": [],
  "warnings": []
}
```

---

### 5. Compile Workflow from Spec

**Endpoint**: `POST /workflows/compile`

**Request**:
```json
{
  "nfa_spec": {
    "states": [
      {"id": "init", "type": "init"},
      {"id": "navigate", "action": "goto", "url": "https://youtube.com"},
      {"id": "search", "action": "click", "selector": "#search-input"},
      {"id": "play", "action": "click", "selector": "video-player"},
      {"id": "watch", "type": "wait", "duration": 60}
    ],
    "transitions": [
      {"from": "init", "to": "navigate"},
      {"from": "navigate", "to": "search"},
      {"from": "search", "to": "play"},
      {"from": "play", "to": "watch"}
    ]
  }
}
```

**Response** (200 OK):
```json
{
  "compiled": true,
  "workflow_id": "compiled-abc123",
  "states": 5,
  "estimated_duration_seconds": 65
}
```

---

### 6. Health Check

**Endpoint**: `GET /health`

**Response** (200 OK):
```json
{
  "status": "healthy",
  "checks": {
    "browser_chromedriver": "available",
    "browser_firefox": "available",
    "selenium_running": true,
    "workflow_engine": "operational"
  }
}
```

## Dataclass Contracts

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum

@dataclass
class WorkflowResult:
    """Complete workflow execution result."""
    workflow_execution_id: str
    workflow_id: str
    experiment_id: str
    application: str
    status: str  # executing, completed, failed, timeout
    start_time: str
    end_time: Optional[str]
    duration_seconds: float
    states_executed: List[str]
    artifacts_collected: Dict[str, Any]
    error: Optional[str] = None

@dataclass
class QoEMetrics:
    """Quality of Experience metrics."""
    video_startup_time_ms: float
    mean_bitrate_mbps: float
    bitrate_changes: int
    rebuffer_events: int
    rebuffer_duration_ms: float
    stall_duration_ms: float = 0.0
    mean_watched_bitrate_mbps: Optional[float] = None
    max_bitrate_mbps: Optional[float] = None
    min_bitrate_mbps: Optional[float] = None

@dataclass
class WorkflowSpecification:
    """NFA-based workflow definition."""
    workflow_id: str
    application: str
    description: str
    states: List[Dict[str, Any]]
    transitions: List[Dict[str, str]]
    expected_duration_seconds: int
    qoe_metric_types: List[str] = field(default_factory=list)
```

## Service Dependencies

| Service | Endpoint | Purpose |
|---------|----------|---------|
| Substrate Worker | GET /workers/metrics | Monitor network conditions during workflow |
| Storage Service | POST /artifacts | Store workflow artifacts (har, logs, screenshots) |

## Testing Criteria

### Unit Tests
- Workflow compilation produces valid NFA state machine
- QoE metric extraction from HAR/DevTools
- Application selector matching
- Timeout handling

### Integration Tests
- YouTube workflow produces consistent QoE metrics
- Zoom meeting workflow captures audio/video quality
- Netflix workflow handles login and playback
- Workflow execution under various network conditions (10, 25, 50 Mbps)
- Artifacts (HAR, logs) stored correctly
- Concurrent workflows don't interfere with each other

### Performance Tests
- Workflow compilation < 1s
- YouTube workflow execution completes in ~70s
- QoE metric extraction < 5s
- Artifact upload < 10s

## Implementation Guide

### Step 1: Project Structure
```bash
services/netgent-service/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── workflows.py
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── nfa_compiler.py     # Compile NFA to Selenium
│   │   ├── workflow_executor.py # Run workflows
│   │   ├── qoe_extractor.py    # Extract QoE metrics
│   │   └── browser_pool.py     # Manage browser instances
│   ├── applications/
│   │   ├── __init__.py
│   │   ├── youtube.py          # YouTube workflow
│   │   ├── netflix.py
│   │   ├── zoom.py
│   │   └── common.py           # Shared utilities
│   ├── models/
│   │   └── __init__.py
│   └── utils/
│       ├── __init__.py
│       └── logging.py
└── tests/
    ├── __init__.py
    └── test_*.py
```

### Step 2: NFA Compiler
```python
# app/engine/nfa_compiler.py
class NFACompiler:
    def compile(self, nfa_spec: WorkflowSpecification):
        """Convert NFA to executable workflow."""
        # Build state machine graph
        states = {s['id']: s for s in nfa_spec.states}
        transitions = nfa_spec.transitions

        # Validate NFA properties
        # Return compiled workflow object
```

### Step 3: Workflow Executor
```python
# app/engine/workflow_executor.py
from selenium import webdriver

class WorkflowExecutor:
    def execute(self, workflow: CompiledWorkflow) -> WorkflowResult:
        """Execute workflow and collect metrics."""
        driver = webdriver.Chrome()
        try:
            # Execute each state in order
            for state_id in workflow.state_order:
                self._execute_state(driver, workflow.states[state_id])

            # Extract QoE metrics
            har = self._get_har(driver)
            metrics = self._extract_qoe(har)

            return WorkflowResult(
                status="completed",
                qoe_metrics=metrics,
                artifacts={"har": har}
            )
        finally:
            driver.quit()
```

### Step 4: QoE Metric Extraction
```python
# app/engine/qoe_extractor.py
class QoEExtractor:
    def extract_from_har(self, har: dict) -> QoEMetrics:
        """Extract QoE metrics from HAR file."""
        # Find video stream entries
        # Calculate startup time (first video response)
        # Analyze bitrate changes
        # Count rebuffer events
```

### Step 5: Application-Specific Workflows
```python
# app/applications/youtube.py
def youtube_watch_60s_workflow(driver) -> WorkflowResult:
    """Watch YouTube video for 60 seconds."""
    driver.get("https://www.youtube.com")

    # Click search
    driver.find_element("id", "search").click()
    driver.find_element("id", "search-input").send_keys("big buck bunny")

    # Press Enter
    driver.find_element("id", "search-input").submit()

    # Click first video
    driver.find_element("css selector", "a#thumbnail[href*='watch?v=']").click()

    # Wait 60 seconds
    time.sleep(60)

    # Return metrics...
```

## References

- NetGent NFA workflows: Private SNL-UCSB repo
- Selenium WebDriver: https://www.selenium.dev/documentation/
- Puppeteer: https://pptr.dev/
- HAR specification: http://www.softwareishard.com/blog/har-12-spec/
- Chrome DevTools Protocol: https://chromedevtools.github.io/devtools-protocol/

---

**Last Updated**: 2026-03-04
**Status**: Specification Ready
**Next Milestone**: Integration with existing NetGent (Week 3)
